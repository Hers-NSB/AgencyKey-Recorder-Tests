# AgencyKey Recorder Tests — web, app y bots independientes

Adaptación de Dropper con grabación automática al terminar cada Drop. Todo el código pertenece a **Hers-NSB/AgencyKey-Recorder-Tests**. Dropper y su servidor permanecen separados.

## Uso en Windows

1. Descarga **AgencyKeyRecorderTests.exe** desde la última versión privada. Requiere Windows de 64 bits y Google Chrome instalado; no necesita Python, OBS ni descargar otro navegador.
2. Configura el entorno nuevo en https://agencykey-recorder-tests.datosenviados07.workers.dev/admin: contraseña de administrador, API de AgencyKey, contraseña de las apps y bots con sus modelos. Usa tokens propios de los bots de pruebas; el token de un mismo bot no puede ser atendido por dos apps a la vez. Puedes usar la misma API de AgencyKey y las mismas asignaciones de modelo.
3. Abre el EXE e introduce la contraseña de las apps del entorno nuevo. Se puede recordar mediante Windows Credential Manager, en una entrada independiente de Dropper.
4. En **la web**, pulsa **Conectar AgencyKey** en el panel de sesión compartida. Abre el enlace de conexión, inicia sesión y deja visible el feed de la modelo indicada. La web detecta la conexión y guarda la sesión automáticamente y cifrada. Esa cuenta debe tener acceso a las modelos que vayas a grabar. Si añades otra modelo autorizada, reutiliza la misma sesión; no hace falta conectar una cuenta por modelo.
5. En la app selecciona el bot y pulsa **Iniciar bot**. La app recupera la sesión compartida de la web en memoria: cerrar el EXE no la elimina. No hay botones para conectar ni guardar sesiones en la app.
6. En Telegram envía `/start`, reenvía fotos individuales con sus textos y pulsa **Publicar**. Al acabar las publicaciones, la app espera el feed, recorre los posts del lote para precargar sus imágenes y vuelve al primer post antes de iniciar el video. Los feeds virtuales descargan nodos fuera de pantalla: durante la grabación se sigue verificando cada imagen visible.
7. El MP4 completo a 480p se envía al chat privado que inició el Drop. **Solo después de confirmar su entrega** se envía el resumen «Drop finalizado». El tiempo total comprende desde pulsar Publicar hasta la entrega del video: publicación, carga del feed, grabación, conversión y subida.

La app muestra un panel mientras descarga configuraciones, progreso del comprobante y un registro desplegable; no muestra vista previa. La web usa paneles de confirmación para las acciones que requieren confirmación. Si AgencyKey caduca o falta acceso a un feed, reconecta desde la web; un video incompleto no se envía.

La prueba publica contenido real en la modelo configurada. Las pruebas de CI usan datos simulados y nunca publican en cuentas reales.

## Funciones conservadas de Dropper

- Interfaz de escritorio, varios bots independientes, sincronización cada 30 segundos, inicio y parada por bot, registro exportable.
- Administración web con API global de AgencyKey, modelo fija por bot y un bot por modelo.
- Fotos y textos en orden, rechazo de álbumes, intervalo de 11 segundos por modelo y vencimiento de fotos de un día.
- Progreso de publicación, contadores de sesión, pausa ante errores, copia para carga manual, continuación sin reenviar el post manual y limpieza de mensajes de preparación.
- Contraseñas de administrador y apps independientes, sesiones seguras, cifrado de claves en D1 y claves descargadas solo a memoria.

## Recuperación y comprobantes

Un fallo de grabación o envío no vuelve a publicar los posts. La app muestra la etapa y el error; los informes y videos completos se conservan localmente.

- `/video`: genera de nuevo o reintenta el comprobante del último Drop. Los envíos confirmados no se duplican.
- Si Telegram perdió la respuesta durante la subida, comprueba primero el chat. `/video reenviar` confirma que quieres volver a enviar ese comprobante.
- Los posts confirmados manualmente necesitan su ID para poder incluirlos en el video: `/id NUMERO ID_O_ENLACE`, por ejemplo `/id 2 2873212320`. Después usa `/video`. El programa no inventa IDs ni vuelve a publicar esos posts.
- **Detener** detiene nuevas publicaciones y solicita cancelar la grabación en curso. Los Drops de publicación pendientes siguen siendo memoria de sesión, igual que en Dropper; los trabajos de comprobante conservan IDs y estado para recuperarlos con `/video` tras reiniciar.

