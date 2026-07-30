# Sistema universitario de análisis y registro de placas

Aplicación web para detectar placas vehiculares, consultar vehículos autorizados,
registrar entradas y salidas y enviar vehículos desconocidos a revisión humana.
Está orientada a porterías universitarias y combina una API FastAPI, un cliente
React, PostgreSQL y un pipeline local de visión ejecutado con ONNX Runtime.

El sistema fue evaluado tomando como referencia ISO/IEC 25010:2023 y los
controles aplicables de OWASP ASVS. Esto no implica una certificación ISO.

## Problema que resuelve

La lectura manual de placas en una portería es lenta y propensa a errores. Este
proyecto automatiza la detección y lectura inicial, conserva trazabilidad del
acceso y permite identificar vehículos registrados. Cuando la evidencia no es
concluyente o la placa no existe, el sistema conserva la decisión final en manos
del operador.

## Funcionalidades principales

- autenticación por JWT, actualmente compatible con cookie HttpOnly y Bearer,
  con autorización backend por roles;
- lectura local de placas bolivianas desde imagen, cámara web, USB o agente RTSP;
- consulta de vehículo y propietario autorizado;
- registro de entrada/salida con protección contra duplicados cercanos;
- estado actual del vehículo dentro o fuera del campus;
- sugerencia editable de color y tipo general;
- bandeja de solicitudes para vehículos desconocidos;
- administración de usuarios, vehículos, marcas, tipos y dispositivos;
- evidencias privadas en Cloudinary con URL temporal firmada;
- webhook y simulador SSE para barrera;
- dashboard y vistas filtradas según rol.

Las salidas de IA son sugerencias, no decisiones. `DESCONOCIDO` es un resultado
válido. El operador confirma placa, propietario, marca, tipo y color antes de que
una solicitud cree un vehículo. El sistema no reconoce automáticamente marca ni
modelo exactos.

## Arquitectura

```text
React 18 + Vite
        |
        | HTTPS / JSON / multipart / JWT (cookie HttpOnly o Bearer)
        v
FastAPI + SQLAlchemy + Alembic
   |          |               |
   |          |               +--> Cloudinary autenticado
   |          +------------------> PostgreSQL / Neon
   |
   +--> FastALPR + FastPlateOCR (placa)
   +--> RF-DETR Nano COCO (caja y categoría general del vehículo)
   +--> OpenCV (color primario)
   +--> CLIP ViT-B/32 ONNX (respaldo conservador de color)
```

PostgreSQL es externo a Compose. FastAPI, SQLAlchemy y Alembic consumen la misma
`DATABASE_URL`. Los modelos se ejecutan localmente en CPU; no se usa una API de
inferencia remota.

## Tecnologías vigentes

| Capa | Tecnología |
|---|---|
| API | FastAPI 0.141.1, Uvicorn, Pydantic 2 |
| Cliente | React 18, React Router 7.18.2, Axios, Vite 8 |
| Persistencia | PostgreSQL, Neon, SQLAlchemy 2, Alembic |
| Medios | Cloudinary autenticado, WebP, URLs temporales firmadas |
| Placas | FastALPR 0.4.0 + FastPlateOCR 1.1.0, ONNX Runtime |
| Vehículo | RF-DETR Nano COCO mediante `open-image-models` |
| Color | OpenCV HSV/LAB/K-Means y CLIP ViT-B/32 ONNX cuantizado |
| Imágenes | OpenCV headless, Pillow, Supervision 0.29.1 |
| Contenedores | Python 3.12 slim, Node 22, Nginx 1.28 Alpine |

EasyOCR y Roboflow Cloud no forman parte del runtime vigente.

## Estructura del repositorio

```text
.
├── backend/
│   ├── app/
│   │   ├── ai/             # OCR, normalización y validación
│   │   ├── api/v1/         # endpoints HTTP
│   │   ├── config/         # settings desde entorno
│   │   ├── core/           # seguridad, límites y excepciones
│   │   ├── db/             # modelos y sesiones SQLAlchemy
│   │   ├── schemas/        # contratos Pydantic
│   │   └── services/       # cámara, IA, imágenes y Cloudinary
│   ├── alembic/            # historial de migraciones
│   ├── scripts/            # mantenimiento de BD y medios
│   ├── tests/              # pruebas automatizadas
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── public/
│   ├── src/                # React, rutas, páginas y cliente HTTP
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── .agents/
│   ├── scripts/            # verificación y smoke test
│   └── memory/             # estado operativo del proyecto
├── docs/                   # auditorías, decisiones y modelos externos
├── docker-compose.yml
├── HANDOFF.md
└── README.md
```

