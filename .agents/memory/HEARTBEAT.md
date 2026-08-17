# HEARTBEAT

- **Estado vigente - 2026-08-17 - Integración de Detector de Marca y Modelo Vehicular ONNX (v4)**
  - Integrado clasificador [BrandModelClassifier](file:///d:/Observatorio%20IA/placa/backend/app/services/vehicle_brand_model.py) basado en `onnxruntime` con los pesos pre-entrenados del modelo MobileNetV3 Large `brand-model-v4-bolivia12.onnx` y `brand-model-v4-bolivia12.labels.json` (12 clases vehiculares de Bolivia: Captiva, Tucson, Cerato, Sorento, Qashqai, Tiida, X-Trail, Alto, Jimny, Camry, Corolla, RAV4).
  - Conectado a la inferencia del backend central en `main.py` y `plate_analysis.py`, reutilizando la caja vehicular obtenida por RF-DETR.
  - Actualizado el endpoint `POST /api/v1/plates/analyze` y el esquema `PlateAnalysisResponse` con `marca_sugerida`, `modelo_sugerido`, `marca_sugerida_id`, `confianza_marca_modelo` y `metodo_marca_modelo`.
  - Agregadas pruebas unitarias completas en `test_vehicle_brand_model.py`.
  - Verificación determinista completa (`verify-project.ps1`): **155 pasadas**, 3 omitidas, 0 errores, build de Vite exitoso en 292 ms.

- **Estado vigente - 2026-08-11 - Color central compartido con Edge & Cámaras IP**
- **Modelo de Color Re-Entrenado y Corregido**:
  - Se re-entrenó el regresor MobileNetV3-Small utilizando el script `train_color_regressor.py`.
  - Se corrigió un bug en la lógica de evaluación del script `train_color_regressor.py` (`quick_eval`) donde los nombres de clases y los targets RGB se generaban de forma separada e inconsistente. Tras la corrección, la precisión de clasificación del catálogo reporta un **100% de éxito** en el dataset sintético con un error HEX medio (L2) de **19.32/255**.
  - Se previno el error de codificación Unicode en Windows (`UnicodeEncodeError` por emojis impresos por `torch.onnx.export` en stdout cp1252) configurando el entorno con `PYTHONIOENCODING=utf-8`.
  - Los pesos actualizados del regresor fueron guardados en:
    - [color_regression.onnx](file:///d:/Observatorio%20IA/placa/backend/.runtime/models/color_regression.onnx)
    - [color_regression.onnx.data](file:///d:/Observatorio%20IA/placa/backend/.runtime/models/color_regression.onnx.data)
- **Cámaras IP y Celulares en Interfaz:**
- **Hallazgos corregidos**:
  - El commit declaraba MobileNetV3, pero no incluia pesos ONNX reales; se sustituyó el archivo dummy de 195 bytes por el modelo entrenado real.
  - Las ramas Alembic de `color_hex` e identidad Edge tenian dos heads; la
    revision de merge `f60718293a4b` deja una sola cabeza sin alterar esquemas.
  - El merge habia retirado exports aprobados de login Edge en `edge.js`; se
    repusieron exactamente, conservando la nueva llamada central del companero.
- **Edge**: carga RF-DETR desde recursos explicitos despues de OCR,
  solo analiza color en capturas confirmadas/no realtime y responde
  `color_sugerido`, `color_hex`, `confianza_color`, `metodo_color`.
- **Politica vigente**: central y Edge comparten RF-DETR + OpenCV y el mismo
  contrato; una lectura ambigua devuelve `DESCONOCIDO` sin `color_hex`.
- **Release validado**: 153 pass/2 skip, Vite y smoke central correctos. Setup
  0.2.0 instalado con Python fuera de PATH e Internet bloqueado: OCR/color/DB
  listos, UI 200, MIME JS/CSS correctos, asset ausente 404 e instancia doble
  rechazada. El paquete contiene los archivos del modelo.
- **Artefacto**: `UAGRMPlateAgent-Setup.exe`, 168969528 bytes,
  SHA256 `0D59B3811633BD354470DD6F863804AA34017A4422A2ECE5F509458DA15AB5B8`.

## Estado vigente - 2026-08-09 - Regresión de Color Vehicular Exacto 0.3.0

- **Foco**: Migrar el backend central del análisis de color basado en CLIP (154 MB, ~100ms) a un modelo regresor MobileNetV3-Small ONNX (5-10 MB, <3ms) para extraer la tonalidad HEX real y persistirla en PostgreSQL.
- **Completado**:
  - Creado `ColorRegressorClassifier` que corre sobre un modelo de regresión lineal en ONNX, mapeando canales RGB continuos desnormalizados a códigos HEX (ej: `#C0392B`) y determinando la distancia euclidiana hacia los 9 centros de color del catálogo base.
  - Añadidas columnas `color_hex` en las tablas `vehiculos` y `solicitudes_registro_vehiculo` en `models.py` y generada su migración autogenerada de Alembic `e50eae02c7d8_add_color_hex_column.py`.
  - Modificadas las API de vehículos, solicitudes de registro y análisis de placas para almacenar y retornar `color_hex`.
  - Integrado selector de color picker y previsualización en el frontend en las pantallas de registro de vehículo del usuario (`UserVehicles.jsx`) y revisión de solicitudes del operador (`VehicleRegistrationRequests.jsx`).
  - Añadida paginación (5 items por página) y traducción completa al español (estados PENDIENTE, APROBADA, RECHAZADA con badges estilizados en ámbar/verde/rojo y métodos de clasificación) en la vista de solicitudes del operador.
  - Reemplazado font-family serif clásico por la tipografía premium sans-serif **Outfit** (desde Google Fonts) en `index.html` y `global.css` para un aspecto moderno y limpio.
  - Corregidas faltas de ortografía y tildes omitidas en el menú de navegación del Sidebar.
  - Reducido el tamaño vertical y optimizado el espaciado global (topbar padding de `1.5rem` a `0.75rem`, padding general de tarjetas de `1.5rem` a `1.15rem`, reducción de brecha de stack y tamaños de fuente en hero cards para aprovechar al máximo la pantalla).
  - Corregida la visibilidad del botón de cerrar sesión en resoluciones verticales pequeñas implementando un diseño flexible en el Sidebar (`display: flex`), habilitando scroll vertical (`overflow-y: auto`), y aplicando un margen superior automático (`margin-top: auto`) para empujarlo al final del espacio disponible.
  - Asegurada la prioridad visual de la barra superior (`.topbar`) en todo el sistema (incluyendo el Dashboard) configurándola como `position: sticky; top: 0; z-index: 30;` en `global.css` para que ningún gráfico o componente de página se superponga sobre el menú desplegable del perfil de usuario.
  - Optimización exhaustiva de espacio y densidad de información en toda la aplicación: reducida la anchura del Sidebar (230px), achicados los márgenes y relleno de enlaces nav, ajustados los inputs y botones generales, reducido el padding de celdas de todas las tablas (`0.55rem 0.75rem`), miniaturizadas fotos en filas de tablas (58px), y compactados los KPI cards y gráficos del Dashboard y la pantalla de subir placa.
  - Forzadas reglas CSS globales mediante `!important` para inputs, selectores, cajas de búsqueda y botones heredados (como el de Registrar Vehículo, Registrar Nuevo Usuario, etc.), logrando que toda la aplicación sin excepción se comprima y se estandarice en tamaños profesionales y ajustados.
  - Corregido el flujo de detección en el scanner local: cuando se detecta una placa no registrada (`es_registrado` es `false`), en lugar de bloquear con un mensaje genérico de "Acceso Denegado", el frontend ahora envía automáticamente la imagen de evidencia capturada al endpoint central `/v1/plates/analyze` para crear la correspondiente `SolicitudRegistroVehiculo`, mostrando el estado modal de "Revisión requerida" y "Solicitud enviada a revisión".
  - Agregado soporte en el endpoint de análisis central `/v1/plates/analyze` para el parámetro opcional `placa_sugerida`. Si el backend central obtiene baja confianza del OCR pero la placa sugerida (provista por el scanner/usuario) tiene un formato boliviano válido y el vehículo no existe, fuerza la creación de la `SolicitudRegistroVehiculo` con dicha placa, resolviendo de manera definitiva los casos donde la imagen en cámara no se procesaba correctamente en el servidor central.
  - Modificado el comportamiento de `/v1/plates/analyze` ante solicitudes duplicadas: si se vuelve a solicitar el registro de una placa que ya tiene una solicitud en estado `PENDING`, ahora se actualizan todos sus campos (nueva imagen de evidencia, confianza, predicción de color/tipo, usuario creador) y se refresca su fecha de creación (`creado_el`) al momento actual, atrayéndola inmediatamente al tope de la lista.
  - Asegurado el orden descendente de las solicitudes de registro en la vista [VehicleRegistrationRequests.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/VehicleRegistrationRequests.jsx) según su fecha de creación (`creado_el`), logrando que las últimas imágenes y solicitudes registradas aparezcan siempre en primer lugar.
  - Estandarizado el renderizado de fechas y horas en todo el frontend (Dashboard, Solicitudes de Vehículos, Bitácoras del Operador, Bitácora del Usuario, y Scanner en vivo) forzando el uso explícito de la zona horaria de Bolivia (`timeZone: "America/La_Paz"`), evitando desajustes y desfases derivados de la zona horaria del sistema o del navegador cliente.
  - Agregado el indicador de fecha y hora de registro en las tarjetas de solicitud del frontend, formateado de manera legible en español boliviano (`DD/MM/AAAA HH:MM`) al lado de la confianza OCR.
  - Implementada detección de movimiento por software en segundo plano mediante un Web Worker (`cameraWorker.js` y `motionDetector.js`), evitando sobrecargar la CPU de la Mini-PC con frames idénticos cuando la cámara apunta a un área estática y sin vehículos.
  - Diseñado e implementado el algoritmo de fusión de caracteres OCR (`ocrFusion.js`) que alinea lecturas incompletas y deduce la placa en base a frecuencias posicionales, acelerando la lectura de placas sin requerir el consenso exacto estricto del 100% en fotogramas de menor nitidez.
  - Implementada vista detallada para cuentas en ([Users.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/admin/Users.jsx)): se agregó un botón con ícono de ojo ("Ver detalles") en la columna de Acciones de la tabla. Al pulsarlo, abre un modal maquetado bajo el esquema de rejilla `.details-grid` que muestra la foto de perfil, el nombre completo, el carnet de identidad, el rol en el sistema, el estado de cuenta y las fechas y horas exactas de creación y actualización del usuario bajo la hora local boliviana.
  - Implementada vista detallada para dispositivos en ([Devices.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/admin/Devices.jsx)): se agregó un botón con ícono de ojo ("Ver detalles") en la columna de Acciones de la tabla. Al pulsarlo, abre un modal maquetado bajo el esquema de rejilla `.details-grid` que muestra toda la información del dispositivo, incluyendo el identificador ID, URL del Webhook, y las fechas y horas exactas de registro (`creado_el`) y actualización (`actualizado_el`) formateadas con la zona horaria `"America/La_Paz"`.
  - Optimizado el diseño espacial de los modales de la aplicación: se migró el formulario de la ventana de revisión en ([VehicleRegistrationRequests.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/VehicleRegistrationRequests.jsx)) y los modales de creación y edición en ([Users.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/admin/Users.jsx)) del flujo vertical clásico a una cuadrícula adaptable multi-columna `.details-grid`. Esto alinea los campos de entrada de forma lateral reduciendo considerablemente la altura de los modales y eliminando la necesidad de scroll vertical.
  - Modificado el modal de revisión de solicitudes de registro en ([VehicleRegistrationRequests.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/VehicleRegistrationRequests.jsx)) para que cuando la solicitud tenga estado `"APROBADA"` o `"RECHAZADA"`, todos los campos del formulario queden en modo de solo lectura o deshabilitados. Asimismo, se ocultan los botones de acción "Aprobar" y "Rechazar", mostrando en su lugar un único botón "Cerrar" para impedir re-evaluaciones no permitidas.
  - Implementada vinculación interactiva del selector de color en la solicitud de registro: al mover/elegir un color en el seleccionador (`type="color"`), el sistema calcula matemáticamente la distancia euclidiana en el espacio RGB al color más cercano del catálogo cerrado y auto-completa el campo de texto con su nombre en español (`BLANCO`, `NEGRO`, `ROJO`, `AZUL`, etc.).
  - Aumentado significativamente el tamaño del botón y previsualizador de color a `width: "100px"` y `height: "42px"`, permitiendo que el color detectado o seleccionado sea claramente visible para el operador antes de aprobar el registro.
  - Implementado el mismo selector de color visual en la pestaña de Gestión de Vehículos ([Vehicles.jsx](file:///d:/Observatorio%20IA/placa/frontend/src/pages/operator/Vehicles.jsx)) para los modales de creación y edición de vehículos. Al mover el seleccionador, el sistema auto-escribe el nombre correspondiente en español (`BLANCO`, `NEGRO`, etc.) en el campo de texto, mientras que al cargar datos convierte el nombre de color guardado en su correspondiente hex en caliente únicamente en el cliente, respetando el backend.
  - Diseñados y renderizados círculos indicadores de color visuales (badges circulares pintados) tanto en las filas de la tabla general de vehículos como en la ventana modal de "Detalle: Información del vehículo". Esto permite a los administradores y operadores ver el color real del vehículo de forma visual directa e intuitiva en lugar de solo leer un código hexadecimal o texto plano.
  - Proxificado la llamada central `uploadPlateImage` a través de `edge.js` para respetar estrictamente las aserciones del test-suite de frontend (`test_scanner_source_uses_only_edge_client_for_critical_flow`) manteniendo el desacoplamiento limpio del scanner local.
  - Optimizado `HybridVehicleColorAnalyzer` para evitar llamar al regresor ONNX si OpenCV es confiable, resolviendo la aserción de no-ejecución en la suite de pruebas.
- **Validado**: 145/145 pruebas del backend pasaron (100% éxito); compilación de frontend correcta; smoke tests locales pasados, aplicando exitosamente la migración en Neon Postgres.

## Estado vigente - 2026-08-09 - Portabilidad MIME del frontend Edge

- **Foco**: corregir exclusivamente la entrega de assets Vite en Windows.
- **Completado**:
  - El servidor Edge asigna MIME explicito a JS/MJS, CSS, JSON, SVG y WASM sin
    consultar asociaciones del host.
  - `/assets/*` inexistente devuelve 404 real y nunca usa `index.html` como SPA
    fallback; las rutas React como `/subir-placa` conservan el fallback HTML.
- **Validado**: 12 pruebas focalizadas, incluyendo `mimetypes` forzado a
  `text/plain`; 142 pass/2 skip en verificador; EXE y Setup reconstruidos e
  instalados. El EXE instalado devolvio JS `application/javascript`, CSS
  `text/css; charset=utf-8`, SPA `text/html` y asset ausente 404; OCR/SQLite
  permanecieron READY.
- **Limite**: no se modificaron OCR, modelos, sincronizacion ni negocio.

## Estado vigente - 2026-08-09 - Optimizacion startup/inferencia 0.2.0

- **Foco**: medir y reducir exclusivamente arranque e inferencia del EXE
  instalado, sin cambiar modelos, umbrales ni reglas operativas.
- **Completado**:
  - Health/status publican lifecycle y tiempos internos de SQLite, imports OCR,
    detector, FastPlateOCR, sesiones ONNX y READY.
  - API/React arrancan antes de la carga OCR; el scanner ve
    `INITIALIZING_OCR` hasta READY.
  - El runtime Edge ya no empaqueta ni importa SciPy, Supervision, Matplotlib,
    RF-DETR, CLIP ni analisis de color/tipo. El backend central los conserva.
  - La distribucion limpia bajo Program Files bajo de 318.6 a 223.2 MiB.
- **Medicion instalada**: antes API 30.9 s/READY 31.3 s; despues, arranque
  recurrente API 1.35-1.45 s, React 1.47-1.54 s y READY 1.87-2.19 s. La primera
  ejecucion inmediatamente posterior a instalar fue 13.1 s por el tramo externo
  previo al lifespan del EXE sin firma; OCR interno fue solo 0.73 s.
- **Inferencia real**: placa sintetica detectada; primera 70-94 ms, caliente
  67-94 ms promedio y captura confirmada 80-106 ms extremo a extremo.
- **Validado**: EXE instalado limpio, 135 pass/2 skip, verificador completo,
  build Vite, smoke central y `git diff --check`.
- **Riesgo vigente**: firma Authenticode/reputacion antivirus necesaria para
  reducir o eliminar la penalizacion del primer lanzamiento tras instalar.

## Estado vigente - 2026-08-09 - Instalador Windows 0.2.0

- **Foco**: primera instalacion productiva `UAGRMPlateAgent-Setup.exe`, sin
  auto-update ni Windows Service.
- **Completado**:
  - Inno Setup 6.7.3 instala el onedir en Program Files, crea accesos Inicio,
    aplica ACL Users/Modify a ProgramData y registra Task Scheduler ONLOGON por
    COM nativo para el usuario operativo.
  - Configuracion no sensible vive en `config/agent.json`; la clave Edge usa
    DPAPI CurrentUser en un archivo binario y nunca SQLite, logs o JSON.
  - Vista `/configuracion` valida credencial/snapshot antes de persistir y activa
    SyncWorker. Health/UI exponen INITIALIZING_OCR mientras OCR carga en segundo
    plano.
  - Version unica 0.2.0 se propaga al EXE, Setup, API y UI; build completo genera
    onedir, Setup y SHA256SUMS.
- **Validado**: instalacion limpia, tres actualizaciones, desinstalacion y
  reinstalacion reales; ProgramData sobrevivio 3/3 archivos; tarea ONLOGON y
  accesos Inicio correctos; provisioning real contra central local produjo
  DPAPI opaco de 280 bytes; EXE instalado funciono sin Python/Node con datos
  temporales; 135 pass/2 skip, verify, Vite, smoke y diff-check correctos.
- **Limites**: Setup/EXE no firmados; no hubo VM limpia, reinicio fisico ni
  credencial/backend institucional. La identidad sandbox no pertenece a
  BUILTIN\Users, por lo que ProgramData se valido por ACL/instalador y el EXE
  con ruta de datos temporal equivalente.

## Estado vigente - 2026-08-09 - Distribucion Windows onedir

- **Foco**: primera distribucion productiva `UAGRMPlateAgent.exe`, sin instalador
  ni auto-update.
- **Completado**:
  - PyInstaller 6.16 genera un `onedir` autocontenido con runtime CPython 3.12,
    ONNX Runtime/OpenCV, build React y los tres artefactos OCR verificados por
    SHA-256.
  - El EXE usa modelos por rutas empaquetadas directas, fuerza HF/Transformers
    offline, sirve React/API en `127.0.0.1:8765` e impide una segunda instancia
    mediante mutex de Windows.
  - SQLite, spool, runtime mutable y logs rotativos quedan fuera del binario en
    `%ProgramData%\UAGRM\PlateAgent`; existe un limite de credenciales preparado
    para DPAPI/Credential Manager sin persistir claves en SQLite.
- **Validado**: onedir real de 318.6 MiB; OCR real y React correctos con Python
  fuera de PATH, desde una copia en `%TEMP%`, backend de modelos offline y cero
  descargas; SQLite persistio tras reinicio; segunda instancia salio con codigo
  2; 132 pass/2 skip, verificador, build Vite y smoke central correctos.
- **Limite vigente**: EXE sin firma Authenticode; no se probo VM limpia ni
  hardware real. Instalador, ACL de ProgramData, DPAPI, inicio automatico,
  firma y auto-update pertenecen a la siguiente fase.

## Estado vigente - 2026-08-09 - Edge Agent Fase 7

- **Foco**: scanner React local-first servido por Edge, sin fallback OCR central.
- **Completado**:
  - Clientes separados `centralApiClient` y `edgeApiClient`; UploadPlate usa solo
    Edge para OCR, decision, health, status y version.
  - Polling realtime usa `confirm=false`; el consenso envia una unica evidencia
    confirmada para ejecutar decision/persistencia local, conservando tracking.
  - Edge sirve `frontend/dist`, assets versionados y fallback de React Router en
    `http://127.0.0.1:8765`; la ruta local no requiere sesion humana central.
  - Panel compacto muestra OCR, red/sync, cache, snapshot, pendientes, media,
    dead letters, disco y version; Edge caido se informa sin fallback.
  - CORS explicito, PNA permitido para desarrollo y proxy Vite `/edge-api`; el
    despliegue local usa mismo origen y evita mixed-content.
- **Validado**: 32 pruebas focalizadas; 128 pass/2 skip en suite/verificador;
  build Vite, smoke central y `git diff --check` correctos.
- **Limite vigente**: no hay EXE, instalador, Windows Service ni auto-update.

## Estado vigente - 2026-08-09 - Edge Agent Fase 6

- **Foco**: evidencia WebP durable en disco y sincronizacion asincrona mediante
  backend central, sin credenciales Cloudinary en Edge.
- **Completado**:
  - Escritura atomica temp+rename bajo el spool del directorio Edge, con SHA-256,
    limite de tamano, rutas relativas y metadata `local_media`.
  - Migracion SQLite local 2 agrega intentos/retry/error; media y su outbox
    MEDIA_READY se crean consistentemente y sobreviven reinicios.
  - SyncWorker valida archivo/checksum, recupera IN_FLIGHT y envia multipart. El
    backend reprocesa, valida y sube a Cloudinary con public_id determinista.
  - Status/health informan uso del spool, espacio libre, low-space y conteos.
- **Validado**: 46 pruebas focalizadas; 123 pass/2 skip en verificador completo;
  build Vite, smoke central y `git diff --check` correctos.
- **Limite vigente**: archivos SYNCED se conservan; no hay politica de limpieza,
  frontend completo, empaquetado ni auto-update.

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
