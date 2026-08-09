# UAGRM Plate Edge Agent

## Aprovisionamiento de sincronizacion

1. Un administrador llama una vez a
   `POST /api/v1/edge-sync/devices/{device_id}/provision` en el backend central.
2. La respuesta entrega `device_id` y `credential`. La credencial no puede
   recuperarse nuevamente; volver a aprovisionar la rota.
3. La instalacion configura fuera de SQLite:

```text
EDGE_CENTRAL_URL=https://backend.example.edu
EDGE_DEVICE_ID=<uuid del dispositivo>
EDGE_DEVICE_KEY=<credencial emitida>
```

En produccion, `EDGE_CENTRAL_URL` debe usar HTTPS. El empaquetado posterior debe
proteger `EDGE_DEVICE_KEY` mediante mecanismos de Windows; esta fase no incluye
el instalador.

Valores operativos opcionales:

```text
EDGE_SNAPSHOT_REFRESH_SECONDS=900
EDGE_SYNC_POLL_SECONDS=5
EDGE_SYNC_TIMEOUT_SECONDS=10
EDGE_SYNC_BATCH_SIZE=25
EDGE_SYNC_MAX_ATTEMPTS=10
```

El agente descarga el snapshot al arrancar cuando no existe uno local. OCR y la
decision SQLite continúan funcionando aunque el backend central no responda.