## Requisitos previos

- Git.
- Python 3.12 de 64 bits.
- Node.js 22 y npm.
- PostgreSQL accesible, local o Neon.
- Cuenta de Cloudinary para los flujos que almacenan evidencias.
- PowerShell 5.1 o superior para los scripts `.agents` incluidos.
- Docker Desktop con Compose v2 si se usará Docker.
- Conexión a Internet durante la instalación inicial o el build Docker para
  descargar paquetes y modelos ONNX.

Los modelos y dependencias de visión consumen varios cientos de MB. Para cámara
física se necesita una webcam compatible o una URL RTSP accesible.

## Variables de entorno

Desde la raíz, cree el archivo local sin versionarlo:

```powershell
Copy-Item backend\.env.example backend\.env
```

En Linux/macOS:

```bash
cp backend/.env.example backend/.env
```

Edite `backend/.env`. Como mínimo debe reemplazar:

```dotenv
DEBUG=false
ALLOWED_ORIGINS='["https://localhost:5173"]'
DATABASE_URL=postgresql+psycopg://usuario:clave@host:5432/base
SECRET_KEY=reemplace-por-un-valor-aleatorio-de-al-menos-32-caracteres
ACCESS_TOKEN_EXPIRE_MINUTES=15

CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
CLOUDINARY_SECURE=true
CLOUDINARY_DELIVERY_TYPE=authenticated
```

Para Neon, la URL debe usar Psycopg y TLS:

```dotenv
DATABASE_URL=postgresql+psycopg://usuario:clave@host-pooler.neon.tech/base?sslmode=require&channel_binding=require
```

No use el placeholder de `SECRET_KEY`: la aplicación lo rechaza. No coloque
secretos en variables `VITE_*`, porque Vite las integra en el JavaScript público.
El resto de variables OCR, cámara, Cloudinary y retención está descrito, con sus
valores vigentes, en `backend/.env.example`.

## Instalación del backend

PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

La primera inicialización descarga los modelos configurados. Para comprobar la
conexión sin imprimir credenciales:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\check_database.py
```

## Instalación del frontend

```powershell
cd frontend
npm ci
```

`npm ci` usa `frontend/package-lock.json` y es preferible a `npm install` para
reproducir el conjunto verificado.

## Migraciones de Alembic

Alembic obtiene la URL exclusivamente desde `backend/.env`/entorno. Desde
`backend`:

```powershell
.\.venv\Scripts\alembic.exe heads
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe check
```

La única cabeza del repositorio es `c2d3e4f5a6b7`. La instancia Neon verificada
el 2026-07-30 está alineada con esa revisión y `alembic check` no detectó nuevas
operaciones. Para otra base o una migración futura, haga backup o cree una rama
de Neon antes de `upgrade head`. No edite ni elimine migraciones aplicadas.

Las migraciones de la base de datos se ejecutan de forma automática al arrancar la aplicación. Si la base de datos se encuentra vacía (sin usuarios), el backend sembrará de manera automática el usuario `ADMINISTRADOR` inicial usando las credenciales configuradas en las variables de entorno (`BOOTSTRAP_ADMIN_CARNET` y `BOOTSTRAP_ADMIN_PASSWORD`), además de sembrar el catálogo base de marcas en la tabla `marcas` para permitir la operatividad inmediata del sistema.

## Ejecución local

Terminal 1, backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python run.py
```

API y documentación interactiva:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/api/v1/plates/health`

Terminal 2, frontend:

```powershell
cd frontend
npm run dev
```

Abra `https://localhost:5173`. Vite usa un certificado local autofirmado y
redirige `/api` al backend. El navegador puede pedir confirmar el certificado.

Agente opcional para cámara USB o RTSP, en una tercera terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.services.camera_capture
```

La cámara del navegador se ejecuta desde `/subir-placa`; requiere HTTPS o
`localhost` y un usuario `ADMINISTRADOR`, `OPERADOR` o `DISPOSITIVO`.

## Ejecución con Docker

Prepare primero `backend/.env` con una base externa. Compose no crea PostgreSQL.
Después:

```powershell
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f
```

Servicios:

- frontend: `https://localhost:5173`;
- backend: `http://localhost:8000`;
- volumen `backend_media_spool`: sólo archivos pendientes de Cloudinary.

