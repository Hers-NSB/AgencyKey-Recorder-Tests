# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica lotes de Telegram y graba comprobantes con Chrome local. Cloudflare administra bots y solicita las verificaciones manuales a la app de Windows, sin iniciar el bot.

## Cambio autorizado

El usuario pidió que la verificación manual muestre el detalle y permita descargar su reporte desde la web. Exigió que el manejo de errores web y app sea independiente, y autorizó actualizar y publicar ambas versiones.

Rama: `feat/independent-web-verification-reports`, basada en main `2283fb0`. PR pendiente de creación.

- Web: Ver detalle y Descargar reporte en la fila de cada modelo, incluyendo error, etapa, identidad, geometría y captura si está disponible. Resultado persistente y descarga ZIP desde el panel autenticado.
- App: los errores y diagnósticos de publicación/grabación conservan su flujo local. La verificación web usa un directorio temporal, devuelve solo su evidencia y no se añade al ZIP de la app ni cambia el estado del bot.
- La web genera un reporte de estado incluso si la app está desconectada, Chrome no abre o el cliente anterior no devuelve evidencia. Si falla la propia conexión del navegador con el servidor, el panel permite descargar el error observado localmente.
- Los reportes se limitan, se filtran y se guardan cifrados. No se exponen por las rutas de las apps. Cambiar modelo/configuración, reconectar o iniciar otra verificación invalida los reportes anteriores.
- La app actualizada debe estar abierta como motor de Chrome local; no hay que iniciar el bot, publicar ni grabar para verificar desde la web.

## Comprobación

178 pruebas Python sin navegador pasaron; compilación Python y build de Cloudflare correctos. Las pruebas de servidor cubren privacidad, descarga ZIP, rechazo de resultados obsoletos, desconexión y separación respecto a las rutas de las apps. ZIP validado con zipfile de Python: CRC, JSON Unicode y JPEG.

Se añadieron pruebas con navegador para descarga web, persistencia tras recarga, recuperación, estado desconectado, vista móvil y captura JPEG sin diagnósticos locales. Chromium está bloqueado en este entorno por socket() failed: Operation not permitted (1); validar estas pruebas en la CI de Ubuntu y Windows antes de publicar.

## Siguiente acción

Crear PR, comprobar CI, fusionar y publicar web y EXE según autorización del usuario. Desplegar el Worker `agencykey-recorder-tests` conservando bindings, secretos y configuración. No cambiar el esquema de D1. La versión pública anterior es recorder-38-1; no ofrece los reportes de verificación en la web.
