# Issue 015 — Color del vehículo solo disponible como entrada manual

## Corrección

La captura definitiva de una placa desconocida ahora se analiza una sola vez
con OpenCV. Se toma una región probable de carrocería por encima de la placa,
se clasifica el color en HSV y se guardan `color_sugerido` y
`confianza_color` en la solicitud.

El polling permanece sin análisis de color. La bandeja prellena el color y
muestra su confianza, pero el operador conserva la obligación de verificarlo
y puede corregirlo antes de aprobar.

## Limitación conocida

Es una estimación para cámaras con encuadre relativamente estable. Reflejos,
oscuridad, fondos u oclusiones pueden reducir la precisión; por ello nunca se
registra automáticamente como dato definitivo.

## Corrección adicional del flujo

Se eliminó la autenticación opcional duplicada de `plates.py`. El endpoint usa
ahora el resolvedor central, compatible tanto con cookie como con token Bearer,
para que las capturas desde dispositivos móviles conserven al creador. Los
errores de persistencia ya no se ocultan como análisis exitosos.
