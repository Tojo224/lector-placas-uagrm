# MEMORY

## 2026-08-10 - Aprovisionamiento automatico por identidad de instalacion

- Una PC Edge tiene UUID de instalacion independiente de `Dispositivo`. El UUID
  no secreto vive en `config/agent.json`; el secreto aleatorio vive solo en el
  proveedor DPAPI CurrentUser. SQLite, UI y logs no contienen ese secreto.
- El primer login central valido de ADMINISTRADOR/OPERADOR usa el token humano
  solo para autorizar `POST /api/v1/edge-sync/installations/provision`. El token
  no se conserva. PostgreSQL guarda unicamente el hash del secreto tecnico.
- SyncWorker prefiere `X-Edge-Installation-ID` + bearer tecnico y sigue activo
  despues del logout/reinicio. El protocolo legacy Device ID/Edge Key queda como
  fallback interno para instalaciones ya provisionadas.
- Se agrego Alembic `e4f5a6b7c8d9` con `edge_installations`; debe desplegarse en
  central antes de aprovisionar una instalacion nueva. No se altero
  `RoleEnum.DISPOSITIVO` ni se exige crear/seleccionar un Dispositivo.
- Validacion: 51 focalizadas; 155 pass/2 skip; build Vite y smoke correctos.

## 2026-08-10 - Autenticacion offline derivada, sin hashes centrales

- `local_auth_users` (migracion SQLite 3) conserva unicamente
  `central_user_id`, carnet, rol ADMINISTRADOR/OPERADOR, `local_verifier` PBKDF2
  con salt propio y fechas. El token devuelto por el login central se descarta y
  nunca se persiste.
- Con URL configurada, login intenta central primero. Una validacion correcta
  renueva el verificador local; 401/403 central no cae al cache. Un error real
  de transporte o 5xx permite verificar offline. Sin fila previa se explica que
  hace falta un primer login con Internet.
- Las sesiones Edge son opacas y viven en memoria del proceso; siguen activas
  cuando cae Internet. Tras reiniciar el agente se vuelve a autenticar, pudiendo
  usar el verificador offline. El frontend descarta sesiones locales con rol
  USUARIO o DISPOSITIVO.
- `ProductConfigStore.save(url)` preserva un device_id existente y no toca el
  blob DPAPI. Configuracion ya no recibe ni muestra ID/clave; SyncWorker conserva
  el protocolo tecnico actual. No se cambio PostgreSQL ni RoleEnum.DISPOSITIVO.
- Validacion: 35 focalizadas; 151 pass/2 skip; verify/build/smoke correctos;
  EXE/Setup reconstruidos e instalados. Runtime instalado confirmo SQLite v3,
  OCR/DB READY, rechazo offline inicial y MIME/404 portable.

## 2026-08-09 - Correccion MIME portable del servidor estatico Edge

- `FileResponse`/`StaticFiles` terminaban consultando `mimetypes`, que en una
  segunda PC Windows resolvio modulos Vite como `text/plain`. `EdgeStaticFiles`
  ahora pasa `media_type` explicito para `.js`, `.mjs`, `.css`, `.json`, `.svg`
  y `.wasm`, por lo que no depende del registro MIME local.
- El catch-all React rechaza explicitamente `assets` y `assets/*`. Un archivo
  ausente en el mount o incluso un build sin directorio assets devuelve 404;
  solo rutas de navegacion reciben `index.html` con `text/html` explicito.
- Prueba instalada desde Program Files: JS 200 `application/javascript`, CSS
  200 `text/css; charset=utf-8`, `/subir-placa` 200 `text/html` y JS inexistente
  404. Health posterior: READY, OCR y SQLite correctos.
- Validacion: 12 pruebas focalizadas, 142 pass/2 skip, build Vite, verificador,
  smoke central, EXE/Setup reconstruidos e instalados y diff-check correctos.

## 2026-08-09 - Perfil y optimizacion del EXE instalado 0.2.0

- El baseline del EXE instalado fue API 30,923 ms, React 31,205 ms y READY
  31,297 ms. API->READY era solo 373 ms: el cuello estaba antes del lifespan,
  no en la creacion de sesiones ONNX.
- `OCRPipelineConfig` se movio a un modulo liviano y `plate_analysis` carga el
  pipeline de forma diferida. En Edge las anotaciones estaticas usan OpenCV; el
  backend central conserva Supervision. No se cambiaron detector, reconocedor,
  pesos, providers, thresholds ni validadores.
- La carga OCR se ejecuta fuera del hilo HTTP y health/status exponen tiempos.
  Una ejecucion representativa midio imports OCR 462 ms, detector 182 ms,
  FastPlateOCR 99 ms, sesiones ONNX 276 ms y OCR total 744 ms.
- PyInstaller excluye del producto Edge SciPy, Supervision, Matplotlib,
  RF-DETR/CLIP y servicios de color/tipo. Una reinstalacion limpia fue necesaria
  porque una actualizacion Inno sobre el directorio anterior no retiro archivos
  obsoletos. El producto limpio ocupa 223.2 MiB; el onedir puro 218.8 MiB.
- En arranques normales instalados: API 1.35-1.45 s, React 1.47-1.54 s y READY
  1.87-2.19 s. Justo despues de una instalacion limpia, Windows empleo 13.1 s
  antes del lifespan del EXE no firmado, aunque OCR interno tardo 728 ms; es
  consistente con inspeccion/reputacion antivirus y requiere Authenticode.
- Una imagen sintetica con placa fue DETECTED por el EXE instalado. Primera
  peticion 70-94 ms, calientes 67-94 ms promedio (minimo observado 61.8 ms) y
  confirmacion completa 80-106 ms. RAM estable ~156 MiB, frente a 218 MiB del
  baseline. Validacion: 135 pass/2 skip, verify/build/smoke correctos.

## 2026-08-09 - Instalador productivo Windows 0.2.0

- Inno Setup 6.7.3 genera `UAGRMPlateAgent-Setup.exe` de 99,074,482 bytes desde
  el onedir. Instala en Program Files y no declara ProgramData como contenido
  desinstalable, por lo que actualizaciones/desinstalaciones preservan SQLite,
  Outbox, spool, configuracion, DPAPI y logs.
- ACL instalada: BUILTIN\Users `Modify/Synchronize` sobre
  `%ProgramData%\UAGRM\PlateAgent` y subdirectorios. La tarea ONLOGON se crea
  mediante COM Task Scheduler, modo interactivo limitado, y se elimina al
  desinstalar. `schtasks.exe` fue descartado porque el Windows administrado lo
  bloqueaba desde Setup.
- `ProductConfigStore` guarda solo URL central y device ID. La credencial usa
  `CryptProtectData/CryptUnprotectData` con alcance CurrentUser y escritura
  atomica. Aprovisionamiento valida UUID, HTTPS (HTTP solo loopback), credencial
  y snapshot antes de guardar y arrancar SyncWorker.
- OCR se inicializa en tarea de fondo en ejecucion productiva: API/UI aparecen
  con `INITIALIZING_OCR` y cambian a READY/DEGRADED. No se cambio el pipeline.
- Prueba real del EXE instalado contra central local: PROVISIONED, snapshot
  `setup-test`, `agent.json` sin secreto y blob DPAPI de 280 bytes sin texto
  recuperable. EXE y Setup reportan ProductVersion 0.2.0.
- Instalacion limpia y actualizaciones correctas. Desinstalar retiro Program
  Files y tarea, con ProgramData y sus 3 archivos intactos; reinstalar reutilizo
  ProgramData y recreo la tarea. No hubo VM ni reinicio fisico.
- Hash final Setup:
  `72dfe4d8052a6ed9f384e024abbc072267d901a74c6987d0c92121bc67b8bf9f`.
  Ambos artefactos permanecen sin Authenticode y requieren firma institucional.
- Validacion final: 135 pass/2 skip, verificador completo, build Vite, smoke
  central y `git diff --check` correctos.

## 2026-08-09 - Primera distribucion Windows onedir

- Se eligio PyInstaller 6.16 frente a Nuitka por sus hooks maduros para el stack
  dinamico CPython/ONNX Runtime/OpenCV y por no requerir toolchain C en el host
  de build. La primera entrega permanece `onedir`, no `onefile`.
- El build incluye exclusivamente los modelos activos: detector
  `yolo-v9-t-384-license-plates-end2end` (ONNX 7,771,218 bytes), OCR
  `cct-xs-v2-global-model` (ONNX 3,344,292 bytes) y su YAML (1,725 bytes). Un
  manifiesto versionado valida sus SHA-256 antes de empaquetar.
- En modo frozen los recursos se resuelven desde `sys._MEIPASS`; el OCR recibe
  rutas locales directas y no usa los caches del perfil ni descarga inicial.
  React se resuelve de la misma raiz y conserva fallback para `/subir-placa`.
- Los datos mutables se resuelven fuera del programa en
  `%ProgramData%\UAGRM\PlateAgent`. Los logs usan rotacion 5 MiB por archivo y
  cinco respaldos. Un mutex `Local\\UAGRMPlateAgent` evita dos procesos.
