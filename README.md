# AgencyKey Recorder Tests

AgencyKey Recorder Tests es una app de Windows que toma los mensajes que reenvías a un bot de Telegram, los publica en el muro de OnlyFans de la modelo asignada mediante AgencyKey y envía al mismo chat un comprobante en video. Un **Drop** es un lote de mensajes reenviados. La app usa Google Chrome instalado en la PC para grabar las publicaciones y el panel web sirve para configurar los bots y conectar AgencyKey.

El proyecto se basa en Dropper y funciona con su propia app, bots y servidor.

## Qué cambió en esta actualización

| Función | Qué verás |
| --- | --- |
| Verificación de Mi perfil | Al vincular una modelo o conectar AgencyKey, el panel usa Chrome para abrir Mi perfil y comparar la cuenta que muestra Chrome con la modelo asignada. La comprobación funciona con el muro vacío y se renueva al cambiar de modelo. El grabador verifica la misma identidad antes de buscar el primer post del lote. |
| Grabación en segundo plano | La app prepara Chrome y abre el perfil durante la publicación del lote. |
| Ritmo de publicación | **Publicar normal** (11 segundos) y **Publicar lento** (22 segundos) aparecen al recibir el primer mensaje válido. |
| Formato | El bot conserva el texto original y la foto cuando viene adjunta. Las publicaciones de solo texto y las que incluyen una foto solicitan un vencimiento de un día. |

Ambos ritmos publican del último mensaje reenviado al primero.

## Uso en Windows

1. Descarga el EXE para Windows. La [última versión privada publicada](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/latest) se descarga por separado. El EXE requiere Windows de 64 bits y Google Chrome instalado.
2. Configura el entorno nuevo en https://agencykey-recorder-tests.datosenviados07.workers.dev/admin: contraseña de administrador, API de AgencyKey, contraseña de las apps y bots con sus modelos. Usa tokens propios de los bots de pruebas; el token de un mismo bot no puede ser atendido por dos apps a la vez. Puedes usar la misma API de AgencyKey y las mismas asignaciones de modelo.
3. Abre el EXE y pulsa **Actualizar** la primera vez. Si te pide acceso, introduce la contraseña de las apps. Puedes recordarla con el Administrador de credenciales de Windows. Al volver a abrir, la app usa los perfiles guardados y comprueba si hay cambios cada 30 segundos. Si aparece **Hay cambios disponibles**, pulsa **Actualizar** para descargarlos. La app también descarga cambios al detectar que afectan a un bot activo. Si cambias su modelo, la app detiene el bot y aplica el perfil nuevo para el siguiente inicio.
4. Deja abierta la app de Windows y pulsa **Conectar AgencyKey** en el panel web. La app abrirá una ventana de Chrome en esa PC. Inicia sesión en AgencyKey y espera la confirmación del panel. El panel comprueba los perfiles pendientes automáticamente. Si hay un fallo, verás el resultado en la fila de la modelo y podrás usar **Verificar Mi perfil** para reintentar. La misma sesión sirve para las modelos a las que la cuenta tiene acceso. La conexión, la verificación y la grabación usan Chrome en la PC, sin consumir minutos de Cloudflare Browser Run.
5. En la app selecciona el bot y pulsa **Iniciar bot**. La app recupera la sesión compartida de la web en memoria: cerrar el EXE no la elimina. Puedes usar los botones web con el EXE abierto aunque todavía no hayas iniciado ningún bot.
6. En Telegram pulsa **Iniciar**, reenvía fotos individuales con sus textos o mensajes de solo texto. Pulsa **Publicar normal** (11 segundos entre publicaciones) o **Publicar lento** (22 segundos). Si el servicio limita temporalmente el ritmo, Telegram indica cuándo puedes continuar. El bot publica del último mensaje reenviado al primero. Mientras publica, la app prepara Chrome en segundo plano. Al terminar, actualiza el perfil si el primer post aún no aparece y empieza a grabar cuando verifica ese ID y las fotos visibles. Durante el recorrido verifica los demás IDs y sus imágenes.
7. El MP4 completo a 480p se envía al chat privado que inició el Drop. **Solo después de confirmar su entrega** se envía el resumen «Drop finalizado». El tiempo total comprende desde pulsar Publicar hasta la entrega del video: publicación, carga del feed, grabación, conversión y subida.

La app muestra un panel mientras descarga configuraciones, progreso del comprobante y un registro desplegable en un panel desplazable, sin vista previa. La web usa paneles de confirmación para las acciones que requieren confirmación. Si AgencyKey caduca o falta acceso a un feed, reconecta desde la web; un video incompleto no se envía.

La prueba publica contenido real en la modelo configurada. Las pruebas de CI usan datos simulados y nunca publican en cuentas reales.

## Funciones conservadas de Dropper

- Interfaz de escritorio, varios bots independientes, aviso de cambios cada 30 segundos y descarga manual de perfiles, inicio y parada por bot, registro exportable.
- Administración web con API global de AgencyKey, modelo fija por bot y un bot por modelo.
- Reenvío de fotos con texto y mensajes de solo texto, rechazo de álbumes y caducidad de un día para publicaciones con foto o solo texto.
- Progreso de publicación, contadores de sesión, pausa ante errores, copia del post fallido y continuación tras pegar su enlace de OnlyFans y limpieza de mensajes de preparación.
- Contraseñas de administrador y apps independientes, sesiones seguras, cifrado de claves en D1 y claves descargadas solo a memoria.

## Recuperación y comprobantes

