# MEMORY

## 2026-07-28 — 4R Review completa + Fixes de seguridad y robustez + Cambios de Beto

- **SDD Init**: Inicializado con engram (capture_prompt: false para artefactos automáticos). Strict TDD activado. Testing capabilities detectadas.
- **4R Review**: Ejecutadas las 4R completas (Risk, Resilience, Readability, Reliability) vía gentle-ai review sobre el último commit (26 archivos, 1372 líneas). Estado: **approved**.
- **SEC-011 (CRITICAL)**: Se descubrió que `storage.js` guardaba el token JWT en localStorage (regresión de una migración previa a cookie httpOnly). Corregido: ahora solo guarda el usuario. El `Authorization: Bearer` header se eliminó de axios — la cookie `session_token` httpOnly con `withCredentials: true` es suficiente.
- **SEC-012 (WARNING)**: `propietario_nombre` se devolvía en `/api/v1/plates/analyze` incluso para llamadas no autenticadas. Corregido: ahora solo se incluye si `current_user is not None`.
- **SEC-013 (CRITICAL)**: El bloque `except Exception: await db.rollback()` en `plates.py` tragaba cualquier error de BD y devolvía una respuesta exitosa con datos incompletos. Corregido: ahora loggea con `exc_info=True` y retorna HTTP 500.
- **SEC-014 (WARNING)**: El cooldown de accesos duplicados usaba SELECT-then-INSERT sin lock atómico (TOCTOU). Corregido: agregado `.with_for_update()` en la consulta del último acceso.
- **ROB-001 (CRITICAL)**: Si `camera_source` fallaba, el bucle de captura se detenía permanentemente. Corregido: se implementó reconexión automática infinita con backoff exponencial.
- **ROB-002 (WARNING)**: Las credenciales RTSP (`rtsp://user:pass@host`) se filtraban al frontend en logs o labels. Corregido: se creó un helper que enmascara las credenciales y solo expone el host/puerto.
- **ROB-003 (WARNING)**: Las peticiones concurrentes en el frontend encolaban múltiples peticiones `/analyze`. Corregido: se introdujo una bandera `isProcessing` en `UploadPlate.jsx` y un `AbortController` para abortar peticiones previas.
- **Integración de cambios de main y Beto**:
  - Se integraron las mejoras de seguridad, robustez y documentación de main con el flujo de Beto.
  - Se conservó el flujo de análisis de placas y la lógica de autenticación opcional para el endpoint de análisis.
  - Se mantuvo la trazabilidad de los cambios de la rama Beto para el flujo USB y cámara.
  - Se añadió soporte para cámaras USB y conexión del celular por USB.
- **Backlog actualizado**: 7 nuevos items (SEC-011 a SEC-014, ROB-001 a ROB-003) marcados como done.
- **Verificación**: Suite de pruebas aprobada.

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

## 2026-07-29 - Migracion EasyOCR -> PaddleOCR (PP-OCRv4)

- Motor OCR cambiado de EasyOCR+PyTorch a PaddleOCR+PaddlePaddle CPU-only.
- Beneficio: imagen Docker reducida ~1 GB al eliminar torch/torchvision.
- PP-OCRv4 es mas rapido y preciso en caracteres alfanumericos compactos (placas).
- Archivos modificados: requirements.txt, paths.py, main.py, settings.py, pipeline.py, test_ocr_pipeline.py, supervision.md.
- Cambio clave en pipeline: PaddleOCR devuelve poligonos de 4 puntos [[x1,y1]...] en lugar de la lista plana de EasyOCR. Se implemento _detections_from_paddle() que convierte a xyxy tomando min/max de cada coordenada.
- _run_ocr() ahora llama ocr_reader.ocr(image, cls=True) y filtra por allowlist (A-Z0-9-) y umbral de confianza antes de devolver resultados. PaddleOCR no tiene parametro allowlist nativo.
- OCR_LANGUAGES y OCR_QUANTIZE eliminados de settings.py (EasyOCR-especificos).
- Tests: MockOCRReader.ocr() y SequencedOCRReader.ocr() reemplazan readtext(). ocr_item() ahora devuelve [pts, (text, conf)].
- Verificacion: 47/47 tests OK, build Vite OK. Debug log corregido (r[1][0]/r[1][1]).
- PENDIENTE: pip install paddlepaddle paddleocr en venv y actualizar Dockerfile.

## 2026-07-29 - Integracion de Hugging Face CLIP Zero-Shot

- Se integro el clasificador de imagenes Zero-Shot basado en el modelo 'openai/clip-vit-base-patch32' de Hugging Face.
- Este clasificador se ejecuta de manera local y en segundo plano solo para analisis estaticos (no-realtime) y si la placa no existe en la base de datos (registro de solicitudes de revision).
- Sugiere dinamicamente marca, tipo y color del vehiculo comparando la imagen con los catalogos activos ('Marca' y 'TipoVehiculo') de la base de datos sin necesidad de entrenamiento previo.
- La respuesta JSON del endpoint /api/v1/plates/analyze ahora incluye 'marca_sugerida', 'tipo_sugerido' y 'color_sugerido'.
- Tests unitarios en 'test_ocr_pipeline.py' y 'test_plates_api.py' actualizados y aprobados.
- Verificacion: 48 tests OK, Vite build OK.

## 2026-07-29 - Optimizaciones de CPU y Compatibilidad 2D en PaddleOCR 3.x

- **Solución a crash de oneDNN en CPU (Windows)**: Se añadió `enable_mkldnn=False` en el constructor de `PaddleOCR` en `main.py` para resolver un bug PIR a runtime de PaddlePaddle en arquitecturas x64 locales.
- **Exclusión de modelos pesados de documentos**: Se configuraron `use_doc_orientation_classify=False` y `use_doc_unwarping=False` en la inicialización de `PaddleOCR`. Esto previene la descarga y el cómputo de modelos 3D lentos de desdoblado de papel, acelerando el escaneo realtime un ~80% en CPU.
- **Corrección de imágenes escala de grises (2D)**: El motor de detección de PaddleOCR 3.x asume formatos de 3 canales `(H, W, C)`. En `_run_ocr` (`pipeline.py`), se añadió una conversión automática de `len(processed.shape) == 2` a BGR vía `cv2.cvtColor`. Esto previene el error `ValueError: not enough values to unpack (expected 3, got 2)` en preprocesamiento adaptativo/realtime.
- **Mapeo de salida del motor**: El método `ocr()` en la nueva versión de PaddleOCR retorna un objeto `OCRResult` que hereda de `dict`. Se adaptó `_run_ocr` para interceptar este diccionario, extraer `rec_polys` (o `dt_polys`), `rec_texts` y `rec_scores` y re-empaquetarlos al formato de lista tradicional `[poly, (text, score)]`, manteniendo intacta la retrocompatibilidad con los tests unitarios y la librería Supervision.
- **Verificación**: Suite de 48 tests pasando exitosamente, compilación local OK y escaneo fluido realtime verificado.