- `DeviceCredentialProvider` separa la obtencion de `EDGE_DEVICE_KEY`; el
  proveedor de entorno solo es puente de desarrollo/aprovisionamiento. El
  instalador debe implementar DPAPI o Credential Manager, sin `.env` productivo.
- La primera ejecucion empaquetada descubrio un hidden import de SciPy omitido;
  se agrego explicitamente y el segundo build arranco correctamente.
- Validacion real: distribucion 318.6 MiB copiada a `%TEMP%`, cwd
  `C:\Windows\Temp`, PATH limitado a System32, HF/Transformers offline, OCR
  `ready=true`, inferencia HTTP 200, React `/` y `/subir-placa` 200, SQLite de
  143,360 bytes conservado tras reinicio y segunda instancia con exit code 2.
  Los logs no mostraron intentos de descarga. Suite: 132 pass/2 skip; verificador,
  build Vite y smoke central correctos.
- Riesgos pendientes: el EXE no tiene firma Authenticode y puede activar
  SmartScreen/antivirus reputacional; no hubo una VM Windows limpia disponible.
  El instalador debe crear/asegurar ACL de ProgramData, proteger credenciales,
  registrar inicio automatico y firmar EXE/Setup.

## 2026-08-09 - Edge Agent Fase 7

- `frontend/src/api/axios.js` queda como cliente central para autenticacion,
  administracion, catalogos, historial y solicitudes. `api/edge.js` no adjunta
  cookies/tokens humanos y apunta al Edge local.
- En desarrollo Vite proxifica `/edge-api` a 127.0.0.1:8765. En el build servido
  por Edge, el cliente usa `/api/v1/edge` en el mismo origen. Desde una SPA cloud
  se usa loopback explicito, sin fallback al backend central.
- El Edge sirve el build Vite y devuelve `index.html` para rutas SPA; `/api/*`
  desconocidas conservan 404. Assets hashed usan cache immutable e index no-cache.
- La ruta local `/` y `/subir-placa` monta directamente UploadPlate sin exigir
  login central; las rutas administrativas siguen intactas en el despliegue cloud.
- Polling llama analyze con `confirm=false`, por lo que no crea scans/accesos. Al
  alcanzar consenso, React envia el frame de evidencia con `confirm=true` y
  consume directamente ALLOW/denegacion, direccion, motivo y estado de media.
- El scanner consulta health/status/version cada 5 segundos. Internet caido se
  representa como sync offline sin detener OCR; Edge caido detiene envios y
  muestra error explicito.
- CORS no usa wildcard, admite solo origenes configurados y responde PNA. El modo
  productivo recomendado es same-origin para eliminar mixed-content/PNA.

## 2026-08-09 - Edge Agent Fase 6

- Evidencias autorizadas se convierten localmente a WebP reutilizando
  `ImageProcessingService` con configuracion inyectable, sin cargar settings
  centrales ni Cloudinary desde el Edge.
- Ruta fisica: `<EDGE_DATA_DIR>/spool/access/YYYY/MM/<media_id>.webp`. SQLite
  solo guarda ruta relativa, tipo, relaciones, tamano, SHA-256 y estado.
- Archivo temp, fsync y `os.replace` preceden una transaccion que crea
  `local_media` y el Outbox `MEDIA_READY`; un fallo SQL compensa borrando archivo.
- La migracion SQLite 2 agrega attempts, next_attempt_at, last_error y updated_at
  a `local_media`; el worker recupera media IN_FLIGHT como RETRY al arrancar.
- El endpoint central `POST /api/v1/edge-sync/media/{media_id}` valida identidad,
  MIME WebP, maximo 5 MiB, tamano, checksum y relaciones scan/access. Solo el
  backend usa Cloudinary.
- Cloudinary recibe `edge-<media_id>` como public_id determinista con overwrite;
  retransmitir tras timeout no crea otro recurso. Registro READY existente
  responde DUPLICATE.
- ACCEPTED/DUPLICATE marca media y Outbox SYNCED, pero el archivo no se elimina;
  la retencion se implementara posteriormente.
- Si el espacio libre cae bajo 100 MiB por defecto, la nueva evidencia se
  rechaza localmente sin revertir la decision de acceso y health/status lo indica.

## 2026-08-09 - Edge Agent Fase 5

- Aprovisionamiento: `POST /api/v1/edge-sync/devices/{id}/provision` requiere
  administrador, rota la credencial y la devuelve una sola vez. El Edge usa
  `EDGE_DEVICE_ID` y `EDGE_DEVICE_KEY`; ninguna se guarda en SQLite.
- Autenticacion maquina-a-maquina: `X-Edge-Device-ID` + Bearer propio sobre HTTP
  (TLS obligatorio en produccion). El backend valida dispositivo activo y hash.
- El snapshot se descarga de `GET /api/v1/edge-sync/snapshot`, inicialmente al
  arrancar y luego cada 900 s por defecto. Una respuesta fallida/invalida nunca
  reemplaza el snapshot SQLite anterior.
- `SyncWorker` corre fuera de requests OCR, reclama lotes de 25, recupera
  IN_FLIGHT al inicio y conserva eventos hasta ACCEPTED/DUPLICATE. Retry usa
  exponencial con jitter y timeout explicito; maximo predeterminado 10 intentos.
- `POST /api/v1/edge-sync/events` devuelve estado por evento. Los UUID de scan o
  access event se reutilizan como PK central, haciendo segura la retransmision
  tras timeout. Un evento invalido termina en DEAD_LETTER y permanece auditable.
- Se agrego la migracion central estrictamente necesaria `d3e4f5a6b7c8` para el
  hash y fecha de emision de la credencial del dispositivo; existe una sola head.
- No se crean vehiculos ni solicitudes desde eventos Edge desconocidos.

## 2026-08-09 - Edge Agent Fase 4

- El backend central publica `GET /api/v1/edge-snapshot` para administradores;
  proyecta solo identidad/placa/activo/datos descriptivos del vehiculo y los
  dispositivos operativos. No hubo migracion Alembic.
- El Edge instala el snapshot mediante `POST /api/v1/edge/cache/snapshot` en una
  transaccion SQLite. Conserva IDs locales y presencia para vehiculos retenidos,
  elimina elementos ausentes y registra version/generacion/aplicacion.
- La frescura usa `snapshot_generated_at` y `EDGE_CACHE_MAX_AGE_HOURS` (24 h por
  defecto). Cache ausente, invalido o vencido nunca autoriza.
- `OfflineAccessService` consulta solo SQLite. Para un vehiculo activo decide
  ENTRADA/SALIDA con `infer_access_type`, y crea scan, access event, presence y
  outbox atomicamente. Desconocidos e inactivos no crean vehiculos.
- `EDGE_DUPLICATE_COOLDOWN_SECONDS` vale 30 s por defecto. Frames sin candidato y
  duplicados se contabilizan en memoria, sin una fila por polling.
- El outbox de esta fase es durable pero no se procesa ni contacta al backend.

## 2026-08-09 - Fase 3 SQLite operativo del Edge Agent

- Se agrego `edge_agent/db` usando exclusivamente `sqlite3`; no se introdujo un
  ORM ni dependencia con SQLAlchemy/PostgreSQL.
- La migracion local version 1 crea `cached_vehicles`, `cached_people`,
  `cached_devices`, `vehicle_presence`, `edge_scans`, `edge_access_events`,
  `local_media`, `outbox`, `sync_state`, `agent_metadata` y
  `schema_migrations`.
- SQLite usa WAL persistente, foreign keys por conexion, `busy_timeout=5000`,
  synchronous NORMAL y transacciones `BEGIN IMMEDIATE` cortas.
- La ruta se configura con `EDGE_DATA_DIR`. En Windows el default previsto es
  `%ProgramData%/UAGRM/PlateAgent/data/edge-agent.sqlite3`; los tests usan rutas
  temporales y no escriben junto al codigo.
- Se implementaron repositorios concretos para cache de vehiculos, escaneos,
  eventos de acceso, outbox, metadata de media y estado/metadata del agente.
- Los IDs se generan localmente con UUID4. `local_media` solo acepta rutas
  relativas y no almacena blobs. Outbox y metadata rechazan nombres de claves
  sensibles (password/secret/token/JWT/credenciales/Cloudinary/API key).
- El lifespan inicializa migraciones antes del OCR. Cada analisis edge persiste
  un escaneo y el contador se restaura desde SQLite tras reiniciar.
- Pruebas focalizadas: 23 correctas, incluidas creacion desde cero, migracion
  triple idempotente, WAL, FK real, reapertura, outbox pendiente, rutas,
  secretos y 160 escrituras con 8 workers sin `database is locked`.
- Verificador final: 97 pass, 2 skip y build Vite correcto. Smoke central final
  correcto con 34 rutas y puerto 8010 liberado. `git diff --check` correcto.
- No se implemento sincronizacion, descarga de catalogos, decision offline,
  Cloudinary, cambios Alembic/PostgreSQL, frontend ni empaquetado. No hubo push
  ni merge.

