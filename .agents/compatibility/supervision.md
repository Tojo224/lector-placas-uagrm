# Compatibilidad de Supervision

Referencia revisada: `roboflow/supervision` tag estable `0.29.1`.

## Matriz soportada

| Componente | Restriccion del proyecto | Motivo |
|---|---:|---|
| Python | `>=3.9` (Docker usa 3.11; entorno validado 3.12) | Supervision 0.29.1 declara Python 3.9 a 3.14 |
| supervision | `==0.29.1` | Version estable revisada contra las APIs usadas |
| PaddleOCR | `>=2.8` | Localiza regiones de texto y reconoce caracteres (PP-OCRv4) |
| PaddlePaddle | `>=2.6.1` | Backend de deep-learning CPU-only para PaddleOCR |
| numpy | `>=2.0,<2.4` | Matrices de imagen, geometria y confianza |
| opencv-python | `==4.10.0.84` | Captura USB/RTSP y preprocesamiento local |
| opencv-python-headless | `==4.10.0.84` | Entornos sin GUI (Docker, servidores) |
| Pillow | `>=11,<12` | Compatibilidad de imagen con Supervision |

## APIs del proyecto verificadas

- `sv.crop_image`
- `sv.BoxAnnotator(..., color_lookup=sv.ColorLookup.INDEX)`
- `sv.LabelAnnotator(..., color_lookup=sv.ColorLookup.INDEX)`
- `sv.Detections(xyxy=..., confidence=..., data=...)` -- construccion directa desde resultados PaddleOCR

Nota: `sv.Detections.from_easyocr` fue eliminado. PaddleOCR devuelve poligonos de 4 puntos
que se convierten a `xyxy` mediante `_detections_from_paddle()` en `pipeline.py`.

## Politica de actualizacion

1. No usar rangos sin limite superior para el stack de vision.
2. Revisar primero los requisitos oficiales de Supervision y PaddleOCR.
3. Actualizar esta matriz y `requirements.txt` juntos.
4. Ejecutar `.agents/scripts/verify-project.ps1` antes de aceptar el cambio.
5. Una validacion con mocks no sustituye una prueba fisica con placa, iluminacion y camara reales.

`-SkipVersionCheck` solo sirve para validar estructura, compilacion y frontend en un entorno global no sincronizado. La verificacion de entrega debe ejecutarse sin ese parametro dentro del entorno virtual del backend.
