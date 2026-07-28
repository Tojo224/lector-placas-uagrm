# HEARTBEAT

## Estado vigente - 2026-07-28

- **Foco**: Optimizacion de velocidad del pipeline OCR de placas (EasyOCR + Supervision + OpenCV).
- **Validado**: 44 pruebas unitarias, build Vite, migracion Alembic aplicada, HTTPS en Vite con certificado auto-firmado.
- **Completado en esta sesion**:
  - OPT-E: OCR_QUANTIZE=true en .env — cuantizacion INT8 del modelo EasyOCR en CPU (-20-35% inferencia).
  - OPT-G: Correcciones OCR ampliadas en validators.py: D->0, Q->0 (zona numerica), 4->A, 3->E (zona alfabetica).
  - OPT-A: MAX_REALTIME_DIM reducido 640->480px en pipeline.py; fallback adaptativo realtime solo si principal detecto texto pero no formato valido.
  - OPT-C: Upscale 2x solo si lado largo < 600px (antes < 1200px) — evita cuadriplicar area en imagenes de celular.
  - OPT-B: Variantes preprocesado reordenadas cheapest-first: gray_clahe -> adaptive_thresh -> morph_erode -> original -> bilateral_sharp.
  - OPT-D: VOTES_NEEDED 3->2 y throttle activo 600->500ms en UploadPlate.jsx.
  - OPT-F: Canvas convertido a escala de grises antes de toBlob() para frames realtime — JPEG 3x mas pequeno.
  - Canvas frontend alineado con backend: MAX_DETECTION_DIM = 480.
- **Completado en esta sesion (Performance Backend)**:
  - PERF-A: Refactorización completa del dashboard (`/api/v1/dashboard/summary`) reemplazando iteración de listas enteras en Python con agregación SQL nativa (`func.count`, `func.avg`), bajando la carga de memoria a casi cero.
  - PERF-B: Aplicación de una capa de `TTLCache` (30s) en `auth.py` (`get_current_user`) para evitar el costoso `SELECT` a la BD con cada petición HTTP autenticada.
  - PERF-C: Añadidos índices a la base de datos (PostgreSQL/Neon) vía Alembic (`models.py`) en las foreign keys y fechas (`propietario_usuario_id`, `esta_activo`, `creado_el`, `escaneado_id`) resolviendo table-scans en listados grandes.
  - PERF-D: Eliminación de N+1 queries redundantes en `access_logs.py` al consolidar `selectinload` duplicados, bajando dramáticamente la cantidad de queries por listado.
  - PERF-E: En `vehicles.py`, las validaciones de `create_vehicle` pasaron de 3 queries seriales a `asyncio.gather` (1 roundtrip a la BD en paralelo).
  - PERF-F: Configuración específica en `session.py` para Neon con `pool_size=5` y `max_overflow=5` previendo error de límite de conexiones agotadas.
- **Impacto total esperado (CPU, sin GPU)**:
  - Realtime: de ~600-800ms/frame -> ~300-450ms/frame
  - Static: de ~2-5s -> ~0.5-1.5s cuando imagen es buena
  - Usuario (camara): confirmacion de placa de ~2-4s -> ~1-1.5s
- **ACCION REQUERIDA**: Reiniciar el backend para que tome OCR_QUANTIZE=true.
- **Proximo paso**: Probar flujo completo celular -> OCR -> consulta placa. Considerar configurar ROI si la camara es fija (mayor ganancia adicional).
- **Convension Dispositivo y Usuario**: El nombre del Dispositivo debe coincidir exactamente con el nombre del Usuario de rol DISPOSITIVO.
- **Color vehicular fase 2**: la captura definitiva de una placa desconocida
  calcula una sugerencia HSV sobre una ROI de carrocería, guarda color y
  confianza y los prellena para revisión manual. Polling permanece intacto.
- **Validación 2026-07-28**: 44 pruebas del harness, 5 pruebas específicas de
  solicitudes/color y build Vite correctos. Migración `c7d8e9f0a1b2` aplicada.
- **Flujo desconocido revisado**: se eliminó autenticación opcional duplicada
  que podía perder el Bearer móvil; 8 pruebas específicas y smoke HTTP local
  correctos (`health=ok`, OCR/Supervision disponibles, puerto liberado).
