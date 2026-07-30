# Entrega técnica del sistema de placas

Fecha de corte: 2026-07-30.

## 1. Resumen ejecutivo

Se entrega un monorepo funcional para análisis y registro universitario de
placas. El backend FastAPI ejecuta OCR y clasificación local, persiste en
PostgreSQL/Neon, almacena evidencia privada en Cloudinary y expone una interfaz
React por roles.

El sistema funciona en desarrollo local y supera la suite automatizada actual,
pero la decisión de release es **NO-GO para producción**. Antes de desplegar se
deben rotar secretos, validar las imágenes Docker,
resolver la estrategia de cookies/dominios y completar E2E con servicios y
hardware reales.

El sistema fue evaluado tomando como referencia ISO/IEC 25010:2023 y los
controles aplicables de OWASP ASVS. No está certificado por ISO.

## 2. Estado actual de la entrega

- Hay una única cabeza Alembic local: `c2d3e4f5a6b7`.
- La base Neon configurada fue migrada y verificada en `c2d3e4f5a6b7 (head)`.
- `alembic check` no detecta operaciones pendientes y las 16 solicitudes
  existentes se conservaron.
- Se integró `origin/main` localmente; no se hizo push.

## 3. Rama actual y último commit relevante

- Rama actual: `main`.
- HEAD local observado: `081bc39`, merge que integra `origin/main`.
- Último commit remoto integrado: `64c74bb` (`fix(frontend): persist JWT token
  and inject Authorization header in Axios`).
- Implementación de seguridad relevante en el historial: `1549779` y `24aac6b`.

## 4. Funcionalidades terminadas

- login JWT, cookie HttpOnly/Bearer y autorización backend por roles;
- administración autenticada de usuarios;
- vistas de dashboard, vehículos y accesos filtradas por rol/propiedad;
- lectura FastALPR + FastPlateOCR local;
- validación y normalización de placa boliviana;
- captura estática y polling `realtime=true`;
- asociación placa-vehículo con una inferencia RF-DETR por captura estática;
- sugerencia de color OpenCV con respaldo CLIP ONNX;
- sugerencia de tipo general RF-DETR contra catálogo activo;
- solicitudes de vehículo desconocido con aprobación/rechazo y bloqueo de fila;
- registro de accesos y estado dentro/fuera;
- cooldown contra lecturas duplicadas cercanas;
- gestión de dispositivos y webhooks HTTP(S) validados;
- barrera mediante webhook y simulador SSE;
- Cloudinary autenticado, WebP y URLs temporales;
- Dockerfiles no-root y Compose con healthchecks;
- controles CSRF/origen, límites de carga y cabeceras de seguridad backend;
- pruebas unitarias/integración opt-in y scripts de verificación local;
- migraciones automáticas de base de datos y bootstrap seguro del administrador inicial (cargado de variables de entorno) y catálogo base de marcas al arrancar;
- archivo `netlify.toml` para despliegue automatizado de React Router en Netlify.

## 5. Funcionalidades parciales

- El spool multimedia persiste y reintenta dentro del proceso, pero no existe una
  cola durable ni un worker que recupere automáticamente todo trabajo después de
  un reinicio.
- La retención tiene script de limpieza, pero falta programarlo y verificarlo con
  Cloudinary real.
- El simulador de barrera existe; falta E2E con ESP32/actuador físico.
- El agente USB/RTSP está implementado; falta calibración con las cámaras finales.
- El logout elimina la cookie, pero no revoca el JWT en servidor.
- Docker está configurado y se repararon los permisos de compilación para usuarios no-root, pero la construcción local Linux no se validó por daemon inactivo.
- Railway/Netlify fueron evaluados y se configuró `netlify.toml` para el frontend; los despliegues reales están en proceso.

## 6. Arquitectura vigente

```text
React/Vite
   |
   v
FastAPI/Uvicorn
   ├── SQLAlchemy/Alembic ── PostgreSQL o Neon
   ├── CloudinaryStorage ─── Cloudinary authenticated
   ├── FastALPR ──────────── detector de placa YOLOv9
   ├── FastPlateOCR ──────── caracteres de placa
   ├── RF-DETR Nano ──────── caja + categoría COCO general
   ├── OpenCV ────────────── color principal
   └── CLIP ONNX ─────────── respaldo conservador de color
```

