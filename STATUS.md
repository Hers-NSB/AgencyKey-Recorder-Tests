# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica mensajes reenviados por Telegram mediante AgencyKey y envía un comprobante grabado con Chrome local. La web configura los bots y solicita la verificación manual del perfil.

## Publicado

- [Web](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin): servicio v6.
- [EXE recorder-40-1](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-40-1): compilado, probado y descargado correctamente.
- Limpieza integrada en main mediante [PR #29](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/29), código `2a7de6c`. README breve; retirados el LEEME duplicado, el ejemplo de configuración sin consumidores, el workflow de prueba antiguo y las conexiones obsoletas con su dependencia y pruebas exclusivas. Los archivos activos y sus pruebas se conservan.

## Funcionamiento que debe conservarse

La verificación manual se consulta y reporta en la web: Verificar Mi perfil → Ver detalle / Descargar reporte. La app debe estar abierta como motor de Chrome; el bot puede estar detenido. Los errores de publicación y grabación se consultan por separado en la app: Ver registro → Guardar registro. La verificación web no escribe en sus diagnósticos ni cambia el estado del bot.

Entradas activas: `app.py` inicia la interfaz; `main.py` ejecuta el bot desde `desktop_runtime.py`; `recorder.py` graba los comprobantes; `cloudflare/worker.mjs` sirve la web y API. La limpieza no eliminó recursos ni secretos de Cloudflare; el Worker generado es idéntico al anterior y no requirió despliegue.

## Validación

[CI del PR](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44135100913): 198 pruebas Python, 33 del servidor/sesión y 2 de interfaz web por sistema, correctas en Ubuntu y Windows, además de la demo. [Compilación de Windows](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44135755791): EXE probado sin comandos Python y archivos publicados comparados con los generados, sin exigir el LEEME eliminado. Las dependencias restantes conservan sus versiones.

## Siguiente acción

Prueba real del usuario: cambiar el mismo bot de Lilith (600912674) a Luna (479099623), verificar el perfil desde la web antes de iniciar el bot y probar un comprobante. Si falla, solicitar el ZIP del flujo correspondiente, web o app. El fallo original de encuadre afectó al post 2899389023; sigue pendiente comprobarlo en su sesión real. No se publicaron posts ni se reenviaron videos en cuentas reales durante el desarrollo.
