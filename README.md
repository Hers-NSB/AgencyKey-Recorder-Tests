# AgencyKey Recorder Tests

Aplicación de Windows que publica los mensajes reenviados a un bot de Telegram en el muro de la modelo asignada mediante AgencyKey y envía un comprobante en video.

## Requisitos y descarga

- Windows de 64 bits, Google Chrome instalado e internet.
- Una API de AgencyKey y un bot de Telegram.
- [Descargar la última versión](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/latest). El EXE no requiere instalar Python.

## Primeros pasos

1. Entra al [panel web](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin) y configura la API de AgencyKey, las contraseñas de administrador y de las apps, y la modelo de cada bot.
2. Abre el EXE, pulsa **Actualizar** e introduce la contraseña de las apps cuando se solicite.
3. Con la app abierta, pulsa **Conectar AgencyKey** en la web e inicia sesión en la ventana de Chrome.
4. Pulsa **Verificar Mi perfil** desde la web. No hace falta iniciar el bot para comprobar la modelo.
5. En la app, selecciona el bot y pulsa **Iniciar bot**. En Telegram pulsa **Iniciar**, reenvía los mensajes y elige **Publicar normal** o **Publicar lento**.

Se admiten mensajes de texto y fotos individuales con texto. El lote se publica del último mensaje reenviado al primero. Después se envían el video y la confirmación final al mismo chat.

La app debe permanecer abierta para verificar, publicar y grabar. **Actualizar** descarga configuraciones; para actualizar la aplicación hay que descargar y abrir el nuevo EXE.

## Errores y reportes

| Dónde ocurre | Dónde consultar y descargar el reporte |
| --- | --- |
| Verificación manual desde la web | En la fila de la modelo: **Ver detalle** o **Descargar reporte**. |
| Publicación o grabación en la app | **Ver registro → Guardar registro** en la app. |

Los reportes de web y app son independientes. Si falla la grabación, usa **Repetir grabación** en Telegram: no vuelve a publicar el lote. Si falla una publicación, **Continuar** permite reanudar tras indicar el enlace del post.

## Estado del proyecto

Consulta [STATUS.md](STATUS.md) para conocer la versión publicada, las comprobaciones realizadas y la siguiente tarea pendiente.
