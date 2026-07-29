# HEARTBEAT

## Estado vigente - 2026-07-28

<<<<<<< HEAD
- **Foco**: Integración de la rama `Beto` en `devgrover` + Corrección de hallazgos de seguridad y robustez tras revisión 4R.
- **Validado**: 
  - 4R review completada (R1 Risk, R4 Resilience, R2 Readability, R3 Reliability). 26 archivos, 1372 líneas revisadas. Estado: approved.
  - Soporte de cámara USB enumeradas por el navegador y conexión del celular mediante USB.
  - Rediseño del modal de revisión de vehículos desconocidos.
- **Completado en esta sesión**:
=======
<<<<<<< HEAD
<<<<<<< Updated upstream
- Foco: ejecucion local/Docker con PostgreSQL externo, Neon y Cloudinary.
- Validado: 44 pruebas, build Vite, HTTP/proxy/OpenAPI, Neon TLS/SELECT 1/Alembic
  y Cloudinary real local y Docker.
- Corregido: multipart Axios, `NotFound` Cloudinary, pool PostgreSQL con
  `pool_pre_ping`, Docker headless/CPU y exclusion de secretos del contexto.
- Datos: dos operadores, dos administradores, una cuenta dispositivo y los
  catalogos Toyota/Nissan/Automóvil/Motocicleta. No guardar contrasenas.
- Flujo DISPOSITIVO: login a `/subir-placa`; la cuenta no esta vinculada
  automaticamente con la entidad fisica `Dispositivo`.
- Pendientes: camara USB/RTSP real, calibracion OCR, vinculo cuenta-dispositivo,
  repositorio remoto y dos avisos moderados React Router.
- Proximo paso: modelar el vinculo de identidad del dispositivo y probar con
  hardware real.

- Fase 1 placas desconocidas implementada en rama `feat/unknown-vehicle-phase1`:
  el análisis no-realtime de una placa válida no registrada guarda una única
  imagen WebP authenticated en Cloudinary, crea solicitud PENDING y expone
  bandeja staff con aprobación/rechazo transaccional. El polling realtime no
  sube imágenes ni crea solicitudes. No se detectan marca/color todavía.
- Incidencia corregida: Neon tenía `alembic_version=3aa735770818`, revisión
  ausente en el checkout. Se añadió ancla de compatibilidad y se ejecutó
  `alembic upgrade head`; Neon quedó en `a1b2c3d4e5f6` con la tabla nueva.
- Bandeja rediseñada: tarjetas compactas + modal estilo registro manual, con
  catálogos legibles, placa editable, evidencia Cloudinary y confirmaciones.

- Foco actual: Consolidación del sistema de roles (ADMINISTRADOR, OPERADOR, DISPOSITIVO, USUARIO) y del flujo de registro de accesos vehiculares manuales y automáticos.
- Ultimo avance: Se completó la separación de flujos por rol en el frontend (Vehicles.jsx, AccessLogs.jsx, UploadPlate.jsx, Sidebar, AppRoutes). El rol DISPOSITIVO tiene acceso exclusivo a la vista de cámara en vivo, con registro automático de Ingreso/Salida inferido por el estado del campus. El endpoint `/api/v1/access-logs/auto` ahora acepta `direction` explícita del operador además de inferirla. Se corrigió el error 422 del formulario de acceso manual (endpoint incorrecto), el mensaje vacío del ConfirmModal (clave `message` vs `mensaje`) y se añadió búsqueda de placa en tiempo real en el modal de acceso manual.
- Estructura actual: backend/ y frontend/ directos en la raíz; docker-compose.yml en la raíz; submódulos en frontend/src/components/ y páginas en frontend/src/pages/.
- Inventario confirmado: Suite completa de 23 pruebas unitarias y empaquetado de producción Vite completados correctamente (100% exitoso).
- Bloqueos: `CAM-004` y `OCR-PHYSICAL-001` siguen bloqueados por hardware físico real. `REPO-001` pendiente de repositorio remoto vacío.
- Proximo paso: Integrar y calibrar con cámaras IP en el entorno físico de la universidad. Validar flujo completo DISPOSITIVO con login → vista de cámara → registro automático de acceso.
- Estado del Alpha: Roles diferenciados, pipeline OCR optimizado, accesos manuales y automáticos funcionales, Dashboard premium unificado, gestión de vehículos por admin/operador completa.
=======
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
- **Deteccion a distancia**: realtime ahora conserva 960 px, solicita cámara 1080p,
  usa JPEG 90%, `mag_ratio=1.25` y ejecuta el fallback sensible aunque la primera
  pasada no encuentre texto. Pipeline OCR (13 pruebas) y build Vite validados.
