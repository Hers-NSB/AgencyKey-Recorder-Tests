# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica mensajes reenviados por Telegram mediante AgencyKey y envía un comprobante grabado con Chrome local. El panel web configura bots y permite verificar el perfil antes de iniciarlos.

## Funcionamiento vigente

- La verificación manual se consulta y reporta en la web: Verificar Mi perfil → Ver detalle / Descargar reporte. La app debe estar abierta como motor de Chrome; el bot puede estar detenido.
- Los errores de publicación y grabación se consultan por separado en la app: Ver registro → Guardar registro. La verificación web no escribe en sus diagnósticos ni cambia el estado del bot.
- [Web publicada](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin): servicio v6. [EXE publicado](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-39-1): recorder-39-1.

## Limpieza aprobada

Rama `docs/readme-y-limpieza`, basada en main `11e5987`. El usuario aprobó dejar el README breve y retirar LEEME-EXE.txt con sus referencias de empaquetado, config.example.json, el workflow de prueba antiguo, browserDriver y su dependencia, y connect_session/session_ready con sus pruebas antiguas. Se conservan el código activo, las pruebas útiles y la compilación. El descriptor de despliegue ya no declara el navegador remoto retirado; no se han eliminado recursos ni secretos de Cloudflare.

## Comprobación

174 pruebas Python sin navegador y 33 de servidor/sesión pasaron. npm ci, build de Cloudflare, compilación Python, YAML de publicación y git diff --check correctos. El Worker generado es idéntico al anterior; las versiones de las dependencias restantes no cambiaron. La CI debe comprobar Chrome y la interfaz en Ubuntu y Windows antes de integrar la limpieza en main.

## Siguiente acción

Crear el PR de esta rama, verificar CI e integrar la limpieza aprobada en main. El workflow existente compilará el EXE y verificará sus descargas sin exigir el LEEME eliminado. La prueba real del usuario de cambio Lilith → Luna sigue pendiente; si falla, solicitar el ZIP del flujo correspondiente, web o app.