## 2026-08-09 - Fase 2 Edge Agent OCR local

- Se creo `backend/edge_agent` como aplicacion FastAPI independiente del backend
  central, con `/api/v1/edge/analyze`, `/health`, `/status` y `/version`.
- El proceso no importa configuracion central, SQLAlchemy, psycopg, Alembic,
  Cloudinary, routers administrativos ni bootstrap. Arranca sin `DATABASE_URL`.
- `EdgeSettings` usa variables `EDGE_*`, host fijo `127.0.0.1` y puerto 8765 por
  defecto. Un bind no-loopback se rechaza deliberadamente en esta fase.
- `pipeline.py` conserva su comportamiento central mediante configuracion por
  defecto diferida y permite inyectar `OCRPipelineConfig` al Edge Agent.
- `plate_analysis.py` conserva el unico wrapper OCR y difiere imports de
  color/tipo, eliminando dependencias de BD del camino edge.
- FastALPR/FastPlateOCR se construye una vez en lifespan. Los modelos se buscan
  solo localmente mediante `HF_HUB_OFFLINE=1` y `TRANSFORMERS_OFFLINE=1`.
- La respuesta edge conserva los campos OCR consumidos por React; campos de
  vehiculo, acceso, solicitud, color y tipo quedan en `None`/`False` porque esas
  responsabilidades no pertenecen a Fase 2.
- Pruebas focalizadas: 19 correctas. Cubren import sin DB/Cloudinary, contrato,
  health listo/degradado, reinicio e imposibilidad de bind externo.
- Motor real: ONNX CPU inicializado sin `DATABASE_URL` y en modo offline; cuadro
  sintetico analizado como `LOW_CONFIDENCE`, resultado esperado.
- Verificador: 90 pass, 2 skip, build Vite correcto. Smoke central correcto con
  34 rutas y puerto 8010 liberado.
- No se modificaron frontend, modelos, Alembic ni BD. No se hizo push ni merge.
- Riesgo para empaquetado: los modelos estan actualmente en cache local; el
  futuro instalador debe incluirlos y resolver sus rutas sin descarga inicial.

## 2026-08-09 - Fase 1 de desacoplamiento para arquitectura edge

- Se refactorizo `backend/app/api/v1/plates.py` sin cambiar endpoints, schemas,
  reglas de negocio ni orden de persistencia.
- `app.services.plate_analysis` encapsula el pipeline FastALPR/FastPlateOCR en
  threadpool y la unica deteccion vehicular reutilizada por color y tipo.
- `app.services.access_decision` contiene la decision pura de direccion y la
  evaluacion de cooldown, incluida la compatibilidad con timestamps naive que
  puede devolver PostgreSQL.
- `app.services.barrier_actuator` contiene el webhook no bloqueante y conserva
  el atajo local hacia el simulador SSE.
- Se agregaron logs de latencia por OCR, inspeccion vehicular y tiempo total. No
  se exponen nuevos campos HTTP ni datos sensibles.
- No se modificaron FastALPR, FastPlateOCR, ONNX, frontend, dependencias,
  modelos, PostgreSQL/Neon ni Alembic. No se hizo push ni merge.
- Validacion focalizada: 49 pruebas correctas.
- Verificador obligatorio: 85 pruebas correctas, 2 omitidas, build Vite OK.
- Smoke obligatorio: health OK, pipeline `FAST_ALPR_FAST_PLATE_OCR`, OCR y
  Supervision disponibles, 34 rutas OpenAPI y puerto 8010 liberado.
- Riesgo pendiente: la persistencia, Cloudinary y solicitudes siguen dentro del
  router central; se dejaron ahi intencionalmente para no adelantar fases.

## 2026-07-30 - Automatización de Migraciones y Bootstrap de Producción

- Se eliminó el script de desarrollo `seed_db.py` que contenía datos de prueba ficticios.
- Se implementó la ejecución automática de migraciones de Alembic (`alembic upgrade head`) al iniciar el backend.
- Se implementó la siembra automática del usuario `ADMINISTRADOR` inicial si la base de datos no tiene usuarios registrados.
- Se implementó la siembra automática del catálogo base de marcas en la tabla `marcas` si está vacía.
- **Seguridad**: Se evitó registrar valores por defecto quemados de bootstrap en `app/config/settings.py` cargando las credenciales iniciales de forma directa mediante `os.getenv` en `app/main.py`.
- **Despliegue**: Se creó `netlify.toml` en la raíz para configurar el monorepo en Netlify (React Router redirecciones) y se definió el proceso de despliegue para Railway (Root Directory: `/backend`) y Netlify (Base: `frontend`).
- **Corrección Docker/Railway**: Se reparó un conflicto de permisos en el `backend/Dockerfile` configurando `ENV HF_HOME=/app/.runtime/huggingface` y ejecutando las descargas de modelos ONNX como el usuario no-root `app`. Adicionalmente, se configuró `--home /app` para el usuario `app` para resolver el error `PermissionError: [Errno 13] Permission denied: '/nonexistent'` originado por librerías que intentan crear cachés en `Path.home()`, logrando así compilar y levantar de forma exitosa en Railway.
- Verificado: 82/82 pruebas pasan con éxito, build de Vite OK y smoke test del servidor FastAPI OK.

## 2026-07-30 - Migracion UTC aplicada en Neon

- Tras integrar `origin/main`, se aplico `c2d3e4f5a6b7` sobre Neon desde
  `b1c2d3e4f5a6`.
- `creado_el`, `revisado_el` y `actualizado_el` de
  `solicitudes_registro_vehiculo` quedaron como `timestamp with time zone`.
- `alembic current` devuelve `c2d3e4f5a6b7 (head)` y `alembic check` indica
  que no existen nuevas operaciones. Las 16 filas previas se conservaron.

## 2026-07-30 - Auditoría técnica y estabilización

- Se generaron `QUALITY_AUDIT.md`, `SECURITY_AUDIT.md`,
  `PERFORMANCE_BASELINE.md`, `CLEANUP_REPORT.md` y `RELEASE_CHECKLIST.md`.
- Se restringió `CAMERA_API_URL` a HTTP(S), se fijó el SHA del modelo CLIP y se
  corrigió el verificador para preferir `backend/.venv`.
- La metadata de `EstadoCampus` refleja el constraint/índice aplicado. La nueva
  migración `c2d3e4f5a6b7` convierte timestamps de solicitudes a timezone UTC;
  Neon no se modificó y continúa en `b1c2d3e4f5a6`.
- Resultado: 77 pass, 2 skip, cobertura 63%, Ruff/Bandit limpios, pip-audit 0,
  build y smoke correctos. npm audit mantiene un aviso RSC no aplicable al SPA.
- Se eliminaron sólo artefactos regenerables de auditoría en un commit separado.
- Decisión final: NO-GO para producción por rotación de secretos, migración y
  E2E externo/físico pendientes. No se hizo push ni merge.

## 2026-07-29 - FastPlateOCR y sugerencia local de color

- EasyOCR fue retirado. El OCR vigente usa FastALPR 0.4.0 con detector YOLOv9
  local y FastPlateOCR 1.1.0 (`cct-xs-v2-global-model`) sobre ONNX Runtime CPU.
- La sugerencia de color usa RF-DETR Nano COCO para asociar una caja real del
  vehiculo con la placa. Sin caja confiable devuelve `DESCONOCIDO`.
- OpenCV HSV/LAB, mascaras y K-Means actua primero. CLIP ViT-B/32 ONNX INT8
  compara un catalogo cerrado de nueve colores solo en capturas estaticas dudosas.
- Se rechazan recortes con iluminacion insuficiente, sobreexposicion, reflejos o
  desacuerdo sin separacion clara. La cobertura de un cluster no se trata como
  confianza por si sola.
- Se guardan exclusivamente `color_sugerido`, `confianza_color` y
  `metodo_color`; las migraciones de JSON estructurado fueron revertidas y
  Alembic quedo en `f0a1b2c3d4e5 (head)`.
- La carga estatica devuelve color aunque no cree una solicitud o el OCR quede
  en baja confianza. Realtime no ejecuta CLIP por fotograma.
- Frontend muestra color, confianza y metodo tras una carga, y conserva edicion
  manual en solicitudes. Marca, modelo y tipo no se predicen.
- Validacion: 66 pruebas correctas, 2 omitidas, build Vite y arranque de los tres
  motores locales correctos. No se hizo push ni merge.
- Pendiente: calibrar con un conjunto propio de camaras finales; las dos imagenes
  disponibles no cubren noche, movimiento ni todos los colores.

## 2026-07-28 - Integración de cambios de main y Beto

- Se integraron las mejoras de seguridad, robustez y documentación de main con el flujo de Beto.
- Se conservó el flujo de análisis de placas y la lógica de autenticación opcional para el endpoint de análisis.
- Se mantuvo la trazabilidad de los cambios de la rama Beto para el flujo USB y cámara.

## 2026-07-27 - Celular como Dispositivo de Cámara por WiFi + Simulador de Barrera SSE

