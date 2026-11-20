# Estado actual · 2026-11-20

Dropper publica desde Telegram y graba el comprobante en la PC de Windows. El panel de Cloudflare administra los bots y muestra las publicaciones confirmadas por fecha y modelo.

## Resumen diario y recuperación desde Telegram

- Rama `feat/dropper-daily-drops`. En **Drops**, el panel agrupa las publicaciones automáticas y manuales por modelo y día de Caracas. La app sincroniza las confirmaciones pendientes cuando recupera la conexión.
- Tras un fallo, **Enviar enlace** confirma el post manual y **Omitir post** avanza al siguiente. El comprobante usa los IDs confirmados, en el orden del Drop. La compilación de Windows genera `Dropper.exe`.
- Validación local con la suite de Python sin navegador, los tests del Worker, la interfaz del resumen con el Worker y la compilación de Cloudflare. Los flujos con Chrome y el EXE se verifican en GitHub Actions.

## Producción

- El [panel web](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin) sigue en v8 hasta el despliegue del Worker v9.
- Tras la revisión del PR, aplicar `cloudflare/schema.sql` en el D1 existente, desplegar el Worker v9 y comprobar `/health` y la sección **Drops**. Instalar el [nuevo EXE oficial](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/latest) cuando lo publique el flujo de Windows en `main`.
