# HEARTBEAT

## Estado vigente - 2026-07-29

- **Foco**: Integración de PaddleOCR v3.0, corrección de fallos en CPU/OneDNN y conversión de imágenes en escala de grises.
- **Validado**: 48/48 pruebas unitarias OK, build Vite OK, compilación Python OK.
- **Completado en esta sesión**:
  - requirements.txt: añadidas dependencias transformers>=4.40.0 y torch>=2.2.0 (CPU).
  - app/core/paths.py: añadida cache HF_CACHE_DIR y configurada la variable de entorno HF_HOME para descarga local.
  - app/main.py: cargado de pipeline("zero-shot-image-classification") en lifespan en CPU de manera condicional (ENABLE_HF_CLASSIFICATION). Inicialización de PaddleOCR v3.0 con `enable_mkldnn=False` (soluciona error de CPU en Windows) y exclusión de modelos de documentos (`use_doc_orientation_classify=False`, `use_doc_unwarping=False`).
  - app/ai/pipeline.py: implementada la función classify_vehicle_attributes. Ajustada `_run_ocr` para asegurar que las imágenes siempre tengan 3 canales (conversión de Gray a BGR) ya que PaddleOCR v3.0 falla con imágenes 2D y adaptada la lectura de salida para soportar el formato diccionario (Paddlex) y lista clásica (EasyOCR).
  - app/api/v1/plates.py: consumo de catálogos dinámicos (Marca y TipoVehiculo) de la base de datos y ejecución del clasificador al crear SolicitudRegistroVehiculo.
  - app/schemas/plate.py: campos marca_sugerida, tipo_sugerido y color_sugerido añadidos a PlateAnalysisResponse.
  - tests: test de integración y test de contrato de API actualizados.
- **ACCIÓN REQUERIDA**: Iniciar el backend con `python run.py`. La velocidad del escaneo realtime ahora es excelente y sin bloqueos por formato de canales.
- **Convención Dispositivo y Usuario**: El nombre del Dispositivo debe coincidir exactamente con el nombre del Usuario de rol DISPOSITIVO.
