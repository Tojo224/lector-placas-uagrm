"""
Entrenamiento del regresor de color vehicular MobileNetV3-Small.

El dataset sintetico simula las condiciones reales que enfrenta el clasificador
como fallback de OpenCV:
  - Vehiculos vistos a distintas horas (iluminacion alta, media y baja)
  - Reflejos especulares y sombras parciales sobre la carroceria
  - Ruido de camara y compresion JPEG
  - Gradientes de iluminacion no uniformes (luz lateral, contraluz suave)
  - Mezcla de textura metalica y mate

Arquitectura: MobileNetV3-Small backbone pre-entrenado en ImageNet + cabeza
de regresion que predice RGB normalizado en [0,1]. La salida se convierte a
HEX y se clasifica en el catalogo cerrado de 9 colores por distancia euclidiana.
"""

import argparse
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import torchvision.transforms as transforms


# ---------------------------------------------------------------------------
# Catalogo cerrado - mismo que vehicle_color.py
# ---------------------------------------------------------------------------
CATALOG_RGB: dict[str, tuple[int, int, int]] = {
    "BLANCO":   (235, 235, 235),
    "NEGRO":    ( 28,  28,  28),
    "GRIS":     (105, 105, 105),
    "PLATEADO": (178, 178, 178),
    "ROJO":     (190,  40,  40),
    "AZUL":     ( 35,  85, 180),
    "VERDE":    ( 65, 145,  65),
    "AMARILLO": (220, 205,  35),
    "MARRON":   (115,  75,  45),
}

# Variaciones de tono intra-clase (delta RGB maxima)
CATALOG_VARIANCE: dict[str, int] = {
    "BLANCO":   18,
    "NEGRO":    12,
    "GRIS":     30,
    "PLATEADO": 28,
    "ROJO":     40,
    "AZUL":     45,
    "VERDE":    40,
    "AMARILLO": 35,
    "MARRON":   40,
}


# ---------------------------------------------------------------------------
# Generacion de parches sinteticos de carroceria vehicular
# ---------------------------------------------------------------------------

def _random_base_color() -> tuple[str, np.ndarray]:
    """Elige una clase del catalogo y genera RGB con variacion intra-clase."""
    name = random.choice(list(CATALOG_RGB))
    base = np.array(CATALOG_RGB[name], dtype=np.float32)
    delta = CATALOG_VARIANCE[name]
    variation = np.random.uniform(-delta, delta, 3)
    rgb = np.clip(base + variation, 0, 255).astype(np.uint8)
    return name, rgb


