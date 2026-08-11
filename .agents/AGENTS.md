# AGENTS - Lector de Placas UAGRM

## Identidad del proyecto

Backend y base de coordinacion del proyecto "Lector de Placas UAGRM". El objetivo del sistema es analizar una imagen de un vehiculo, detectar y leer una placa, consultar si ya existe en PostgreSQL y, solo si no existe, habilitar un registro manual condicionado a un codigo universitario valido.

## Stack real actual

- Backend: FastAPI
- Base de datos: PostgreSQL + SQLAlchemy + Alembic
- OCR local: FastALPR (detector YOLOv9) + FastPlateOCR sobre ONNX Runtime
- Color vehicular: RF-DETR Nano para caja real + OpenCV HSV/LAB/K-Means;
  devuelve `DESCONOCIDO` cuando la prediccion no es confiable
- Tipo vehicular: reutiliza la misma inferencia RF-DETR Nano y solo mapea las
  clases COCO `car`, `motorcycle`, `bus` y `truck` al catalogo activo
- Supervision: representacion, recorte y anotacion de detecciones
- Captura automatica: agente separado para webcam USB o RTSP
- Medios privados: Cloudinary autenticado con WebP y URLs temporales firmadas
- Frontend separado: React 18 + JavaScript/JSX + CSS, construido con Vite

## Arquitectura real

- `backend/app/api/v1/`: endpoints HTTP
- `backend/app/ai/`: pipeline IA y validadores
- `backend/app/db/`: modelos y sesion
- `backend/app/config/`: settings
- `backend/app/services/`: servicios locales separados, incluido el agente de camara USB/RTSP
- `frontend/`: aplicacion React/Vite del cliente web
- `.agents/`: memoria operativa del proyecto

## Dependencias externas

- PostgreSQL es externo a la aplicacion y se configura exclusivamente mediante
  `DATABASE_URL`; Compose no declara ni exige un servicio `db`.
- La misma `DATABASE_URL` es consumida por FastAPI, SQLAlchemy y Alembic.
- Se admiten PostgreSQL local, PostgreSQL accesible desde Docker y Neon sin
  cambiar codigo ni Compose. Neon requiere TLS.
- Cloudinary se configura desde `backend/.env`; nunca registrar credenciales,
  URLs firmadas ni identificadores sensibles en memoria o logs.
- `backend/.env` no se versiona y queda excluido del contexto Docker.

## Roles vigentes

- `ADMINISTRADOR`: panel, usuarios, catalogos y dispositivos.
- `OPERADOR`: gestion operativa de vehiculos y accesos manuales.
- `DISPOSITIVO`: acceso exclusivo al flujo de escaneo `/subir-placa`.
- `USUARIO`: propietario regular de vehiculos y consulta autorizada.
- El registro fisico `Dispositivo` y la cuenta `Usuario` con rol `DISPOSITIVO`
  siguen siendo entidades separadas; no asumir que crear una genera la otra.

## Reglas de negocio obligatorias

1. Nunca registrar automaticamente una placa solo porque el OCR detecto texto.
2. Si la placa ya existe, devolver vehiculo y persona asociada.
3. Si la placa no existe, pedir codigo universitario antes de permitir registro.
4. El codigo debe pertenecer a una persona valida y activa.
5. Una placa nueva debe pasar validacion de formato en backend.
6. Detecciones u OCR de baja confianza requieren revision manual.

## Flujo obligatorio antes de programar

Antes de tocar codigo, cualquier agente debe leer en este orden:

1. `.agents/AGENTS.md`
2. `.agents/memory/SOUL.md`
3. `.agents/memory/HEARTBEAT.md`
4. `.agents/steering/backlog.md`

Despues de cambios en Python, dependencias o pipeline IA, ejecutar desde la raiz:

```powershell
powershell -ExecutionPolicy Bypass -File .agents/scripts/verify-project.ps1
```

El comando es local y determinista: no usa servicios cloud ni modifica la base de datos.

Para probar el arranque HTTP en un puerto aislado y cerrarlo automaticamente:

```powershell
powershell -ExecutionPolicy Bypass -File .agents/scripts/smoke-local.ps1
```

## Protocolo de memoria

Al cerrar una sesion:

1. actualizar `.agents/memory/HEARTBEAT.md`;
2. registrar decisiones y validaciones en `.agents/memory/MEMORY.md`;
3. actualizar estados en `.agents/steering/backlog.md`.

## Reglas de IA

- FastALPR localiza placas y FastPlateOCR reconoce sus caracteres; EasyOCR fue
  retirado y no debe reintroducirse sin una decision explicita.
- Supervision representa, recorta y anota resultados; no es un motor OCR ni un
  clasificador de color.
- RF-DETR Nano se usa para obtener una caja real del vehiculo asociada con la
  placa. Sin una caja confiable, el color debe ser `DESCONOCIDO`.
- RF-DETR se ejecuta una sola vez por imagen estatica; su deteccion y asociacion
  se reutilizan para color y tipo. Nunca ejecutar esta inferencia en realtime.
- La sugerencia de tipo solo admite Automovil, Motocicleta, Bus y Camion por
  aliases normalizados y coincidencia unica con un tipo activo. No inferir SUV,
  sedan, hatchback, pickup, minibus o furgoneta.
- Persistir para tipo solo `tipo_sugerido_id`, `confianza_tipo` y `metodo_tipo`.
  Una sugerencia ambigua no selecciona ni registra automaticamente un vehiculo.
- OpenCV evalua el color dentro de la caja asociada por RF-DETR. No existe un
  regresor entrenado versionado; una imagen ambigua devuelve `DESCONOCIDO`. El
  polling realtime no ejecuta RF-DETR ni color por frame.
- El catalogo de color es cerrado: BLANCO, NEGRO, GRIS, PLATEADO, ROJO, AZUL,
  VERDE, AMARILLO y MARRON. Un resultado dudoso nunca debe forzar una clase.
- No implementar marca, modelo o tipo con CLIP sin una solicitud explicita.
- Los tres campos persistidos son `color_sugerido`, `confianza_color` y
  `metodo_color`; no guardar arrays JSON de colores.
- Preferir una ROI configurada para camaras fijas y reducir falsos positivos.
- Preferir rutas portables con `pathlib.Path`.
- Mantener la matriz documentada en `.agents/compatibility/supervision.md`.
- No cambiar Supervision, FastALPR, FastPlateOCR, ONNX Runtime, NumPy u OpenCV
  sin actualizar la matriz y ejecutar el verificador.
- La captura automatica debe ejecutarse fuera del proceso FastAPI y reutilizar `POST /api/v1/plates/analyze`.
- No usar `cv2.imshow()` ni registrar URLs RTSP, porque pueden contener credenciales.

## Prohibiciones

- No subir secretos al repositorio.
- No guardar imagenes privadas, capturas de camara ni credenciales RTSP en el repositorio.
- No marcar una funcionalidad como terminada si no se verifico.
- No introducir rutas absolutas de Windows en codigo de aplicacion.
