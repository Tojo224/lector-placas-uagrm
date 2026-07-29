FROM python:3.11-slim

# Metadatos de la imagen
LABEL maintainer="UAGRM" \
      description="Backend del Lector de Placas Bolivianas - UAGRM"

# Variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para OpenCV y PaddlePaddle/PaddleOCR (libgomp1 es crítico)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch>=2.2.0 && \
    pip install --no-cache-dir -r requirements.txt && \
    pip uninstall --yes opencv-python opencv-python-headless && \
    pip install --no-cache-dir opencv-python-headless==4.10.0.84

# Copiar el código fuente de la aplicación
COPY . .

# Puerto de la aplicación
EXPOSE 8000

# Comando de inicio con Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
