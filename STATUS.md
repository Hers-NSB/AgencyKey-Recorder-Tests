# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica mensajes reenviados por Telegram y genera un comprobante con Chrome en la PC. El panel web solicita a la app de Windows la verificación de Mi perfil, que puede ejecutarse con el bot detenido.

## Publicado

- [Panel web v7](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin) desplegado en Cloudflare. Se comprobó `/health`, la carga del panel actualizado y la protección de la ruta privada.
- [EXE recorder-43-1](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-43-1) compilado, probado sin Python y verificado tras su publicación.
- [PR #30](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/30) integrada en `4c821f34`. La app reutiliza Chrome al cambiar de modelo, comprueba el ID y usuario de Mi perfil y reintenta las cargas incompletas. La web retoma verificaciones pendientes y la app reenvía resultados interrumpidos sin repetir la comprobación.

## Validación

[Pruebas de main](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44192358626) correctas en Windows y Ubuntu, incluida la grabación de demostración. [Compilación oficial de Windows](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44192358541) correcta.

## En revisión

[PR #31](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/31), rama `fix/recorder-safety-recovery`. Control de Telegram por usuario, acceso por PC con credenciales y sesiones separadas, recuperación de avance del lote y validación de capturas con fotos. Las verificaciones abandonadas caducan tras 30 minutos. La retención de archivos es opcional. La nueva web (v8) y el EXE deben validarse juntos antes de publicarse.

## Publicación mediante Cloudflare en preparación

La rama `feat/cloudflare-publishing` mueve la publicación y el uso de la clave global al Worker. La app conserva el token de Telegram y su sesión de grabación. El nuevo protocolo de escritorio requiere publicar el Worker y el EXE juntos. Validar publicación de texto y foto con una modelo de prueba antes de cambiar producción.

## Siguiente acción

Con el EXE actualizado abierto, cambiar el mismo bot de Lilith (600912674) a Luna (479099623) y pulsar **Verificar Mi perfil** desde el panel. Después probar un comprobante con la sesión real. La comprobación manual no busca posts y el resultado se consulta en la web.