Un fallo de grabación o envío no vuelve a publicar los posts. La app muestra la etapa y el error; los informes y videos completos se conservan localmente.

- **Repetir grabación** aparece en el teclado de Telegram cuando falla la grabación y vuelve a grabar los posts del mismo Drop.
- Al abrir un Drop, **Cancelar Drop** aparece tras recibir el primer mensaje.
- Chrome dispone de dos minutos por intento para abrir el perfil. Durante el recorrido, cada post verificado reinicia la espera de tres minutos sin avance.
- Si Telegram perdió la respuesta durante la subida, comprueba primero el chat. Pulsa **Reenviar video** en el teclado para confirmar el reenvío.
- Si falla un post, **Continuar** muestra una copia y pide el enlace individual de OnlyFans. Al recibirlo, el bot reanuda el lote y genera el comprobante al terminar.
- **Detener** detiene nuevas publicaciones y solicita cancelar la grabación en curso. Los Drops de publicación pendientes siguen siendo memoria de sesión, igual que en Dropper; los trabajos de comprobante conservan IDs y estado para recuperarlos desde el teclado tras reiniciar.

La app muestra la etapa del fallo y, si corresponde, el ID de la publicación buscada. Los errores de Telegram distinguen certificados, proxy, DNS y tiempos de espera en el modo de envío manual. La app integrada usa también certificados y proxy de Windows y muestra la etapa y el tipo de fallo, sin registrar tokens. No se desactiva la verificación HTTPS.

Si falla **Verificar Mi perfil** desde la web o la grabación, la app guarda automáticamente el diagnóstico antes de cerrar Chrome. En la app, abre **Ver registro → Guardar registro** y comparte `recorder-diagnostico.zip`: incluye el registro y los últimos 20 diagnósticos locales, con error, etapa, perfil esperado y detectado, paneles visibles, posiciones de posts, carga de imágenes y una captura de la página cuando está disponible. Las capturas ocultan campos de entrada y se omiten en el inicio de sesión; pueden mostrar el contenido del perfil. No se exportan archivos de sesión, cookies, configuración ni HTML. Si Chrome se cerró o no respondió, el informe indica por qué faltan datos o captura.

## Datos independientes

El EXE guarda trabajos e informes en `%LOCALAPPDATA%\AgencyKeyRecorderTests`; no usa la entrada de acceso de Dropper. El servidor usa un Worker, una base D1, cookies y secretos propios. No se han copiado tokens de bots de producción ni las contraseñas privadas de Dropper: se configuran en la web nueva.

La grabación solo se considera completa si se verificaron todos los IDs, sus imágenes visibles y los fotogramas de inicio y cierre en la misma pestaña. No se envían videos incompletos o alterados. Si el panel se oculta, cambia de pestaña o se recarga, se rechaza el recorrido. No se comprueban fondos CSS/canvas, reproducción de videos DRM ni expansión automática de textos. El límite conservador de subida es 49 MB.

## Herramientas de grabación manual

El modo original sigue disponible desde consola:

```powershell
.\AgencyKeyRecorderTests.exe menu
.\AgencyKeyRecorderTests.exe record --headless
.\AgencyKeyRecorderTests.exe record --show-browser
.\AgencyKeyRecorderTests.exe demo --headless
```

Al abrir el EXE con doble clic, la consola técnica se oculta automáticamente. El progreso y los errores se ven en la app. La app integrada graba con Chrome en segundo plano. Si falla, la app muestra el error y la etapa. La herramienta manual conserva `--show-browser` para depuración y permite configurar IDs, conectar una sesión y enviar un comprobante verificado.

## Desarrollo y compilación

Python 3.12, Node.js 24 y Chrome instalado. Instala `requirements-build.txt`, ejecuta `npm ci --prefix cloudflare`.

```powershell
python -m unittest discover -s tests -v
node --test cloudflare/worker.test.mjs cloudflare/recording-session.test.mjs
node --test cloudflare/admin.test.mjs
python desktop.py --smoke-test
python -m PyInstaller --clean --noconfirm AgencyKeyRecorderTests.spec
```

El codificador mínimo se construye y verifica en `.github/workflows/windows-exe.yml`. El EXE incluye la app, los perfiles de subida de respaldo, el controlador Chrome y el codificador; no descarga navegadores ni codificadores en el primer uso. Las fuentes y licencias del codificador se publican junto al EXE.

## Servidor independiente

`cloudflare/worker.mjs`, `admin-page.mjs` y `schema.sql` conservan la administración de Dropper adaptada a una identidad y base de datos distintas. Compila con `npm run build --prefix cloudflare`. El Worker requiere el binding D1 `DB` y los secretos `ACCESS_TOKEN`, `ENCRYPTION_KEY`, `ADMIN_TOKEN`; `ADMIN_SETUP` contiene el enlace inicial de un solo uso. No guardes esos secretos en git ni reutilices bindings de Dropper. La clave AES-GCM no debe rotarse sin recifrar los datos. El panel web encola las solicitudes de conexión y verificación en D1. La app de Windows autenticada las recoge y ejecuta en Chrome local. La solicitud caduca si ninguna app la recibe. La conexión solo requiere iniciar sesión en la ventana local. Cada solicitud de verificación usa la sesión compartida y la ruta de su modelo. Las renovaciones de la sesión compartida usan revisión para no sobrescribir una reconexión o renovación más reciente.

La referencia de origen es Dropper en el commit `1937fdb69988aa532806f5ad7967cde84a6d0669`. Las modificaciones y pruebas de integración se mantienen únicamente aquí.