Para detener sin borrar el volumen:

```powershell
docker compose down
```

No use `docker compose down -v` salvo que acepte perder el spool pendiente. Los
Dockerfiles descargan modelos durante el build; el primer build puede tardar.

## Pruebas y verificaciones

Suite principal desde la raíz:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\scripts\verify-project.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\scripts\smoke-local.ps1
```

El primer script ejecuta `compileall`, comprueba el stack de visión, corre pytest
y construye el frontend. El smoke inicia Uvicorn en el puerto 8010, comprueba
health/OpenAPI y confirma que `/analyze` rechaza acceso anónimo; siempre detiene
el proceso al finalizar.

Comandos individuales:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\bandit.exe -q -r app scripts
.\.venv\Scripts\pip-audit.exe -r requirements.txt

cd ..\frontend
npm.cmd run build
npm.cmd audit --audit-level=low
```

Ruff, Bandit, pip-audit y pytest-cov son herramientas de desarrollo y pueden
requerir instalación explícita si no existen en el entorno:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install ruff bandit pip-audit pytest-cov
```

El frontend no define actualmente un script `npm run lint`.

## Roles y permisos

| Rol | Acceso principal |
|---|---|
| `ADMINISTRADOR` | usuarios, catálogos, dispositivos, dashboard, vehículos, accesos, solicitudes y escaneo |
| `OPERADOR` | operación de vehículos/accesos, solicitudes y escaneo; no administra usuarios ni dispositivos |
| `DISPOSITIVO` | flujo autenticado de escaneo; se asocia por nombre exacto con un registro `Dispositivo` |
| `USUARIO` | perfil, sus vehículos y sus accesos autorizados |

Las comprobaciones relevantes se repiten en el backend; ocultar una ruta en React
no constituye autorización.

## Flujo de reconocimiento de placas

1. El cliente envía JPEG/PNG de hasta 5 MB a `POST /api/v1/plates/analyze`.
2. FastALPR localiza candidatos y FastPlateOCR reconoce caracteres.
3. Se normaliza y valida el formato boliviano; baja confianza requiere revisión.
4. En captura estática, RF-DETR Nano se ejecuta una sola vez para obtener la caja
   y categoría COCO general (`car`, `motorcycle`, `bus` o `truck`).
5. La misma asociación se reutiliza para tipo y color.
6. OpenCV analiza el color; CLIP ONNX sólo actúa como respaldo conservador sobre
   el recorte estático seleccionado.
7. Si no hay evidencia suficiente, color o tipo quedan `DESCONOCIDO`.
8. Si el vehículo existe, se registra el acceso evitando duplicados cercanos y,
   si corresponde, se dispara el webhook de barrera.

RF-DETR no identifica marca o modelo exactos. Las categorías y colores sugeridos
son editables y deben confirmarse cuando se registra un vehículo.

Con `realtime=true` sólo se realiza el flujo de lectura necesario para polling:
no se ejecutan RF-DETR/CLIP por fotograma, no se crea una solicitud y no se sube
evidencia a Cloudinary.

## Flujo de vehículos desconocidos

1. Una captura estática produce una placa válida y no registrada.
2. El backend registra el escaneo y sube una sola evidencia privada.
3. Se crea, como máximo, una solicitud `PENDING` por placa pendiente.
4. La bandeja muestra placa, confianza y sugerencias editables de color/tipo.
5. Un `ADMINISTRADOR` u `OPERADOR` aprueba o rechaza.
6. Al aprobar, el operador confirma propietario regular activo, marca, tipo,
   color y placa. Sólo entonces se crea el vehículo.

Una lectura ambigua, `DESCONOCIDO` o baja confianza nunca registra un vehículo
automáticamente.

## Almacenamiento de evidencias

- Cloudinary se configura únicamente en el backend.
- Las imágenes se procesan a WebP y se guardan como recursos autenticados.
- La base almacena metadatos, no credenciales ni URLs permanentes públicas.
- El acceso se realiza mediante URLs temporales firmadas.
- Evidencias de acceso usan spool y tarea de fondo con reintentos.
- Evidencias de solicitudes se cargan una vez antes de crear la solicitud.
- `cleanup_expired_media.py` atiende la retención configurada; prográmelo de
  forma controlada en producción.

## Despliegue

El repositorio puede servir el backend como contenedor y el frontend como sitio
estático. Antes de producción son obligatorios:

1. rotar `SECRET_KEY`, credenciales Neon y Cloudinary;
2. comprobar `alembic current/check` y respaldar la base antes de futuras migraciones;
3. configurar el origen HTTPS exacto en `ALLOWED_ORIGINS`;
4. probar login, roles, Cloudinary, cámara, barrera y retención;
5. medir memoria y latencia de OCR/RF-DETR/CLIP;
6. configurar persistencia de `MEDIA_SPOOL_DIR` y recuperación de tareas fallidas;
7. comprobar cookies entre los dominios de frontend y API.

Para Railway + Netlify se recomiendan subdominios propios del mismo sitio, por
ejemplo `app.ejemplo.edu.bo` y `api.ejemplo.edu.bo`. Los dominios gratuitos de
ambas plataformas son sitios diferentes y la cookie actual `SameSite=Lax` puede
no acompañar peticiones XHR. Netlify necesita además fallback SPA, cabeceras de
seguridad y `VITE_API_BASE_URL`; estos archivos de plataforma todavía no existen.

## Solución de problemas

### La aplicación rechaza `SECRET_KEY`

El placeholder de `.env.example` es deliberadamente inválido. Use un secreto
aleatorio de al menos 32 caracteres.

### Neon no conecta

Compruebe el driver `postgresql+psycopg`, host, base y `sslmode=require`. Ejecute:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\check_database.py
```