Los errores de Telegram distinguen certificados, proxy, DNS y tiempos de espera en el modo de envío manual. La app integrada usa también certificados y proxy de Windows y muestra la etapa y el tipo de fallo, sin registrar tokens. No se desactiva la verificación HTTPS.

## Datos independientes

El EXE guarda trabajos e informes en `%LOCALAPPDATA%\AgencyKeyRecorderTests`; no usa la entrada de acceso de Dropper. El servidor usa un Worker, una base D1, cookies y secretos propios. No se han copiado tokens de bots de producción ni las contraseñas privadas de Dropper: se configuran en la web nueva.

La grabación solo se considera completa si se verificaron todos los IDs, sus imágenes visibles y los límites del video. No se envían videos incompletos o alterados. Si el panel se oculta, cambia de pestaña o se recarga, se rechaza el recorrido. No se comprueban fondos CSS/canvas, reproducción de videos DRM ni expansión automática de textos. El límite conservador de subida es 49 MB.

## Herramientas de grabación manual

El modo original sigue disponible desde consola:

```powershell
.\AgencyKeyRecorderTests.exe menu
.\AgencyKeyRecorderTests.exe record --headless
.\AgencyKeyRecorderTests.exe record --show-browser
.\AgencyKeyRecorderTests.exe demo --headless
```

Al abrir el EXE con doble clic, la consola técnica se oculta automáticamente. El progreso y los errores se ven en la app. La app integrada graba sin ventana. La herramienta manual conserva `--show-browser` para depuración y permite configurar IDs, conectar una sesión y enviar un comprobante verificado.

## Desarrollo y compilación

Python 3.12, Node.js 24 y Chrome instalado. Instala `requirements-build.txt`, ejecuta `npm ci --prefix cloudflare` y prepara la herramienta de video con `python -m playwright install ffmpeg` (no instala navegadores).

```powershell
python -m unittest discover -s tests -v
node --test cloudflare/worker.test.mjs cloudflare/recording-session.test.mjs
node --test cloudflare/admin.test.mjs
python desktop.py --smoke-test
python -m PyInstaller --clean --noconfirm AgencyKeyRecorderTests.spec
```

El codificador mínimo se construye y verifica en `.github/workflows/windows-exe.yml`. El EXE incluye la app, los perfiles de subida de respaldo, el controlador Chrome y los codificadores; no descarga navegadores ni codificadores en el primer uso. Las fuentes y licencias del codificador se publican junto al EXE.

## Servidor independiente

`cloudflare/worker.mjs`, `admin-page.mjs` y `schema.sql` conservan la administración de Dropper adaptada a una identidad y base de datos distintas. Compila con `npm run build --prefix cloudflare`. El Worker requiere el binding D1 `DB` y los secretos `ACCESS_TOKEN`, `ENCRYPTION_KEY`, `ADMIN_TOKEN`; `ADMIN_SETUP` contiene el enlace inicial de un solo uso. No guardes esos secretos en git ni reutilices bindings de Dropper. La clave AES-GCM no debe rotarse sin recifrar los datos. La conexión desde la web requiere además un binding Browser Run llamado `BROWSER` y `compatibility_flags: ["nodejs_compat"]` (ver `cloudflare/deployment.json`). Los enlaces temporales de conexión se entregan solo al administrador autenticado, no se registran ni guardan. El navegador remoto se cierra al guardar o cancelar; las sesiones pendientes caducan. Las renovaciones de la sesión compartida usan revisión para no sobrescribir una reconexión o renovación más reciente.

La referencia de origen es Dropper en el commit `1937fdb69988aa532806f5ad7967cde84a6d0669`. Las modificaciones y pruebas de integración se mantienen únicamente aquí.

