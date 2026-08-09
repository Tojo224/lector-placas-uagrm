# HEARTBEAT

## Estado vigente - 2026-08-09 - Edge Agent Fase 5

- **Foco**: aprovisionamiento de identidad, renovacion de snapshot y Outbox
  durable por HTTP, sin hacer depender OCR/decision de la red.
- **Completado**:
  - Cada `Dispositivo` puede recibir una credencial Edge aleatoria emitida una
    vez; PostgreSQL conserva solo su hash. No se usan cuentas administrativas.
  - `SyncWorker` independiente renueva el snapshot atomicamente y procesa lotes
    pequenos con PENDING/IN_FLIGHT/RETRY/SYNCED/DEAD_LETTER.
  - UUID locales son claves idempotentes centrales. ACCEPTED y DUPLICATE
    confirman el Outbox; errores transitorios aplican backoff exponencial+jitter.
  - Reinicios recuperan IN_FLIGHT, y `/status` publica red, ultimo exito,
    proximo intento y conteos del Outbox.
- **Validado**: 31 pruebas focalizadas; 113 pass/2 skip en verificador completo;
  build Vite, smoke central, cabeza Alembic unica y `git diff --check` correctos.
- **Limite vigente**: no hay media/Cloudinary Edge, frontend, empaquetado EXE,
  auto-update, WebSockets, Redis ni broker.

## Estado vigente - 2026-08-09 - Edge Agent Fase 4

- **Foco**: snapshot operativo y decision de acceso offline, sin SyncWorker.
- **Completado**:
  - Snapshot minimo autenticado desde el backend central, aplicado atomicamente a
    `cached_vehicles` y `cached_devices`, con version y fecha en `sync_state`.
  - Decision local exclusivamente sobre SQLite, reutilizando
    `access_decision.py`; cache ausente/vencido, placa desconocida, vehiculo
    inactivo o dispositivo ausente fallan cerrados.
  - Scan confirmado, evento permitido, presencia y outbox se escriben en una
    unica transaccion; el estado sobrevive reinicios.
  - Polling vacio y duplicados dentro del cooldown solo incrementan metricas y
    no hacen crecer `edge_scans`.
- **Validado**: 20 pruebas focalizadas; 102 pass/2 skip en verificador completo;
  build Vite y smoke central correctos; `git diff --check` correcto.
- **Limite vigente**: outbox solo se prepara; no hay SyncWorker, sincronizacion
  incremental, Cloudinary, cambios de esquema central, frontend ni EXE.

## Estado vigente - 2026-08-09 - Edge Agent Fase 3

- **Foco**: persistencia operativa local y durable, sin sincronizacion.
- **Completado**:
  - SQLite exclusivo del Edge Agent con WAL, foreign keys, busy timeout de 5 s
    y conexiones/transacciones cortas cerradas explicitamente.
  - Migracion local versionada `1` e idempotente con las tablas operativas
    minimas: caches, presencia, escaneos, accesos, media, outbox y estado.
  - Repositorios concretos para vehiculos, escaneos, eventos de acceso, outbox,
    media local y metadata/sync state.
  - Nota superada por Fase 4: ahora solo se persisten resultados OCR relevantes.
  - Rutas de media obligatoriamente relativas y bloqueo de claves sensibles en
    outbox/metadata.
- **Validado**: 23 pruebas focalizadas; 97 pass/2 skip en verificador completo;
  160 escrituras concurrentes sin lock; build Vite y smoke central correctos.
- **Limite vigente**: no se descargan caches, no se decide acceso, no se procesa
  ni sincroniza outbox, no se suben imagenes y no hay cambios centrales/EXE.

## Estado vigente - 2026-08-09 - Edge Agent Fase 2

- **Foco**: Edge Agent OCR independiente y estrictamente local, sin persistencia.
- **Completado**:
  - Nueva aplicacion `backend/edge_agent` con API de analisis, health, status y
    version; escucha exclusivamente en `127.0.0.1` por defecto y rechaza otros
    hosts en esta fase.
  - FastALPR/FastPlateOCR se inicializa una vez por ciclo de vida del proceso.
  - El pipeline acepta configuracion OCR inyectada, por lo que el Edge Agent no
    carga `app.config.settings` ni requiere `DATABASE_URL`.
  - `plate_analysis.py` ya no importa SQLAlchemy ni servicios de inspeccion
    vehicular durante el camino OCR; color/tipo se cargan de forma diferida solo
    para el backend central.
  - Hugging Face/Transformers opera en modo offline y el cache Matplotlib queda
    bajo `.runtime/edge`.
- **Validado**: 19 pruebas focalizadas, 90 pass/2 skip en verificador completo,
  build Vite y smoke central correctos. El motor ONNX real inicializo y analizo
  una imagen sintetica sin `DATABASE_URL` y con modo offline forzado.
- **Limite vigente**: no existen SQLite, cache de vehiculos, decision offline,
  Outbox, sincronizacion, cambios de BD ni empaquetado EXE.

## Estado vigente - 2026-08-09

- **Foco**: Migracion progresiva local-first/edge-first, limitada por ahora a la
  Fase 1 de desacoplamiento sin cambios observables.
- **Completado**:
  - `plates.py` delega la ejecucion OCR y la inspeccion vehicular a
    `app.services.plate_analysis`.
  - La inferencia de direccion y el cooldown son funciones reutilizables en
    `app.services.access_decision`.
  - El webhook de barrera reside en `app.services.barrier_actuator`.
  - Se registran latencias simples para OCR, inspeccion vehicular y total del
    request, sin agregarlas al contrato HTTP.
- **Validado**: verificador completo correcto (85 pass, 2 skip), pruebas
  focalizadas correctas (49 pass), build Vite correcto y smoke HTTP correcto.
- **Limite vigente**: no se inicio Edge Agent, SQLite, sincronizacion, cambios de
  BD, empaquetado ni cambios de frontend.

## Estado vigente - 2026-07-30

- **Foco**: Preparación y automatización del despliegue en producción.
- **Validado**: 82/82 pruebas unitarias/integración OK, smoke test HTTP OK, build Vite OK.
- **Completado en esta sesión**:
  - Cambiado localmente a la rama `main` y sincronizado con `origin/main` (22 commits nuevos).
  - Actualizadas las dependencias locales en el entorno virtual (`fast-alpr`, `fast-plate-ocr`, etc.).
  - app/main.py: implementada la ejecución automática de migraciones de Alembic y bootstrap del administrador inicial (cargado de variables de entorno) y catálogo de marcas por defecto al iniciar en `lifespan`.
  - netlify.toml: creado en la raíz para habilitar redirecciones de React Router y build automático en Netlify.
  - backend/Dockerfile: se corrigió el home del usuario `app` a `--home /app` para evitar fallos de permisos al crear cachés de modelos durante la compilación en Railway.
- **ACCIÓN REQUERIDA**: Desplegar la aplicación; ahora realiza migraciones y puesta a punto de forma automática y transparente en el arranque.

## Convenciones vigentes

- La cuenta `DISPOSITIVO` y el registro fisico `Dispositivo` se asocian por coincidencia exacta de nombre mientras no exista una FK explicita.
- No guardar contrasenas, secretos, URLs RTSP, imagenes privadas ni URLs firmadas en esta memoria.
- No hacer push o merge salvo solicitud explicita.
