FROM python:3.12-slim

# Metadatos de la imagen
LABEL maintainer="UAGRM" \
      description="Backend del Lector de Placas Bolivianas - UAGRM"

# Variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip uninstall --yes opencv-python && \
    pip install --no-cache-dir --no-deps --force-reinstall \
      opencv-python-headless==4.10.0.84

# Copiar el código fuente de la aplicación
COPY . .

RUN addgroup --system app && adduser --system --ingroup app --home /app app && \
    mkdir -p /app/.runtime && chown -R app:app /app

# Forzar el cache de HuggingFace en la ruta del runtime propiedad del usuario app
ENV HF_HOME=/app/.runtime/huggingface

USER app

# Descarga los modelos ONNX durante el build para no depender de Internet al arrancar.
RUN python -c "from fast_alpr import ALPR; ALPR(detector_model='yolo-v9-t-384-license-plate-end2end', detector_providers=['CPUExecutionProvider'], ocr_model='cct-xs-v2-global-model', ocr_device='cpu', ocr_providers=['CPUExecutionProvider'])"

# Preinstala tambien el detector vehicular, CLIP y el modelo de Marca/Modelo para operar sin red al arrancar.
RUN python -c "from open_image_models.detection.factory import create_detector; create_detector('rf-detr-nano-384-coco', conf_thresh=.45, providers=['CPUExecutionProvider'])" && \
    python -c "from huggingface_hub import hf_hub_download; files=['onnx/model_quantized.onnx','tokenizer.json','tokenizer_config.json','special_tokens_map.json','preprocessor_config.json','config.json']; [hf_hub_download(repo_id='Xenova/clip-vit-base-patch32', revision='d15189d7028b43f1d3e65039190477f6af591c2a', filename=f, local_dir='/app/.runtime/models/clip-vit-b-32') for f in files]" && \
    python -c "import urllib.request, pathlib; p=pathlib.Path('/app/models'); p.mkdir(parents=True, exist_ok=True); urllib.request.urlretrieve('https://github.com/Tatiana72499/uagrm-modelomarca-ai/releases/download/model-v4/brand-model-v4-bolivia12.onnx', p/'brand-model-v4-bolivia12.onnx') if not (p/'brand-model-v4-bolivia12.onnx').exists() else None; urllib.request.urlretrieve('https://github.com/Tatiana72499/uagrm-modelomarca-ai/releases/download/model-v4/brand-model-v4-bolivia12.onnx.data', p/'brand-model-v4-bolivia12.onnx.data') if not (p/'brand-model-v4-bolivia12.onnx.data').exists() else None; urllib.request.urlretrieve('https://github.com/Tatiana72499/uagrm-modelomarca-ai/releases/download/model-v4/brand-model-v4-bolivia12.labels.json', p/'brand-model-v4-bolivia12.labels.json') if not (p/'brand-model-v4-bolivia12.labels.json').exists() else None"

# Puerto de la aplicación
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/plates/health', timeout=5)" || exit 1

# Comando de inicio con Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