- **Placas en movimiento**: cámara solicita 24-30 fps y enfoque/exposición
  continuos cuando están disponibles; polling baja a 100-250 ms, elimina la
  conversión gris costosa del navegador y permite captura inmediata con score
  válido >= 0.88. Build Vite validado.
- **Cámara USB para staff**: ADMINISTRADOR y OPERADOR pueden entrar a
  `/subir-placa`, seleccionar cámaras USB enumeradas por el navegador y cambiar
  de dispositivo sin recargar. Se manejan conexión/desconexión, aborto del OCR
  activo y liberación del stream anterior. Build Vite validado.
- **Proximo paso**: Probar flujo completo celular -> OCR -> consulta placa. Considerar configurar ROI si la camara es fija (mayor ganancia adicional).
- **Convension Dispositivo y Usuario**: El nombre del Dispositivo debe coincidir exactamente con el nombre del Usuario de rol DISPOSITIVO.
- **Solicitudes desconocidas en main**: corregida autenticación opcional duplicada
  para conservar Bearer móvil y errores explícitos al persistir formularios.
>>>>>>> Stashed changes
=======
- **Foco**: Corrección de hallazgos de seguridad y robustez tras revisión 4R.
- **Validado**: 4R review completada (R1 Risk, R4 Resilience, R2 Readability, R3 Reliability). 26 archivos, 1372 líneas revisadas. Estado: approved.
- **Completado en esta sesión (4R + Fixes)**:
>>>>>>> Beto
  - **SDD Init**: Inicializado con engram, strict TDD activado.
  - **4R Review**: Risk, Resilience, Readability, Reliability ejecutados con native gentle-ai.
  - **SEC-011**: Token JWT removido de localStorage — solo cookie httpOnly session_token.
  - **SEC-012**: PII propietario_nombre solo para usuarios autenticados en /analyze.
  - **SEC-013**: Excepción de BD en plates.py ya no es tragada — retorna 500 con log.
  - **SEC-014**: TOCTOU en cooldown de accesos corregido con FOR UPDATE.
  - **ROB-001**: asyncio.gather sobre misma AsyncSession reemplazado por awaits secuenciales.
  - **ROB-002**: Acumulación de streams de cámara corregida — stopCamera siempre en cleanup.
  - **ROB-003**: Limitación de TTLCache in-process documentada.
<<<<<<< HEAD
  - **BETO-CONN**: Soporte para conexión de celular mediante USB y selección/enumeración de cámaras USB en `/subir-placa` sin recargar la página.
  - **BETO-UI**: Rediseño de la bandeja y modal de revisión de vehículos desconocidos.
- **ACCION REQUERIDA**: Ninguna por ahora. Backend listo para reiniciar.
- **Proximo paso**: Resolver pendientes del backlog o iniciar nuevo feature (como la migración a PaddleOCR).
- **Convension Dispositivo y Usuario**: El nombre del Dispositivo debe coincidir exactamente con el nombre del Usuario de rol DISPOSITIVO.
=======
- **ACCION REQUERIDA**: Ninguna por ahora. Backend listo para reiniciar.
- **Proximo paso**: Resolver pendientes del backlog o iniciar nuevo feature.
- **Convension Dispositivo y Usuario**: El nombre del Dispositivo debe coincidir exactamente con el nombre del Usuario de rol DISPOSITIVO.
>>>>>>> origin/main
>>>>>>> Beto
