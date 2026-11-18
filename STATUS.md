# Estado actual · 2026-11-17

AgencyKey Recorder Tests ejecuta los bots, la publicación, la grabación y los registros en la PC de Windows. El panel web guarda la configuración y permite solicitar la verificación de Mi perfil con la app abierta y el bot detenido.

## Producción

- [Panel web v8](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin) activo. Incluye la clave global de AgencyKey, los tokens de Telegram, los `@usuarios` autorizados y la verificación de Mi perfil.
- [EXE oficial `recorder-47-1`](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-47-1) publicado. La compilación verificó el arranque sin Python y comparó los archivos descargados con los probados.
- [PR #31](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/31) integrada en `0a2ac86`. Guarda el avance del lote, identifica el post fallido y pide su enlace. Comprueba los posts y fotos antes de entregar el video. Las verificaciones abandonadas caducan tras 30 minutos y la retención local es opcional.

## Validación

- El usuario confirmó la prueba con el panel v8 simplificado y el EXE de la PR #31.
- [Pruebas de main](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44213868759) correctas en Windows y Ubuntu. Una captura de diagnóstico falló en la primera ejecución de Windows y pasó en la repetición.
- [Compilación y publicación de Windows](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44213868727) correctas.

## Uso

Consulta [README.md](README.md) para descargar el EXE, configurar los bots y recuperar lotes o comprobantes. Los errores del bot se consultan en el registro de la app y los de verificación en el panel web.
