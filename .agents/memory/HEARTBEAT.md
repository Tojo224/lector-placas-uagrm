# HEARTBEAT

## Estado vigente - 2026-07-28

- **Foco**: Integración de la rama `Beto` en `devgrover` + Corrección de hallazgos de seguridad y robustez tras revisión 4R.
- **Validado**: 
  - 4R review completada (R1 Risk, R4 Resilience, R2 Readability, R3 Reliability). 26 archivos, 1372 líneas revisadas. Estado: approved.
  - Soporte de cámara USB enumeradas por el navegador y conexión del celular mediante USB.
  - Rediseño del modal de revisión de vehículos desconocidos.
- **Completado en esta sesión**:
  - **SDD Init**: Inicializado con engram, strict TDD activado.
  - **4R Review**: Risk, Resilience, Readability, Reliability ejecutados con native gentle-ai.
  - **SEC-011**: Token JWT removido de localStorage — solo cookie httpOnly session_token.
  - **SEC-012**: PII propietario_nombre solo para usuarios autenticados en /analyze.
  - **SEC-013**: Excepción de BD en plates.py ya no es tragada — retorna 500 con log.
  - **SEC-014**: TOCTOU en cooldown de accesos corregido con FOR UPDATE.
  - **ROB-001**: asyncio.gather sobre misma AsyncSession reemplazado por awaits secuenciales.
  - **ROB-002**: Acumulación de streams de cámara corregida — stopCamera siempre en cleanup.
  - **ROB-003**: Limitación de TTLCache in-process documentada.
  - **BETO-CONN**: Soporte para conexión de celular mediante USB y selección/enumeración de cámaras USB en `/subir-placa` sin recargar la página.
  - **BETO-UI**: Rediseño de la bandeja y modal de revisión de vehículos desconocidos.
- **ACCION REQUERIDA**: Ninguna por ahora. Backend listo para reiniciar.
- **Proximo paso**: Resolver pendientes del backlog o iniciar nuevo feature (como la migración a PaddleOCR).
- **Convension Dispositivo y Usuario**: El nombre del Dispositivo debe coincidir exactamente con el nombre del Usuario de rol DISPOSITIVO.
