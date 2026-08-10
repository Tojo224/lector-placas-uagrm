# UAGRM Plate Edge Agent

## Aprovisionamiento de sincronizacion

1. Un administrador llama una vez a
   `POST /api/v1/edge-sync/devices/{device_id}/provision` en el backend central.
2. La respuesta entrega `device_id` y `credential`. La credencial no puede
   recuperarse nuevamente; volver a aprovisionar la rota.
3. El operador abre `/configuracion`, ingresa URL, ID y credencial una sola vez.
   El agente valida y descarga el snapshot antes de guardar la URL/ID en JSON y
   la credencial con DPAPI CurrentUser. No se requiere `.env` en produccion.

Las variables `EDGE_CENTRAL_URL`, `EDGE_DEVICE_ID` y `EDGE_DEVICE_KEY` quedan
disponibles exclusivamente como puente de desarrollo/pruebas. En produccion la
URL debe usar HTTPS.

Valores operativos opcionales:

```text
EDGE_SNAPSHOT_REFRESH_SECONDS=900
EDGE_SYNC_POLL_SECONDS=5
EDGE_SYNC_TIMEOUT_SECONDS=10
EDGE_SYNC_BATCH_SIZE=25
EDGE_SYNC_MAX_ATTEMPTS=10
EDGE_MEDIA_MAX_UPLOAD_BYTES=5242880
EDGE_MEDIA_MIN_FREE_BYTES=104857600
```

## Interfaz React local

El agente sirve `frontend/dist` por defecto y aplica fallback de SPA para rutas
como `/subir-placa`. Puede usarse otra ubicacion con:

```text
EDGE_FRONTEND_DIR=<directorio del build Vite>
```

La URL operativa es `http://127.0.0.1:8765`. Al servirse desde el mismo origen,
OCR no depende de CORS, Private Network Access ni contenido mixto. Para Vite en
desarrollo, `/edge-api` se proxifica al agente local. Origenes adicionales se
declaran explicitamente en `EDGE_UI_ORIGINS`; no se permite wildcard.

El agente descarga el snapshot al arrancar cuando no existe uno local. OCR y la
decision SQLite continúan funcionando aunque el backend central no responda.

Las evidencias se convierten a WebP y se almacenan bajo `spool/access/YYYY/MM`
dentro de `EDGE_DATA_DIR`. SQLite conserva solamente ruta relativa, checksum y
estado. Un archivo confirmado por el backend no se elimina todavía; la política
de retención pertenece a una fase posterior.

## Distribucion Windows onedir

El build de produccion se genera desde la raiz con:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/build-windows-onedir.ps1
```

El resultado queda en
`backend/dist/windows/UAGRMPlateAgent/UAGRMPlateAgent.exe`, acompañado por la
carpeta `runtime`. El operador copia la carpeta completa y ejecuta solamente el
EXE; no necesita Python, Uvicorn, Node ni terminal de desarrollo. La interfaz
queda disponible en `http://127.0.0.1:8765`.

El build valida por SHA-256 e incluye el detector YOLOv9, el OCR CCT XS v2 y su
configuracion. En ejecucion se usan rutas directas bajo `runtime/resources` y se
fuerza el modo offline. Los datos mutables nunca se escriben junto al EXE: por
defecto viven en `%ProgramData%\UAGRM\PlateAgent` y los logs rotativos en su
subdirectorio `logs`.

`EDGE_DEVICE_KEY` es solamente un puente de desarrollo. El instalador productivo
usa `WindowsDpapiCredentialProvider`, sin guardar la clave en SQLite, JSON ni un
archivo `.env`.

## Instalador productivo

El pipeline completo se ejecuta con:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/build-windows-installer.ps1
```

Genera `backend/dist/windows/UAGRMPlateAgent-Setup.exe`, conserva el onedir y
escribe `SHA256SUMS.txt`. Inno Setup instala en
`%ProgramFiles%\UAGRM\PlateAgent`, concede `Modify` a usuarios sobre
`%ProgramData%\UAGRM\PlateAgent` y registra una tarea Task Scheduler ONLOGON.
Desinstalar retira binarios y tarea, pero conserva ProgramData.

La primera configuracion se abre en `http://127.0.0.1:8765/configuracion`.
`central_url` y `device_id` se guardan en `config/agent.json`; la clave se
protege con DPAPI CurrentUser en `config/device-key.dpapi`. El agente valida la
credencial descargando el snapshot antes de persistirla y nunca vuelve a
mostrarla. No se admite HTTP productivo salvo loopback para pruebas.

La version 0.2.0 se define en `edge_agent/version.py` y el build la propaga a
las propiedades del EXE, Setup, API y UI. Los artefactos actuales no tienen
firma Authenticode y pueden mostrar advertencias de SmartScreen.
