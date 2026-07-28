# Issue 017 — Escaneo desconocido sin solicitud pendiente

## Evidencia

Neon contenía escaneos recientes de la placa `2534RIS` como `DETECTADO` y sin
vehículo asociado, pero no existía una solicitud de registro correspondiente.

## Causa

El endpoint de placas tenía un resolvedor opcional de autenticación duplicado.
En capturas móviles podía perder el token Bearer y dejar `current_user=None`;
el escaneo se guardaba, pero la condición que exige un creador impedía crear la
solicitud. El proceso que produjo el incidente todavía usaba ese código.

## Corrección

`plates.py` usa ahora el resolvedor central compatible con cookie y Bearer. Los
fallos de persistencia de una solicitud ya no se silencian como análisis
exitosos. Se añadió una prueba específica del token Bearer y se sincronizó la
`.venv` utilizada por el arranque local.

## Validación

- 8 pruebas específicas correctas.
- Smoke HTTP local correcto.
- `health=ok`, EasyOCR y Supervision disponibles.
