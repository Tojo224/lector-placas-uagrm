import argparse
import os
from pathlib import Path
import numpy as np
import cv2
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import torchvision.transforms as transforms

class MobileNetV3ColorRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        # Carga MobileNetV3-Small backbone pre-entrenado en ImageNet
        self.backbone = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
        in_features = self.backbone.classifier[0].in_features
        # Reemplaza el clasificador original con una cabeza de regresion lineal
        self.backbone.classifier = nn.Sequential(
            nn.Linear(in_features, 1024),
            nn.Hardswish(),
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(1024, 3),
            nn.Sigmoid()  # Sigmoid normaliza los valores de salida RGB en el rango [0, 1]
        )

    def forward(self, x):
        return self.backbone(x)

class SyntheticColorDataset(Dataset):
    """Generador de Dataset sintetico para pruebas rápidas y demostraciones."""
    def __init__(self, size=200):
        self.size = size
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
    def __len__(self):
        return self.size
        
    def __getitem__(self, idx):
        # Generar color aleatorio en BGR
        color_bgr = np.random.randint(0, 256, size=3, dtype=np.uint8)
        # El target sera RGB normalizado entre [0, 1]
        target = np.array([color_bgr[2], color_bgr[1], color_bgr[0]], dtype=np.float32) / 255.0
        
        # Generar imagen solida con ruido aleatorio para simular textura
        img = np.zeros((224, 224, 3), dtype=np.uint8)
        img[:, :] = color_bgr
        noise = np.random.normal(0, 8, img.shape).astype(np.int16)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return self.transform(img_rgb), torch.tensor(target, dtype=torch.float32)

def export_onnx(model, output_path: Path):
    model.eval()
    dummy_input = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        opset_version=14
    )
    print(f"Modelo ONNX exportado exitosamente a: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Entrenar y exportar MobileNetV3 Color Regressor")
    parser.add_argument("--epochs", type=int, default=5, help="Numero de epochs para entrenamiento")
    parser.add_argument("--quick-export", action="store_true", help="Exporta el modelo sin entrenarlo en base a pesos por defecto")
    parser.add_argument("--output", type=str, default="../backend/.runtime/models/color_regression.onnx", help="Ruta del ONNX resultante")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model = MobileNetV3ColorRegressor()

    if args.quick_export:
        print("Realizando exportación rápida del modelo MobileNetV3-Small...")
        export_onnx(model, output_path)
        return

    print("Iniciando entrenamiento con dataset sintetico...")
    dataset = SyntheticColorDataset(size=500)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for inputs, targets in dataloader:
            inputs, targets = inputs.to(device), targets.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * inputs.size(0)
            
        print(f"Epoch {epoch+1}/{args.epochs} - Loss: {epoch_loss / len(dataset):.6f}")

    export_onnx(model.to("cpu"), output_path)

if __name__ == "__main__":
    main()