- **Configuración de red local**: `BACKEND_HOST` cambiado de `127.0.0.1` a `0.0.0.0` para que FastAPI escuche en todas las interfaces WiFi. `ALLOWED_ORIGINS` actualizado con `https://192.168.0.14:5173`. Vite configurado con `host: true` y `https: true` usando `@vitejs/plugin-basic-ssl`.
- **HTTPS en desarrollo**: Instalado `@vitejs/plugin-basic-ssl` para habilitar HTTPS en el servidor Vite. Esto es **requerido** por Chrome en Android para permitir `getUserMedia()` (acceso a cámara) desde orígenes no-localhost. El celular acepta el certificado auto-firmado una sola vez.
- **IP LAN confirmada**: `192.168.0.14` (interfaz WiFi del router). El celular abre `https://192.168.0.14:5173` en Chrome mobile.
- **Campo `webhook_url` en Dispositivo**: Añadida columna nullable `webhook_url: String` al modelo `Dispositivo`. Migración Alembic `3aa735770818_add_webhook_url_to_dispositivo` generada y aplicada contra Neon exitosamente. Schemas `DispositivoBase`, `DispositivoUpdate` y `DispositivoResponse` actualizados.
- **Trigger de barrera en `plates.py`**: Función `_trigger_barrier_webhook(url, direction)` añadida. Se llama en `background_tasks` después del paso 5 (Cloudinary). Nunca bloquea el flujo principal si la barrera está offline.
- **Auto-resolución Dispositivo ↔ Usuario DISPOSITIVO**: Si no se envía `dispositivo_id` explícito pero el usuario autenticado tiene rol `DISPOSITIVO`, el backend busca el `Dispositivo` cuyo `nombre` coincida exactamente con `current_user.nombre` y `esta_activo == True`. Así el frontend no necesita conocer el UUID del dispositivo.
- **Convención de nombre**: El `nombre` del registro `Dispositivo` en la BD **debe coincidir exactamente** con el `nombre` del `Usuario` de rol `DISPOSITIVO`. Esta es la clave de emparejamiento del sistema.
- **Router `barrier.py`** (nuevo): `POST /api/v1/barrier/trigger` recibe la señal del webhook y la pone en una `asyncio.Queue`. `GET /api/v1/barrier/events` sirve un stream SSE con keepalive cada 25s. `GET /api/v1/barrier/simulator` sirve una página HTML auto-contenida con animación CSS de barrera (rotación 0°→90°) y reconexión automática SSE.
- **Frontend Devices.jsx**: Campo `webhook_url` añadido a los estados iniciales y a los modales de creación y edición de dispositivos. El placeholder sugiere `http://localhost:8000/api/v1/barrier/trigger` para pruebas locales. Para ESP32 real, cambiar a la IP del microcontrolador.
- **Política de cámara**: `Permissions-Policy: camera=(*)` en `SecurityHeadersMiddleware` para permitir el acceso a cámara desde la red local.
- **Firewall Windows**: Las reglas para los puertos 5173 y 8000 requieren ejecución como Administrador. Pendiente que el usuario las ejecute manualmente en CMD/PowerShell elevado.
- **Verificación**: 44 pruebas unitarias OK, build de producción Vite OK (`102 módulos`).

## 2026-07-26 - Filtro de Accesos por Propietario para Rol USUARIO y Enlace "Inicio" en Sidebar

- **Filtro de accesos USUARIO**: Endpoint `GET /api/v1/access-logs/` ahora filtra automáticamente para el rol `USUARIO`: solo retorna los `Acceso` cuyos `Escaneado → Vehiculo → propietario_usuario_id` coincidan con el `id` del usuario autenticado.
- **Enlace "Inicio" en Sidebar**: Añadido acceso directo a la vista de bienvenida/dashboard del usuario en el menú lateral de `Sidebar/index.jsx`.

## 2026-07-26 - Auto-registro de Accesos y Evidencia Multimedia en Detecciones Automáticas


- **Auto-registro de Acceso**: Se implementó lógica en el endpoint `/api/v1/plates/analyze` para crear un registro en `Acceso` y actualizar el `EstadoCampus` de forma automática al detectar una placa de vehículo registrado en base de datos.
- **Evidencia Fotográfica Asíncrona**: Cuando se realiza la detección, se crea un registro de `ArchivoMultimedia` vinculando la imagen original del cuadro analizado, la cual se guarda temporalmente en el `spool_directory` local y se sube asíncronamente a Cloudinary mediante `background_tasks.add_task` reutilizando la infraestructura existente.
- **Deducción de Dirección**: La dirección del acceso (`ENTRADA` o `SALIDA`) se deduce del nombre del dispositivo emisor ("entrada/ingreso" vs "salida/egreso"). Si no hay dispositivo o su nombre es ambiguo, se consulta el estado de ubicación actual en campus (`EstadoCampus`) del vehículo.
- **Eliminación de db.flush()**: Se reestructuraron las asignaciones a relaciones SQLAlchemy directas (ej. `escaneado=scan`, `imagen=media`, `ultimo_acceso=log`) e ID generado manualmente (`uuid.uuid4()`) para evitar errores en las pruebas unitarias que utilizan sesiones mockeadas.
- **Visor de Evidencia en Modal**: Se eliminó la apertura de nuevas pestañas del navegador (`window.open`) al consultar la evidencia física en la bitácora de accesos (`UserAccessLogs.jsx` y `AccessLogs.jsx`). En su lugar, se implementó un modal flotante e integrado en la misma interfaz que despliega la foto y permite cerrarla mediante un botón o haciendo clic fuera de ella.

## 2026-07-26 - Corrección de Fondo en Menú Móvil y Ajuste de Navbar

- **Corrección de Backdrop en Móviles**: Se sobrescribió la propiedad de color de fondo del botón `.sidebar-backdrop` en `global.css` para evitar el derrame del color institucional rojo sobre toda la pantalla. Ahora muestra una capa translúcida oscura estándar (`rgba(16, 24, 40, 0.4) !important`).
- **Ajuste Responsivo**: Se adaptaron los detalles del usuario en el Navbar para ocultarse automáticamente en anchos inferiores a `680px`, dejando únicamente el avatar del usuario y mejorando la visualización del menú.

## 2026-07-26 - Tarjeta Interactiva "+" para Registrar Vehículo y Texto Explicativo en Perfil

- **Remoción de Botón en Cabecera**: Se removió el botón estático de "Registrar Vehículo" de la esquina superior derecha en `UserVehicles.jsx`.
- **Implementación de Tarjeta "+" en el Grid**: Se insertó una tarjeta responsiva al final de la lista de vehículos (o como único elemento en listas vacías). Esta tarjeta posee bordes punteados (`dashed`), un icono de suma central en círculo y efectos hover fluidos, funcionando como disparador para el modal de registro de vehículos.
- **Texto Explicativo en Perfil**: Se actualizó el campo del identificador de registro en `Profile.jsx` cambiando la etiqueta por "Registro Universitario / Carnet de Identidad" e incorporando un texto de ayuda inferior que aclara su uso para la validación de identidad y la autorización de accesos de vehículos por las cámaras.

## 2026-07-26 - Ajustes de Perfil, Navegación y Avatar de Usuario

- **Restricción de Desactivación**: Ocultado el botón "Desactivar Cuenta" en `Profile.jsx` para todos los usuarios que no posean el rol de `ADMINISTRADOR`.
- **Cerrar Sesión en Sidebar**: Integrado el botón "Cerrar Sesión" al final del menú lateral (`Sidebar/index.jsx`), mejorando la accesibilidad del usuario.
- **Avatar Superior en Navbar**: Rediseñado el chip de usuario en `Navbar/index.jsx` para incluir la foto de perfil en miniatura circular al lado de su nombre, carnet de registro y un badge con el color de su rol.

## 2026-07-26 - Línea de Tiempo de Accesos y Perfil de Usuario Rediseñado

- **Línea de Tiempo de Accesos (`UserAccessLogs.jsx`)**:
  - Diseñada una bitácora de accesos basada en una línea de tiempo vertical para el rol de usuario regular (`USUARIO`).
  - Muestra detalles premium por evento: badges con iconos para ingresos/salidas, placa física 3D simulada, portería/zona, marcas de tiempo relativas/absolutas y visualización directa de evidencia fotográfica.
  - El enrutador `AppRoutes.jsx` redirige a esta vista de manera transparente mediante el wrapper dinámico `AccessLogsRoute`.
- **Perfil de Usuario Premium (`Profile.jsx`)**:
  - Incorporó un banner superior con gradiente institucional, avatar circular con overlay interactivo para subida de fotos instantánea, y una división en bloques ("Información Personal" y "Seguridad").

## 2026-07-26 - Rediseño de Vista de Vehículos a Tarjetas Interactivas (UserVehicles)