Los motores se inicializan una vez en el lifespan de FastAPI. La cámara USB/RTSP
es un proceso separado y consume `POST /api/v1/plates/analyze`. PostgreSQL no
forma parte de Compose: siempre es un servicio externo.

## 7. Flujo completo

1. Un usuario autenticado con rol de escaneo envía una imagen.
2. El backend valida tipo y tamaño y ejecuta FastALPR/FastPlateOCR.
3. Normaliza la placa, calcula confianza y valida el formato.
4. Si es captura estática, ejecuta RF-DETR una vez y reutiliza la asociación para
   tipo y color; OpenCV precede al fallback CLIP.
5. Si el vehículo existe, registra escaneo y acceso, actualiza estado campus,
   conserva evidencia y puede llamar el webhook de barrera.
6. Si no existe y la placa está detectada y es válida, sube una evidencia y crea
   o reutiliza una solicitud pendiente.
7. El operador revisa sugerencias editables. `DESCONOCIDO` es válido.
8. Al aprobar confirma placa, propietario regular activo, marca, tipo y color; la
   transacción crea el vehículo. Marca y modelo exacto nunca se infieren.

`realtime=true` no ejecuta RF-DETR/CLIP por fotograma, no crea solicitudes y no
sube evidencias.

## 8. Servicios externos

### Neon/PostgreSQL

- Variable única: `DATABASE_URL`.
- Driver requerido: `postgresql+psycopg`.
- Neon exige `sslmode=require`, `verify-ca` o `verify-full`.
- Pool actual por proceso: 5 conexiones base, 5 de overflow.
- FastAPI y Alembic consumen exactamente la misma URL.

### Cloudinary

- Requiere `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` y
  `CLOUDINARY_API_SECRET` sólo en backend.
- Delivery obligatorio: `authenticated`.
- Guarda WebP y entrega URLs temporales firmadas.
- El spool local por defecto es `backend/.runtime/media-spool`.

### Modelos y caché

- FastALPR/FastPlateOCR descargan artefactos del modelo configurado.
- RF-DETR usa `rf-detr-nano-384-coco`.
- CLIP usa `Xenova/clip-vit-base-patch32`, revisión
  `d15189d7028b43f1d3e65039190477f6af591c2a`.
- El Dockerfile precarga los modelos durante el build para evitar descargas al
  arrancar. El volumen Compose sólo cubre `media-spool`, no la caché de modelos.
- La caché local observada ocupa aproximadamente 308 MB; la imagen completa es
  mayor por dependencias nativas.

## 9. Estado de migraciones

```text
Cabeza del repositorio: c2d3e4f5a6b7
Revisión verificada en Neon: c2d3e4f5a6b7 (head)
alembic check: No new upgrade operations detected
```

La migración `c2d3e4f5a6b7` se aplicó el 2026-07-30. Convirtió `creado_el`,
`revisado_el` y `actualizado_el` de `solicitudes_registro_vehiculo` a
`timestamp with time zone`; se verificó la conservación de las 16 filas. Para
comprobar el estado:

```powershell
cd backend
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe check
```

No editar ni eliminar migraciones aplicadas.

## 10. Comandos para ejecutar

Preparación inicial:

```powershell
Copy-Item backend\.env.example backend\.env
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd ..\frontend
npm ci
```

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python run.py
```

Frontend:

```powershell
cd frontend
npm run dev
```

Cámara externa opcional:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.services.camera_capture
```

Docker, con `backend/.env` configurado y Docker Desktop activo:

```powershell
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

## 11. Comandos para verificar

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\scripts\verify-project.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\scripts\smoke-local.ps1
```

Auditorías individuales:

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\bandit.exe -q -r app scripts
.\.venv\Scripts\pip-audit.exe -r requirements.txt
.\.venv\Scripts\alembic.exe heads
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe check

