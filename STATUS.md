# Estado actual · 2026-11-18

AgencyKey Recorder Tests ejecuta los bots, la publicación, la grabación y los registros en la PC de Windows. El panel web guarda la configuración y permite solicitar la verificación de Mi perfil con la app abierta y el bot detenido.

## Producción

- [Panel web v8](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin) activo. Incluye la clave global de AgencyKey, los tokens de Telegram, los `@usuarios` autorizados y la verificación de Mi perfil.
- El [EXE oficial](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/latest) se genera desde `main`. El flujo de Windows comprueba el arranque sin Python y compara los archivos publicados con los probados.
- El comprobante en Chrome oculto incluye únicamente los posts del Drop. Telegram permite reintentar la carga o cancelar tras 120 segundos. Las fotos con aviso de DRM se identifican como no verificadas en el comprobante.

## Validación

- Las pruebas cubren publicaciones fijadas ajenas al Drop, fotos que cargan tarde, avisos de DRM, cierre de Chrome y cancelar o reintentar desde Telegram.
- [Pruebas de Windows y Ubuntu](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/workflows/tests.yml) y [compilación del EXE](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/workflows/windows-exe.yml).

## Uso

Consulta [README.md](README.md) para descargar el EXE, configurar los bots y recuperar lotes o comprobantes. Los errores del bot se consultan en el registro de la app y los de verificación en el panel web.