### Login correcto seguido de 401

Verifique HTTPS, `ALLOWED_ORIGINS`, `VITE_API_BASE_URL`, cookies bloqueadas y que
frontend/API compartan el mismo sitio o una configuración de cookie compatible.

### `alembic check` dice que la base no está actualizada

Ejecute primero `alembic current`, haga backup y aplique `alembic upgrade head`.
La cabeza esperada es `c2d3e4f5a6b7`.

### El health está `degraded`

Revise descarga de modelos, memoria, permisos de `.runtime` y logs de inicio. El
endpoint devuelve HTTP 200 aun cuando el cuerpo indique `degraded`; inspeccione
siempre `status` y `ocr_available`.

### Docker no construye

Confirme que Docker Desktop y su motor Linux estén activos. El build necesita
Internet para paquetes y modelos y puede consumir bastante disco.

### La cámara no aparece

Use HTTPS/localhost, conceda permiso al navegador y compruebe el rol. Para RTSP,
revise `CAMERA_RTSP_URL`; no publique esa URL porque puede contener credenciales.

### Cloudinary queda en `FAILED`

Revise las tres credenciales, `CLOUDINARY_DELIVERY_TYPE=authenticated`, el spool
y los logs sin copiar secretos. Los endpoints autorizados permiten reintento.

## Limitaciones conocidas

- El logout borra la cookie, pero no hay revocación JWT en servidor.
- El rate limit y la caché de usuario son locales al proceso, no distribuidos.
- Las tareas multimedia en segundo plano no sustituyen una cola durable.
- El health de Railway debería separar liveness y readiness.
- No hay métricas productivas p50/p95, concurrencia ni memoria máxima.
- La cobertura total actual es 64%; varios endpoints tienen cobertura baja.
- Falta E2E real con los cuatro roles, Neon, Cloudinary, cámara y barrera.
- Suciedad, reflejos, ángulo, movimiento e iluminación afectan la precisión.
- `DESCONOCIDO` es intencional y preferible a una clasificación forzada.
- No se reconocen automáticamente marca, modelo exacto, SUV, sedán o variantes
  comerciales; el operador los selecciona de catálogos disponibles.
- El frontend no tiene lint configurado.

## Licencias y modelos externos

El repositorio no concede una garantía sobre los modelos de terceros. Antes de
redistribuir o explotar comercialmente, conserve avisos y revise las condiciones
de cada dependencia y peso.

- CLIP de OpenAI y la conversión ONNX seleccionada: licencia MIT según sus
  repositorios/model cards; se usa `Xenova/clip-vit-base-patch32` con revisión
  fijada en configuración.
- RF-DETR Nano y pesos designados: Apache-2.0; `open-image-models`: MIT.
- OpenCV: Apache-2.0.
- FastALPR/FastPlateOCR y sus modelos deben revisarse en sus distribuciones
  concretas antes de redistribuirlos.

Las referencias verificadas del proyecto están en `docs/third-party-models.md`
y `.agents/compatibility/supervision.md`.