cd ..\frontend
npm.cmd run build
npm.cmd audit --audit-level=low
```

## 12. Resultados recientes verificados

Resultados obtenidos el 2026-07-30 sobre Windows, Python 3.12.10 y el entorno
local vigente:

| Verificación | Resultado |
|---|---|
| `compileall` | correcto |
| pytest | 82 correctas, 2 omitidas, 1 warning |
| cobertura | 64%: 2908 sentencias, 1033 sin cubrir |
| Ruff | sin hallazgos |
| Bandit | sin hallazgos en `app` y `scripts` |
| pip-audit | 0 vulnerabilidades conocidas |
| build frontend | correcto; 108 módulos; JS 437.93 kB, gzip 116.51 kB |
| npm audit | 2 altas por el mismo advisory de React Router RSC; la SPA no usa RSC/SSR/actions |
| Alembic heads | `c2d3e4f5a6b7` |
| Alembic current | Neon en `c2d3e4f5a6b7 (head)` |
| Alembic check | correcto; sin nuevas operaciones |
| verify-project | correcto; stack de visión, pytest y build aprobados |
| smoke-local | correcto; health `ok`, 34 rutas, OCR disponible y analyze anónimo 401 |
| Docker build | no verificado: daemon Docker Desktop inactivo |

El warning de pytest proviene de la deprecación de `httpx` con
`starlette.testclient`. El advisory npm requiere seguimiento, pero su modo RSC
afectado no está habilitado en esta aplicación; no ejecutar `npm audit fix
--force` sin revisar la regresión propuesta.

## 13. Guía corta de demostración

1. Configure `.env` y confirme Neon, Cloudinary y `alembic check`.
2. Inicie backend y frontend.
3. Inicie sesión con una cuenta de demostración entregada por el propietario; no
   escriba credenciales en este archivo.
4. Muestre dashboard y permisos de un administrador/operador.
5. Abra `Escanear Placas`, seleccione cámara o imagen y analice una placa conocida.
6. Compruebe vehículo, propietario, entrada/salida y evidencia.
7. Analice una placa válida desconocida en modo estático.
8. Abra `Solicitudes de vehículos`, edite sugerencias y apruebe o rechace.
9. Muestre que `realtime=true` no crea solicitudes ni sube evidencia.
10. Opcionalmente abra el simulador de barrera con una cuenta staff.

Use datos ficticios o autorizados y evite mostrar secretos, URLs firmadas o datos
personales reales durante la demostración.

## 14. Decisiones técnicas importantes

- OCR completamente local con FastALPR/FastPlateOCR; EasyOCR fue reemplazado.
- No se usa Roboflow Cloud; RF-DETR se ejecuta localmente mediante ONNX.
- RF-DETR se ejecuta una vez por captura estática y se reutiliza.
- OpenCV es el primer método de color; CLIP sólo respalda casos ambiguos.
- `DESCONOCIDO` es una salida correcta y segura.
- Las sugerencias son editables y nunca registran vehículos por sí mismas.
- Marca y modelo exacto quedan fuera del reconocimiento automático.
- Cloudinary usa recursos autenticados y URLs de corta duración.
- PostgreSQL es externo a la aplicación y Compose no crea una base.
- Autorización y validaciones críticas se ejecutan en backend.
- La cuenta `DISPOSITIVO` se vincula al dispositivo físico por coincidencia
  exacta de nombre; aún no existe una FK explícita.
- El registro público está cerrado; sólo un administrador crea cuentas.

## 15. Limitaciones conocidas

- precisión no calibrada con dataset propio, día/noche, movimiento y reflejos;
- cobertura baja en varios endpoints críticos pese al 64% global;
- ausencia de E2E completo y pruebas físicas;
- rate limiter y caché de usuario in-process;
- tareas multimedia sin cola durable;
- health devuelve HTTP 200 aun con estado `degraded`;
- frontend sin lint;
- no se midieron p50/p95, memoria, concurrencia ni cold start productivos.

## 16. Riesgos pendientes

- revocación JWT inexistente después de logout;
- posible pérdida o atasco de spool ante reinicio sin reconciliador;
- Docker Linux no construido en la última sesión;
- cookies `SameSite=Lax` requieren diseño de dominios compatible en despliegue;
- React Router conserva un advisory alto duplicado para RSC no utilizado;
- falta observabilidad, alertas y plan operativo formal de incidentes;

## 17. Credenciales que debe rotar el propietario

Antes de cualquier despliegue, rotar y revocar:

1. `SECRET_KEY` del backend; las sesiones anteriores quedarán invalidadas.
2. contraseña/URL de conexión de Neon.
3. `CLOUDINARY_API_KEY` y `CLOUDINARY_API_SECRET` según capacidades del proveedor.
4. cualquier credencial RTSP configurada o compartida durante pruebas.
5. tokens de Railway, Netlify o repositorio si fueron utilizados fuera de un
   gestor de secretos.

No reutilizar valores anteriores ni guardarlos en Git, documentación, variables
`VITE_*`, logs o capturas. Actualizar los servicios consumidores y verificar el
arranque después de cada rotación.

## 18. Recuperación y rollback

### Código

1. Identifique el último commit estable con `git log --oneline`.
2. Cree una rama de recuperación; no use `git reset --hard` sobre trabajo ajeno.
3. Para deshacer un despliegue versionado, prefiera `git revert <commit>` y vuelva
   a ejecutar verify-project/smoke antes de publicar.
4. Railway/Netlify deben volver a desplegar el commit estable y conservar las
   mismas variables verificadas.

### Base de datos

1. Antes de migrar, cree backup o branch de Neon.
2. Si la migración falla, detenga el release y conserve el código anterior.
3. Prefiera restaurar el branch/backup validado. Sólo use
   `alembic downgrade b1c2d3e4f5a6` después de revisar el `downgrade`, ventana de
   mantenimiento y efecto de conversión horaria.
4. Compruebe `alembic current`, conteos e integridad antes de reabrir tráfico.

### Cloudinary y spool

1. No borre el volumen durante un rollback.
2. Liste registros `PENDING`, `PROCESSING` o `FAILED` y contraste sus `public_id`.
3. Reintente mediante endpoints autorizados o procedimiento de mantenimiento.
4. No elimine activos hasta confirmar que no son referenciados por la base.

## 19. Pendientes priorizados

### P0

- Rotar secretos de sesión, Neon, Cloudinary y cualquier RTSP expuesto.

### P1

- Diseñar/probar cookies y dominios para Railway + Netlify.
- Construir las imágenes Docker y ejecutar smoke en Linux.
- Completar E2E de roles, placa conocida/desconocida, Cloudinary y barrera.
- Incorporar cola/reconciliación durable para evidencias.
- Separar health de liveness y readiness.

### P2

- Aumentar cobertura de auth, accesos, vehículos, medios y dashboard.
- Calibrar OCR/color/tipo con dataset propio y cámaras finales.
- Medir memoria, latencia p50/p95, concurrencia y cold start.
- Implementar revocación JWT mediante diseño y migración coordinados.
- Añadir lint frontend y automatizar SAST/SCA en CI.

### P3

- Añadir observabilidad, paneles y alertas.
- Reemplazar la asociación por nombre entre cuenta y dispositivo por una FK.
- Mejorar documentación operativa de incidentes y mantenimiento periódico.
- Revisar el warning futuro de TestClient/httpx y actualizaciones no disruptivas.

## 20. Próximos pasos recomendados

1. Rotar todas las credenciales y verificar que no existan secretos versionados.
2. Crear branch/backup Neon antes de futuras migraciones y ejecutar E2E sobre staging.
3. Arrancar Docker Desktop, construir ambas imágenes y medir recursos reales.
4. Elegir dominios propios para frontend/API y validar cookies en navegadores.
5. Preparar configuración reproducible de Railway/Netlify sin desplegar todavía.
6. Añadir recuperación durable de medios y health readiness.
7. Repetir Ruff, Bandit, pip-audit, npm audit, pytest, verify-project y smoke.
8. Realizar demostración controlada y obtener aprobación del propietario antes de
   cualquier push o despliegue productivo.