def _apply_lighting(img: np.ndarray, mode: str) -> np.ndarray:
    """Aplica una condicion de iluminacion realista sobre la imagen BGR."""
    h, w = img.shape[:2]

    if mode == "bright":
        factor = np.random.uniform(1.10, 1.35)
        img = np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)

    elif mode == "low":
        factor = np.random.uniform(0.45, 0.72)
        img = np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)

    elif mode == "gradient_lr":
        grad = np.linspace(0.60, 1.25, w, dtype=np.float32)
        alpha = np.tile(grad, (h, 1))
        img = np.clip(img.astype(np.float32) * alpha[:, :, None], 0, 255).astype(np.uint8)

    elif mode == "gradient_tb":
        grad = np.linspace(1.20, 0.65, h, dtype=np.float32)
        alpha = np.tile(grad.reshape(-1, 1), (1, w))
        img = np.clip(img.astype(np.float32) * alpha[:, :, None], 0, 255).astype(np.uint8)

    elif mode == "shadow":
        x1 = random.randint(0, w // 2)
        x2 = random.randint(w // 2, w)
        shadow_factor = np.random.uniform(0.35, 0.62)
        img = img.astype(np.float32)
        img[:, x1:x2] *= shadow_factor
        img = np.clip(img, 0, 255).astype(np.uint8)

    elif mode == "specular":
        cx = random.randint(w // 4, 3 * w // 4)
        cy = random.randint(h // 4, 3 * h // 4)
        rx = random.randint(w // 8, w // 3)
        ry = random.randint(h // 8, h // 3)
        mask = np.zeros((h, w), dtype=np.float32)
        cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1, rx // 3 + 4))
        mask = mask / (mask.max() + 1e-6)
        intensity = np.random.uniform(0.55, 0.90)
        img = img.astype(np.float32)
        img += (255 - img) * mask[:, :, None] * intensity
        img = np.clip(img, 0, 255).astype(np.uint8)

    return img


def _apply_texture(img: np.ndarray, style: str) -> np.ndarray:
    """Agrega textura de pintura metalica, mate o nacarada."""
    if style == "metallic":
        noise = np.random.normal(0, 9, img.shape[:2]).astype(np.float32)
        noise = cv2.GaussianBlur(noise, (1, 15), 0)
        img = np.clip(img.astype(np.float32) + noise[:, :, None], 0, 255).astype(np.uint8)
    elif style == "matte":
        noise = np.random.normal(0, 5, img.shape).astype(np.float32)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    elif style == "pearlescent":
        angle_noise = np.random.normal(0, 14, img.shape).astype(np.float32)
        angle_noise = cv2.GaussianBlur(angle_noise, (5, 5), 0)
        img = np.clip(img.astype(np.float32) + angle_noise * 0.6, 0, 255).astype(np.uint8)
    return img


def _apply_jpeg_noise(img: np.ndarray) -> np.ndarray:
    quality = random.randint(55, 92)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _generate_vehicle_patch(size: int = 224) -> tuple[np.ndarray, np.ndarray]:
    """
    Genera un parche sintetico de carroceria vehicular.
    Retorna (imagen BGR uint8 224x224, target RGB float32 normalizado [0,1]).
    """
    _name, rgb = _random_base_color()
    bgr = rgb[::-1].copy()

    img = np.full((size, size, 3), bgr, dtype=np.uint8)

    texture = random.choice(["metallic", "matte", "pearlescent", "matte"])
    img = _apply_texture(img, texture)

    lighting = random.choice(["normal", "bright", "low",
                              "gradient_lr", "gradient_tb",
                              "shadow", "specular"])
    if lighting != "normal":
        img = _apply_lighting(img, lighting)

    cam_noise = np.random.normal(0, random.uniform(2, 7), img.shape).astype(np.float32)
    img = np.clip(img.astype(np.float32) + cam_noise, 0, 255).astype(np.uint8)

    if random.random() < 0.60:
        img = _apply_jpeg_noise(img)

    target = rgb.astype(np.float32) / 255.0
    return img, target


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class VehicleColorDataset(Dataset):
    """Dataset sintetico mejorado para regresion de color vehicular."""

    def __init__(self, size: int = 4000) -> None:
        self.size = size
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, idx: int):
        bgr, target = _generate_vehicle_patch(224)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return self.transform(rgb), torch.tensor(target, dtype=torch.float32)


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

class MobileNetV3ColorRegressor(nn.Module):
    """MobileNetV3-Small con cabeza de regresion RGB en [0,1]."""

    def __init__(self) -> None:
        super().__init__()
        self.backbone = models.mobilenet_v3_small(
            weights=models.MobileNet_V3_Small_Weights.DEFAULT
        )
        in_features = self.backbone.classifier[0].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Linear(in_features, 512),
            nn.Hardswish(),
            nn.Dropout(p=0.25, inplace=True),
            nn.Linear(512, 3),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)


# ---------------------------------------------------------------------------
# Exportacion ONNX
# ---------------------------------------------------------------------------

def export_onnx(model: nn.Module, output_path: Path) -> None:
    model.eval()
    dummy = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        opset_version=18,
    )
    print(f"Modelo ONNX exportado: {output_path}")


# ---------------------------------------------------------------------------
# Entrenamiento con warmup progresivo
# ---------------------------------------------------------------------------

def train(args) -> "MobileNetV3ColorRegressor":
    dataset = VehicleColorDataset(size=args.samples)
    loader = DataLoader(dataset, batch_size=args.batch_size,
                        shuffle=True, num_workers=0, pin_memory=False)

    model = MobileNetV3ColorRegressor()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    # Fase warmup: congelar backbone para estabilizar la nueva cabeza
    for param in model.backbone.features.parameters():
        param.requires_grad = False

    criterion = nn.MSELoss()
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.lr, weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=1e-5,
    )

    warmup_epochs = max(1, args.epochs // 5)
    print(f"Dispositivo: {device}  |  Muestras: {args.samples}  |  Epocas: {args.epochs}")
    print(f"Warmup: {warmup_epochs} epocas (backbone congelado)")

    for epoch in range(1, args.epochs + 1):
        if epoch == warmup_epochs + 1:
            for param in model.backbone.features.parameters():
                param.requires_grad = True
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=args.lr * 0.2, weight_decay=1e-4,
            )
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer,
                T_max=args.epochs - warmup_epochs,
                eta_min=1e-6,
            )
            print("Backbone descongelado para fine-tuning.")

        model.train()
        total_loss = 0.0
        for inputs, targets in loader:
            inputs, targets = inputs.to(device), targets.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * inputs.size(0)

        scheduler.step()
        avg = total_loss / len(dataset)
        rmse_255 = (avg ** 0.5) * 255
        print(f"Epoca {epoch:>3}/{args.epochs}  |  "
              f"MSE={avg:.6f}  |  RMSE~{rmse_255:.2f}/255  |  "
              f"LR={scheduler.get_last_lr()[0]:.2e}")

    model.to("cpu")
    return model


# ---------------------------------------------------------------------------
# Evaluacion post-entrenamiento
# ---------------------------------------------------------------------------

def quick_eval(model: nn.Module, n: int = 300) -> None:
    """Evalua accuracy de clasificacion por catalogo y error HEX medio."""
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])
    catalog = np.array(list(CATALOG_RGB.values()), dtype=np.float32) / 255.0
    names = list(CATALOG_RGB.keys())

    correct: dict[str, int] = defaultdict(int)
    total_per_class: dict[str, int] = defaultdict(int)
    hex_errors: list[float] = []

    model.eval()
    with torch.no_grad():
        for _ in range(n):
            bgr, target = _generate_vehicle_patch(224)
            rgb_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            inp = transform(rgb_img).unsqueeze(0)
            pred = model(inp).squeeze().numpy()

            dists = np.linalg.norm(catalog - pred, axis=1)
            predicted_name = names[int(np.argmin(dists))]

            # Map target RGB back to its catalog name (closest match)
            target_dists = np.linalg.norm(catalog - target, axis=1)
            actual_name = names[int(np.argmin(target_dists))]

            total_per_class[actual_name] += 1
            if predicted_name == actual_name:
                correct[actual_name] += 1

            hex_errors.append(float(np.linalg.norm((pred - target) * 255)))

    overall = sum(correct.values()) / max(1, sum(total_per_class.values()))
    mean_hex_err = float(np.mean(hex_errors))
    print(f"\n--- Evaluacion post-entrenamiento ({n} muestras) ---")
    print(f"Accuracy clasificacion por catalogo: {overall*100:.1f}%")
    print(f"Error HEX medio (L2 en 0-255):       {mean_hex_err:.2f}")
    print("Detalle por clase:")
    for cls in names:
        total_c = total_per_class.get(cls, 0)
        acc = correct.get(cls, 0) / max(1, total_c)
        print(f"  {cls:<10s}: {acc*100:5.1f}%  ({total_c} muestras)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entrenar y exportar MobileNetV3 Color Regressor para vehiculos"
    )
    parser.add_argument("--epochs", type=int, default=25,
                        help="Epocas de entrenamiento (default: 25)")
    parser.add_argument("--samples", type=int, default=4000,
                        help="Muestras sinteticas (default: 4000)")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Batch size (default: 64)")
    parser.add_argument("--lr", type=float, default=5e-4,
                        help="Learning rate inicial (default: 5e-4)")
    parser.add_argument("--quick-export", action="store_true",
                        help="Solo exportar pesos por defecto sin entrenar")
    parser.add_argument("--output", type=str,
                        default="backend/.runtime/models/color_regression.onnx",
                        help="Ruta de salida del ONNX")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.quick_export:
        print("Exportacion rapida (sin entrenamiento)...")
        model = MobileNetV3ColorRegressor()
    else:
        model = train(args)
        quick_eval(model)

    export_onnx(model, output_path)


if __name__ == "__main__":
    main()