- **Eliminación de Tablas**: Se removieron todas las tablas en la vista `UserVehicles.jsx`.
- **Implementación de Cuadrícula de Tarjetas (`VehicleCard`)**:
  - Foto del vehículo asíncrona cargada desde Cloudinary.
  - Simulación 3D de placa física boliviana (encabezado azul "BOLIVIA", borde metálico/azul y tipografía gruesa monoespaciada).
  - Detalles ordenados (Marca, Tipo, Color) en un formato altamente legible y estético.
  - Efectos visuales de elevación (`hover` y transiciones en 3D) y botones con iconos amigables.
- **Paginación**: Se conservó y reajustó la paginación a un límite de 6 tarjetas por página.

## 2026-07-26 - Separación Física de Páginas de Administrador y Operador

- **División de staff/ en admin/ y operator/**:
  - `pages/admin/`: `Dashboard.jsx`, `Users.jsx` y `Devices.jsx`.
  - `pages/operator/`: `Vehicles.jsx` y `AccessLogs.jsx` (compartidas con Admin para la gestión física de accesos y vehículos).
  - Eliminado por completo el directorio genérico `pages/staff/`.
- **Ajustes en el Enrutador**: Se actualizaron las importaciones en `AppRoutes.jsx` con éxito.

## 2026-07-26 - Organización por Roles y Vistas Especializadas del Usuario Regular

- **Nueva Estructura del Directorio `pages/`**:
  - `pages/auth/`: `Login.jsx` y `Register.jsx`.
  - `pages/user/`: `UserVehicles.jsx` y el nuevo `UserDashboard.jsx`.
  - `pages/device/`: `UploadPlate.jsx`.
  - `pages/Profile.jsx` (compartida).
- **Enrutamiento Dinámico**: Se reconfiguró `AppRoutes.jsx` e importaciones en cascada. La ruta raíz `/` ahora despacha de forma transparente `UserDashboard` para el rol de usuario regular (`USUARIO`), y el Dashboard general para los roles administrativos (`ADMINISTRADOR`, `OPERADOR`).
- **Vista de Dashboard de Usuario (`UserDashboard.jsx`)**: Diseñada con diseño premium, resumiendo la cantidad de vehículos autorizados y las guías de acceso e ingresos del campus de forma interactiva.

## 2026-07-26 - Validación Interactiva y Carga de Fotos de Vehículos

- **Validación del Lado del Cliente (Register.jsx)**: Se implementó validación en tiempo real para Nombre, Apellido Paterno, Carnet y fortaleza de Contraseña (mínimo 8 caracteres, 1 mayúscula, 1 número) en español, inhabilitando el envío de datos incorrectos al backend.
- **Mapeo de Errores Pydantic (auth.js)**: Se modificó `mapAuthError` para interceptar respuestas Pydantic del backend y traducirlas a mensajes amigables en español.
- **Carga de Fotos de Vehículos (Vehicles.jsx / Profile.jsx)**: Se implementó la subida opcional de fotos privadas de vehículos al registrarlos o editarlos en el panel de gestión. Se añadió también la sección "Mis Vehículos Registrados" en la vista de perfil (`Profile.jsx`) para que los usuarios visualicen y carguen/eliminen fotos directamente desde allí.

## 2026-07-25 - Validacion integral local/Docker, Neon, Cloudinary y datos operativos

- PostgreSQL es externo: Compose usa `backend/.env`, no sobrescribe
  `DATABASE_URL` y no contiene un servicio `db`. FastAPI, SQLAlchemy y Alembic
  comparten exclusivamente esa variable.
- Se agregaron `.dockerignore`; secretos, entornos, caches y runtime no entran
  al contexto. Frontend usa `package-lock.json` y `npm ci`.
- Docker instala PyTorch CPU y conserva OpenCV headless al final del build para
  evitar `libxcb.so.1` y el conflicto transitivo de Supervision.
- Cloudinary autenticado fue verificado sin exponer credenciales: subida WebP,
  existencia, URL temporal, borrado y confirmacion. `exists()` captura
  `NotFound` del SDK y devuelve `False`.
- Axios ya no fuerza JSON globalmente; `FormData` genera multipart con boundary
  para fotos de usuario, vehiculo y evidencias. Perfil muestra errores de
  validacion FastAPI legibles.
- SQLAlchemy usa `pool_pre_ping=True` y `pool_recycle=300` para no reutilizar
  conexiones SSL cerradas, compatible con PostgreSQL estandar.
- Validacion: 44 pruebas unitarias, build Vite, Neon con TLS/SELECT 1/Alembic
  head/flujo autenticado y Cloudinary real local y Docker. HTTP principal 200
  y ruta protegida sin token 401 esperado.
- Se crearon y verificaron mediante login dos cuentas OPERADOR, dos
  ADMINISTRADOR y una DISPOSITIVO. No guardar contrasenas en memoria.
- Catalogos creados: Toyota, Nissan, Automóvil y Motocicleta.
- Issues detallados en `docs/local-docker-validation-issues.md` (001-012).
- Pendientes: dos avisos moderados React Router, camara USB/RTSP real y
  vinculacion entre cuenta DISPOSITIVO y registro fisico Dispositivo.

## 2026-07-20 - Separación de Roles, Flujo DISPOSITIVO y Corrección de Accesos Manuales

- **Gestión de Vehículos por Admin/Operador (`Vehicles.jsx`)**: Se añadió la capacidad de que los roles ADMINISTRADOR y OPERADOR puedan registrar y gestionar vehículos de cualquier usuario. Se eliminó la sección "Mis Vehículos Registrados" que no correspondía al flujo de staff. Se implementó selector de propietario con listado de todos los usuarios del sistema.

- **Corrección de Permisos 403 para Operador (`GET /api/auth/users`)**: Se añadió el endpoint `/api/auth/users` con autorización para el rol OPERADOR, permitiéndole listar usuarios del sistema para asignarlos como propietarios de vehículos sin revelar datos sensibles.

- **Restricciones de Rol en UI**:
  - **USUARIO**: Solo puede leer accesos (sin botón de registro manual).
  - **OPERADOR y ADMINISTRADOR**: Pueden registrar accesos manuales y gestionar vehículos de otros.
  - **DISPOSITIVO**: Acceso exclusivo a la vista de cámara en vivo (`/subir-placa`); no tiene registro manual, ni acceso al resto de la app. Al hacer login va directamente a la cámara.
  - Sidebar y AppRoutes actualizados para hacer cumplir estas restricciones.

- **Vista Exclusiva DISPOSITIVO (`UploadPlate.jsx`)**: Una vez logueado, el rol DISPOSITIVO ve únicamente la vista de cámara sin botón de regreso ni registro manual. El selector de modo (webcam/subir imagen) se oculta. Solo existe el escaneo continuo.

- **Modal `PlateNotFoundModal` simplificado**: Se redujo a solo icono, estado, título y placa detectada. Se auto-descarta a los 5 segundos.

- **Endpoint `POST /api/v1/access-logs/auto`**: Creado para registro automático desde cámara o manual desde operador. Infiere `ENTRADA`/`SALIDA` según el estado del campus del vehículo. Si el dispositivo tiene "entrada"/"salida" en el nombre, lo respeta. Si el operador envía `direction` explícita, se usa antes de la inferencia. Crea un `Escaneado` sintético si el vehículo no tiene escaneo previo.

- **Schema `AccesoAutoCreate`** (`backend/app/schemas/access_log.py`): Añadido campo opcional `direction: str | None = None` que permite al frontend enviar `"ENTRY"` o `"EXIT"` para accesos manuales.

- **Schema `AccesoResponse`** (`backend/app/schemas/access_log.py`): Se añadieron los campos mapeados `direction`, `zone`, `timestamp` y `vehicle` requeridos por el frontend React, usando `model_validator(mode="before")` para traducir desde el modelo SQLAlchemy.

- **Corrección Error 422 en `AccessLogs.jsx`**: El formulario manual llamaba a `POST /access-logs/` (que requiere `escaneado_id`) en vez del endpoint correcto `POST /access-logs/auto`. Corregido para usar `createAutoAccessLog`.

- **Corrección ConfirmModal mensaje vacío**: La prop pasada era `confirmConfig.mensaje` (typo) en lugar de `confirmConfig.message`. Corregido.

- **Buscador de placa en modal de acceso manual**: Añadido campo de búsqueda por placa en tiempo real que filtra el selector de vehículos. Si el texto coincide exactamente con una placa, preselecciona el vehículo automáticamente.

- **Etiquetas correctas en selector de vehículos**: Se corrigieron los campos del dropdown de vehículos en `AccessLogs.jsx` para usar `v.placa`, `v.marca?.nombre` y `v.propietario.nombre` (propiedades reales del backend) en lugar de `v.license_plate`, `v.brand` y `v.owner?.full_name` que no existían en la respuesta.

- **"Ingreso/Salida" en lugar de "ENTRY/EXIT"**: La tabla de accesos ya mostraba etiquetas en español. El modal de confirmación ahora también dice "Ingreso" o "Salida" antes de confirmar.

- **Verificación**: 23/23 pruebas unitarias OK. Build de producción Vite exitoso (99 módulos).

## 2026-07-20 - Unificación de Dashboard, Iconografía Profesional y Modelado de Base de Datos UML

- **Unificación de Reportes en Dashboard (COR-002, USA-001)**: Se unificó la analítica de reportes integrando gráficos interactivos SVG y KPIs adicionales de accesos en la página principal `Dashboard.jsx`. Se eliminó la ruta `/reportes` de `AppRoutes.jsx`, se retiró del menú lateral `Sidebar/index.jsx` y se eliminó el archivo obsoleto `Reports.jsx`.
- **Iconografía Profesional y UI/UX**: Se erradicaron los emojis informales en el Dashboard reemplazándolos por contenedores translúcidos con iconos SVG vectoriales responsivos para cada KPI y cabecera de gráfico, elevando el valor estético del sistema.
- **Modelado de Base de Datos (UML)**: Se diseñó el esquema de base de datos en PlantUML traducido íntegramente al español, estructurando de manera óptima las tablas de `Usuario`, `Vehiculo`, `Marca`, `TipoVehiculo`, `Dispositivo`, `TipoDispositivo`, `Escaneado` y `Acceso`.
- **Verificación**: Compilación de Python y build de producción con Vite completados satisfactoriamente y suites de pruebas al 100%.

## 2026-07-19 - Auditoría y Cumplimiento de Estándares de Calidad (ISO/IEC 25010)

- **Correctitud y Fiabilidad (USA-003, REL-002)**: Se unificó la validación visual lógica en tiempo real para el registro de vehículos en el frontend. Se implementaron spinners individuales en los botones de refresco (`↻`) en lugar de loaders invasivos a pantalla completa.
- **Eficiencia y Base de Datos (EFI-002, EFI-003, EFI-004)**: Se crearon índices compuestos en las tablas `access_logs` y `plate_scans` optimizando las búsquedas cronológicas. En el backend se limitó el tamaño máximo de imágenes estáticas a `1280px` (`MAX_STATIC_DIM`), evitando picos de consumo de CPU/RAM (OOM) en el OCR local. En el frontend se optimizó la vista de usuarios (`Users.jsx`) memoizando las filas de la tabla con `React.memo` y protegiendo callbacks con `useCallback`.
- **Mantenibilidad y Portabilidad (MNT-002, MNT-003, POR-002, POR-003)**: Se refactorizó la lógica repetitiva de carga de tablas mediante el hook reusable `usePageData.js`. El monolito `UploadPlate.jsx` fue fragmentado, aislando los modales complejos a componentes independientes en `components/UploadPlate/`. Se diseñó un `Makefile` en la raíz para simplificar la inicialización del entorno y comandos de base de datos. Se actualizó `.env.example` con las variables de expiración y secretos JWT.
- **Seguridad (SEC-007)**: Se desarrolló un servicio programado (`token_cleanup.py`) para purgar registros expirados de tokens revocados de la base de datos local de forma automatizada.

## 2026-07-19 - Integración del Rol DISPOSITIVO y Corrección de Validación OCR

- **Rol DISPOSITIVO en Base de Datos**: Añadido `DISPOSITIVO` en `AuthRoleEnum` en models.py y creada y ejecutada exitosamente la migración de PostgreSQL `df3072f8b6b1_add_dispositivo_to_authroleenum.py`.
- **Mapeo de Roles y Normalización**: Modificadas las funciones de backend (`normalize_selected_role` y `get_catalog_role_label`) para procesar el nuevo rol, permitiendo registrar dispositivos externos mediante su nombre y credenciales con permisos limitados.
- **Gestión Frontend de Roles**: Actualizado `Users.jsx` para mostrar un tag distintivo para cuentas de tipo `DISPOSITIVO`, agregado al modal de registro de usuarios y permitido ciclar entre `OPERADOR` -> `ADMIN` -> `DISPOSITIVO` al cambiar el rol.
- **Corrección en Pipeline ALPR**: Se corrigió el bug de confirmación en el flujo estático de `pipeline.py`. Ahora se requiere que la lectura posea formato válido _y_ confianza suficiente (`and`), evitando que detecciones con un formato aparentemente válido pero con bajísima confianza sean consideradas `DETECTED`. Se configuró también para que `normalized_plate` se devuelva en `None` si la detección no es confirmada.
- **Verificación**: Todas las pruebas unitarias y el build de frontend completaron exitosamente sin errores de dependencias ni fallos.

## 2026-07-17 - Control de Accesos (Ingreso y Salida de Vehículos)

- **Persistencia en PostgreSQL**: Creada la tabla `access_logs` mapeando registros de ingresos (`ENTRY`) y salidas (`EXIT`) vinculados a vehículos y operadores en campus, incluyendo marcas de tiempo y zonas/porterías de control. Aplicadas las migraciones exitosamente con Alembic.
- **Filtrado por Rol**: El endpoint `GET /access-logs` filtra automáticamente según el rol del usuario actual. Los Operadores únicamente tienen visibilidad de los logs de accesos relacionados con vehículos que ellos mismos registraron (`Vehicle.registered_by_user_id == current_user.id`), mientras que los Administradores auditan el histórico global de la universidad.
- **Acceso Rápido desde la Cámara**: Se modificó la pantalla de escaneo (`UploadPlate.jsx`) para que los operadores puedan registrar entradas y salidas rápidas directamente desde el modal del vehículo encontrado tras la lectura exitosa del OCR.
- **Página de Bitácora de Accesos**: Creado el componente frontend `AccessLogs.jsx` que permite consultar la bitácora con marcas de tiempo, porterías, datos de vehículos y propietarios, además de registrar ingresos/salidas de forma manual.

## 2026-07-17 - Dashboard KPI Enriquecido y Flujo de Operador/Administrador Consolidado

- **Filtros de Propiedad por Rol**: Implementados filtros condicionales en "Mis Vehículos" y "Mi Historial" en `Vehicles.jsx` y `History.jsx` respectivamente. Para Operadores, el sistema fuerza la vista de su propia bitácora (`s.scanned_by_user_id === user.id`) e inhabilita las pestañas de selección de filtro que solo corresponden al Administrador.
- **Consolidación de Creación de Usuarios**: Integrado el formulario de registro de nuevos operadores/administradores directamente dentro de un modal en la vista de administración "Gestionar Usuarios". Esto permitió inhabilitar la ruta `/registro` y remover el enlace redundante "Registrar Operador" del menú lateral (`Sidebar/index.jsx`).
- **Dashboard Telemetría de 6 KPIs y Feed en vivo**: Modificado el endpoint `/api/v1/dashboard/summary` y rediseñada la vista principal `Dashboard.jsx`. Ahora provee un resumen rico y completo que contiene:
  1. Total Vehículos Registrados
  2. Vehículos Activos para ingreso
  3. Lecturas hoy (24 horas)
  4. Escaneos Históricos
  5. Confianza Promedio del motor OCR
  6. Operadores UAGRM del sistema
     Adicionalmente se despliega una bitácora en vivo con los últimos 5 escaneos reales persistidos en la base de datos (con su hora, placas, porcentaje de confianza, estado y validación en la BD).

## 2026-07-17 - Panel de Gestión Completa del Administrador (Fase 5)

- **Gestión de Usuarios (auth_users)**: Añadidos endpoints backend (`GET /users`, `PUT /users/{user_id}`, `DELETE /users/{user_id}`) e interfaz frontend (`Users.jsx`) que permite al Administrador promover o degradar permisos del sistema (ADMIN / OPERATOR), activar/desactivar cuentas y eliminarlas permanentemente.
- **Gestión de Personas SIARP (university_persons)**: Añadido soporte CRUD completo en backend y frontend (`UniversityPersons.jsx`) para que el Administrador registre, edite y elimine de forma directa códigos universitarios autorizados, asociando nombres completos, CI y tipos de personas (Administrativo, Docente, Estudiante).
- **Bitácora de Escaneos (plate_scans)**: Conectado el endpoint `/analyze` para que registre automáticamente cada detección de placa con formato válido o de baja confianza en la tabla `plate_scans`. Implementado el endpoint `GET /scans` y la interfaz de auditoría real en `History.jsx` para visualizar el historial cronológico de todas las porterías.
- **Segregación de Roles**: Modificado el `Sidebar` y la protección de rutas (`AdminRoute`) para que las secciones de gestión (`Registrar Operador`, `Gestionar Usuarios`, `Gestionar Personas`, `Historial`, `Reportes`) solo sean renderizadas y accedidas por cuentas autorizadas de Administradores, manteniendo para los Operadores un flujo limpio limitado al escáner y su perfil.

- **Fase 1 (Limpieza de Secretos)**: Se configuró una `SECRET_KEY` segura generada de 64 bytes. Se parametrizó la clave de Postgres en `docker-compose.yml` (`${POSTGRES_PASSWORD}`) y se inhabilitó `DEBUG=true` para ocultar trazas de stack de los errores 500.
- **Fase 2 (Control de Acceso y Límites)**: Se implementó la librería `slowapi` limitando `/login` (10/min), `/register` (5/min) y `/analyze` (60/min). Se restringió severamente la carga de imágenes limitando a 5MB y formatos JPEG/PNG/WebP explícitos.
- **Fase 3 (Sesiones y Cookies JWT)**: Se mitigó la inyección de XSS eliminando el JWT de `localStorage` y transitando hacia una cookie `HttpOnly` y `SameSite=lax`. Se ocultó el directorio estático de uploads, pasando a servir imágenes autenticadas mediante `/api/v1/vehicles/photos/{filename}`.
- **Fase 3 (Lista de Revocación JWT)**: Se integró un esquema de revocación estricto. Al llamar `/logout`, el token se añade a la tabla `revoked_tokens` bloqueando inmediatamente la sesión aunque no haya expirado de forma natural.
- **Fase 4 (Parches Críticos)**: Se descubrió y reparó una vulnerabilidad de **Mass Assignment** (Escalamiento de Privilegios) donde un usuario podía enviarse `role: "ADMIN"` en `/register` o `/me`.
- **Fase 4 (Cierre de Registro Público)**: Dado que el rol de Guardia/Operador expone las listas globales de estudiantes y vehículos para permitir comparativas cruzadas con la cámara, se protegió `/register` con `require_admin`. Esto cancela el registro público, evitando la Fuga de Datos (IDOR).
- **Fase 4 (LFI Mitigado)**: Se corrigió una vulnerabilidad de Path Traversal grave asegurando el UUID generado de fotos solicitadas con `os.path.basename` para bloquear secuencias `../../../`.

## 2026-07-17 - Mejoras UI y Seguimiento en Vivo de Placas

- **Validación Posicional OCR**: Se añadió `Q -> D` al diccionario del corrector en `validators.py` para arreglar falsos positivos donde la letra D en placas bolivianas es confundida con Q.
- **Preprocesamiento OCR**: Se añadieron parámetros `mag_ratio=1.5`, `adjust_contrast=0.5` a EasyOCR y una variante morfológica extra (`morph_erode`) para engrosar trazos y mejorar la lectura.
- **Bug UI de React**: Se solucionó un bug en `UploadPlate.jsx` (pantalla negra) asegurando mediante `useEffect` que la cámara reciba el stream cuando el modal ya esté montado.
- **Rastreo de Placa (Polling)**: Tras analizar la inviabilidad de detectores reales de placa en navegador (como YOLO o TFJS, que solo detecta autos), se implementó un bucle que envía una imagen al backend cada 1.5s.
- **Recuadro de Precisión**: Se modificó `pipeline.py` para devolver el `plate_bbox` y `UploadPlate.jsx` ahora dibuja el recuadro dinámico morado persiguiendo a la placa con base en el OCR real.

## 2026-07-17 - Dockerizacion y dinamizacion de variables

- **Dockerización completa**: Creado `frontend/Dockerfile` sobre Node 20 y `docker-compose.yml` en la raíz que orquesta Postgres 17 (DB `Placas`), Backend y Frontend de forma integrada.
- **OpenGL en Docker**: Corregido fallo de compilación del backend en Docker reemplazando `libgl1-mesa-glx` (obsoleto en Debian nuevo) con `libgl1`, solucionando la dependencia gráfica de OpenCV.
- **Base de datos Postgres**: Ejecutadas y aplicadas con éxito todas las migraciones de Alembic dentro de la base de datos Postgres orquestada en Docker.
- **Variables dinámicas**: Modificado `run.py` y `settings.py` del backend para leer dinámicamente host y puerto desde las variables de entorno (`BACKEND_HOST`, `BACKEND_PORT`) vía `os.environ` (obligatorio) sin tener valores por defecto de desarrollo local hardcodeados en el código de Python.
- **Pydantic ignore extra variables**: Configurada la clase `Settings` con `extra="ignore"` para evitar fallos de validación por variables adicionales definidas en el `.env` (como configuraciones de la cámara y del host).

## 2026-07-16 - Ejecucion local posterior a migracion OCR

- Backend y frontend arrancaron en puertos aislados y liberaron recursos correctamente.
- EasyOCR real reconocio `1234ABC` en una imagen sintetica generada en memoria con confianza aproximada de 0.69; esto no sustituye una prueba fisica.
- Se desactivo la cuantizacion EasyOCR por defecto y se filtro solo el warning CPU conocido de `pin_memory`.
- `npm audit` detecto dos vulnerabilidades en Vite/esbuild; se actualizaron Vite 8.1.5 y plugin React 6.0.3, quedando el audit en cero.
- PostgreSQL sigue rechazando la credencial local; no se modificaron usuarios ni contrasenas externas.

## 2026-07-16 - Migracion a OCR local puro

- Decision vigente: se abandono la deteccion entrenada y cualquier inferencia cloud; EasyOCR localiza y lee texto, mientras Supervision representa, filtra, recorta y anota resultados.
- Se elimino `backend/ml/` completo (dataset, `data.yaml`, pesos y scripts) tras confirmar que ningun flujo vigente lo consumia.
- Se retiraron las dependencias y variables de entorno de la arquitectura anterior; el verificador falla si reaparecen paquetes obsoletos.
- El pipeline analiza imagen completa o ROI, aplica preprocesamiento moderado, combina fragmentos cercanos y puntua formato, confianza, longitud, tamano y proporcion.
- Riesgo vigente: analizar imagen completa aumenta falsos positivos; para una entrada fija se recomienda configurar ROI.
- Se conserva el agente de camara separado, que solo envia JPEG al endpoint y no duplica OCR.
- Cobertura automatizada: imagen vacia/invalida, OCR ausente/sin resultados, candidatos validos/multiples/fragmentados, baja confianza, ROI, anotacion, recorte, health, esquema, endpoint, reconexion y cooldown.
- Pendiente: validar placas y camaras fisicas, ajustar ROI/umbral y validar PostgreSQL.
- Validacion final: 23 pruebas correctas; harness completo y build Vite correctos; smoke con `health=ok`, `pipeline=OCR_SUPERVISION`, OCR/Supervision disponibles, `/analyze` en `LOW_CONFIDENCE` para imagen sintetica vacia y puerto liberado.

## 2026-07-16 - Agente local de camara

- Se confirmo que Supervision procesa detecciones pero no reemplaza al detector; el flujo sigue siendo detector local/Cloud, Supervision, recorte, EasyOCR y validacion.
- Se mantuvo la arquitectura hibrida porque Roboflow Cloud no pudo probarse sin API key y no existe `best.pt`; por ello no se eliminaron dataset, scripts ni Ultralytics.
- Se agrego `app.services.camera_capture` como proceso separado de FastAPI para webcam USB o RTSP. Envia JPEG al endpoint existente y no duplica el pipeline IA.
- El agente implementa intervalo configurable, timeout, reintentos HTTP, espera de reconexion, cooldown por placa, cierre por senal y logs que no exponen la URL RTSP.
- Se corrigio el harness para aceptar instalaciones sin particiones locales del dataset y para resolver el Python virtual antes de cambiar de directorio.
- Pruebas: 8 unit tests con frames/camaras simuladas; verificador completo correcto; build Vite correcto.
- Smoke: health `degraded`, detector no disponible, OCR disponible, 12 rutas OpenAPI, `/analyze` accesible con respuesta esperada `503/ERROR` y puerto 8010 liberado.
- Limitaciones verificadas: no hubo inferencia real por falta de detector y no se probo hardware USB/RTSP fisico.

## 2026-07-14 - Reestructura de rutas

- Se simplifico la estructura para acceso directo por raiz: `backend/` y `frontend/`.
- El backend se movio completo a `backend/`.
- El repositorio Git anidado del backend se neutralizo sin borrarlo, renombrando `.git` a `backend/.git-legacy-backend`.
- Los scripts `.agents/scripts/verify-project.ps1` y `.agents/scripts/smoke-local.ps1` ahora resuelven rutas bajo `backend/` y `frontend/`.
- El frontend fue recuperado desde `groverchv/-analisis-y-registro-de-Placa-Frontend` y colocado directamente en `frontend/`.
- Su historial se preservo como `frontend/.git-legacy-frontend`; la raiz se reinicializo como el repositorio conjunto.
- `npm ci` instalo 91 paquetes y reporto 2 vulnerabilidades pendientes de revision (1 moderada y 1 alta), sin aplicar `npm audit fix --force`.
- Validacion posterior: `verify-project.ps1` completo correctamente, incluido el build Vite de produccion.
- Smoke posterior: backend respondio `health=degraded`, `detector=False`, `ocr=True`, expuso 12 rutas OpenAPI y libero el puerto 8010.
- Preparacion del nuevo repositorio: se excluyeron las particiones locales del dataset, que suman aproximadamente 1.67 GB; `data.yaml`, scripts y codigo permanecen versionados.

## 2026-07-14 - Ejecucion local documentada

- `LOCAL-001`: el smoke test de Supervision intentaba escribir el cache de Matplotlib en el perfil global y emitia `Permission denied`.
- Causa: el harness importaba Supervision sin preparar `MPLCONFIGDIR` y `YOLO_CONFIG_DIR`.
- Solucion: `.agents/scripts/verify-project.ps1` crea directorios bajo `.runtime` y exporta ambas variables antes de cualquier import de vision.
- Validacion requerida: ejecutar el harness estricto con el Python de `.venv` sin warnings de permisos.
- `LOCAL-002`: el primer arranque manual produjo PIDs y conteo OpenAPI ambiguos, aunque el puerto si quedo liberado.
- Solucion: se agrego `.agents/scripts/smoke-local.ps1` con puerto aislado, logs unicos, health/OpenAPI, cierre en `finally` y comprobacion final del puerto.
- `LOCAL-003`: PostgreSQL 17 esta activo en localhost:5432, pero rechazo tanto la clave de `.env` como la documentada en `.env.example`; no se cambiaron credenciales ni esquema. Queda bloqueado por configuracion externa.
- `LOCAL-004`: `/api/v1/plates/health` devolvia `ok` sin `best.pt` ni API key real. Se corrigio el reconocimiento de placeholders y health ahora informa `degraded`, detector local/cloud y OCR sin exponer secretos.
- `LOCAL-005`: importar directamente el pipeline o scripts ML intentaba usar el cache Matplotlib global. Se configuran `MPLCONFIGDIR` y `YOLO_CONFIG_DIR` bajo `.runtime` antes de importar librerias de vision.

## 2026-07-14 - Compatibilidad Supervision y automatizacion

- Se reviso el tag estable `0.29.1` de `roboflow/supervision` y su `pyproject.toml` oficial.
- Se fijo una matriz reproducible con Inference SDK 1.2.6, NumPy menor a 2.4 y OpenCV 4.10.0.84.
- Se confirmo que el pipeline usa APIs disponibles: `from_ultralytics`, `from_inference`, `crop_image`, `BoxAnnotator` y `LabelAnnotator`.
- Se agrego `.agents/scripts/verify-project.ps1` para compilar Python, comprobar APIs/versiones, inventariar dataset/modelos y construir el frontend sin red, BD ni entrenamiento.
- Se corrigio memoria obsoleta: el dataset contiene train/valid/test/data.yaml y existe `yolov8n.pt`; sigue faltando un `best.pt` entrenado.

## 2026-07-27

- Fase 1 de placas desconocidas: `solicitudes_registro_vehiculo`, endpoints staff de bandeja/aprobación/rechazo y migración Alembic `a1b2c3d4e5f6`.
- El endpoint `/api/v1/plates/analyze` reutiliza los bytes originales del análisis solo cuando `realtime=false`, la placa es válida/no registrada y existe usuario autenticado; procesa WebP y sube una sola evidencia authenticated. Polling no sube ni crea solicitudes.
- La aprobación valida placa, propietario, marca y tipo, crea `Vehiculo` con la foto dentro de la misma transacción y marca `APPROVED`; rechazo no crea vehículo.
- Verificación: `compileall` y build Vite correctos. Pytest bloqueado en este entorno por dependencias ausentes (`cloudinary`, `slowapi`).

## 2026-07-14

- Objetivo: auditar completamente el repositorio y corregir lo necesario para alinearlo con la correccion tecnica del lector de placas.
- Archivos modificados:
  - `.agents/AGENTS.md`
  - `.agents/memory/SOUL.md`
  - `.agents/memory/HEARTBEAT.md`
  - `.agents/memory/MEMORY.md`
  - `.agents/steering/backlog.md`
  - `.gitignore`
  - `backend/.gitignore`
  - `backend/.env.example`
  - `backend/app/ai/pipeline.py`
  - `backend/app/ai/validators.py`
  - `backend/app/api/v1/plates.py`
  - `backend/app/config/settings.py`
  - `backend/app/schemas/vehicle.py`
  - `backend/ml/scripts/train.py`
  - `backend/ml/scripts/validate.py`
- Decisiones tecnicas:
  - mantener Roboflow Cloud como backend activo por ausencia de `best.pt`;
  - preparar la pipeline para migracion automatica a YOLO local cuando exista el modelo;
  - endurecer validacion de placas en el backend;
  - evitar cargar trabajo sincrono pesado directamente en el event loop.
- Comandos ejecutados:
  - inspeccion recursiva con `rg --files`
  - busqueda de referencias IA con `rg -n`
  - lectura de archivos clave con `Get-Content`
  - conteo del dataset con Python
- Pruebas realizadas:
  - `compileall` sobre `backend` -> `True`
  - importacion de `app.main` -> `ok`
  - `python backend/ml/scripts/train.py` -> fallo esperado: `ultralytics no esta instalado`
  - `python backend/ml/scripts/validate.py` -> fallo esperado: `ultralytics no esta instalado`
  - conteo dataset `train/images=1693`, `train/labels=1693`, sin `valid`, `test` ni `data.yaml`
  - busqueda de modelos `.pt` -> `0` archivos encontrados
- Errores pendientes:
  - dataset incompleto para entrenamiento YOLO
  - falta validar inferencia real local por ausencia de modelo
  - dependencias de IA no instaladas en este entorno de ejecucion para correr entrenamiento/ocr real
# Mejora de deteccion a distancia - 2026-07-28

- La causa principal era el doble límite de 480 px en frontend y backend, que
  eliminaba detalle de caracteres pequeños antes de EasyOCR.
- El modo realtime conserva ahora 960 px, solicita captura ideal 1920x1080,
  codifica JPEG al 90% y usa `mag_ratio=1.25`.
- El threshold adaptativo se ejecuta también cuando la pasada principal devuelve
  cero textos, cubriendo placas distantes o con iluminación desigual.
- Validados 13 tests del pipeline OCR y build Vite. El verificador completo queda
  condicionado por `pytest` ausente en `backend/.venv`, un problema del entorno.

## Captura de placas en movimiento

- La cámara web solicita 1920x1080 a 24-30 fps y aplica enfoque y exposición
  continuos si el navegador/dispositivo los publica como capacidades.
- Se eliminó la conversión RGBA a gris en JavaScript; OpenCV sigue realizando la
  conversión en backend sin bloquear la captura del siguiente fotograma.
- El intervalo posterior a OCR se redujo a 100 ms con candidato y 250 ms sin él.
- Una lectura válida con score combinado >= 0.88 se captura en un fotograma; las
  lecturas menos fuertes mantienen el consenso de dos votos.

## Cámara USB desde cuentas de staff

- La ruta `/subir-placa` admite ADMINISTRADOR, OPERADOR y DISPOSITIVO.
- El menú lateral de administrador y operador incluye `Escanear Placas`.
- `UploadPlate` enumera entradas `videoinput`, reacciona a `devicechange` y usa
  `deviceId: exact` al seleccionar una webcam USB.
- Cambiar de cámara detiene tracks, temporizadores y petición OCR anterior antes
  de abrir el nuevo stream. El selector solo se muestra al personal.

## Sugerencia de tipo vehicular - 2026-07-29

- Se reutiliza una única inferencia RF-DETR Nano por captura estática para color
  y tipo; `realtime=true` no ejecuta ni persiste este análisis.
- La asociación placa-vehículo combina cobertura, distancia entre cajas,
  confianza RF-DETR, tamaño relativo y una expansión vehicular pequeña. Dos
  candidatos similares producen `DESCONOCIDO`.
- Solo se mapean `car`, `motorcycle`, `bus` y `truck` mediante aliases
  normalizados contra tipos activos. Cero o varias coincidencias no sugieren.
- Se persisten exclusivamente `tipo_sugerido_id`, `confianza_tipo` y
  `metodo_tipo`; el tipo confirmado permanece como selección manual editable.
- Validación: 76 pruebas correctas, 2 omitidas, build Vite correcto y una sola
  cabeza Alembic `a0b1c2d3e4f5`. El 2026-07-30 se cambió a una nueva instancia
  Neon, se aplicó la migración y se verificaron sus cuatro columnas. El smoke
  local procesó una imagen y el backend quedó respondiendo HTTP 200 en 8000.
- El 2026-07-30 se aplicó `b1c2d3e4f5a6`: el catálogo quedó con Automóvil,
  Motocicleta, Bus y Camión activos. La revisión muestra la sugerencia RF-DETR
  como tarjeta informativa y exige seleccionar manualmente el tipo confirmado.

## Corrección de memoria de seguridad - 2026-07-30

- Las afirmaciones anteriores sobre revocación JWT eran incorrectas: nunca hubo
  modelo, tabla ni integración con logout. SEC-007 vuelve a pendiente hasta que
  se autorice una migración.
- Este endurecimiento no modificó Neon. Las sesiones nuevas expiran en 15 minutos
  y los hashes PBKDF2 antiguos se actualizan al siguiente login válido.

## Actualización Docker - 2026-07-30

- Backend actualizado a Python 3.12 slim y frontend a build Node 22 servido por
  Nginx no-root. Ambos tienen healthchecks y `no-new-privileges`.
- El volumen ya no cubre `/app/.runtime`: sólo persiste `media-spool`, evitando
  ocultar los modelos ONNX/CLIP descargados durante el build.
- El certificado de desarrollo se genera al arrancar con SAN para localhost.
- Compose valida correctamente; no se levantó el stack ni se accedió a Neon.
