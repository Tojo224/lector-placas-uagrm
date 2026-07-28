# Issue 016 — Dependencias usadas por el backend no instaladas

## Síntoma

El harness no podía importar Cloudinary, SlowAPI ni `cachetools`.

## Causa y corrección

Cloudinary y SlowAPI estaban declarados pero no instalados localmente.
`cachetools` era utilizado por autenticación sin estar en `requirements.txt`.
Se instalaron y se añadió `cachetools>=5.5.0,<7.0.0` a las dependencias.
También se sincronizó `backend/.venv`, que es el intérprete utilizado por el
smoke local; instalarlo solo en el Python global no permitía arrancar Uvicorn.

## Validación

El harness terminó con 44 pruebas correctas, 2 integraciones externas omitidas
por diseño y build Vite satisfactorio.
