# AgencyKey Recorder Tests

Proyecto independiente para probar comprobantes de publicaciones existentes en AgencyKey. **No modifica Dropper, no utiliza su configuración, no publica posts y no solicita su API.** No hay integración automática con Drops en esta fase.

## Qué hace

- Localiza publicaciones por `id="postId_NUMERO"`, observado en AgencyKey.
- Recorre el feed hacia abajo del post más reciente al más antiguo.
- Comprueba el orden de todos los IDs indicados, incluso con un feed que recicla elementos.
- Espera las imágenes `<img>` visibles y muestra cada post al menos 3 segundos; recorre los posts largos por segmentos.
- Exporta un único MP4 continuo H.264 de **854×480**, sin audio. Elimina del MP4 la preparación y búsqueda inicial; conserva las esperas de carga durante el recorrido.
- Genera un informe con IDs, duración, peso y hash del video.
- Permite enviar un comprobante completo al chat privado de un bot de pruebas, con confirmación del usuario del bot y código de identificación del chat.

## Windows — ejecutable sin Python

1. Abre [la última versión publicada](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/latest) con tu sesión de GitHub.
2. En **Assets**, descarga **AgencyKeyRecorderTests.exe**. El repositorio y sus descargas son privados.
3. Guarda el EXE en su propia carpeta y ábrelo con doble clic. Verás el mismo menú de consola; no requiere instalar Python ni OBS.
4. Primero selecciona **5. Generar demo**. La primera operación que necesita navegador descarga Chromium automáticamente; espera a que termine y mantén Internet conectado.
5. Después usa **1** para configurar los posts existentes, **2** para iniciar sesión en AgencyKey, **3** para grabar y **4** para enviar el video al bot de pruebas. **0** cierra la app.

El EXE guarda configuración, sesión, navegador y videos en `%LOCALAPPDATA%\AgencyKeyRecorderTests`. La ruta exacta aparece al abrir el menú. Los datos se conservan al cerrar o cambiar el EXE: no se guardan en la carpeta temporal del empaquetado. El token de Telegram sigue sin guardarse. Para desconectar la versión EXE elimina únicamente `private/session.json` dentro de esa carpeta.

La descarga de Chromium puede ocupar varios cientos de MB la primera vez; es independiente del tamaño de los videos. El EXE mantiene las funciones del piloto y no activa grabaciones por finalización de Drops.

## Windows — ejecutar el código Python

Esta alternativa requiere Python 3.12 (incluido el lanzador `py`) y acceso a Internet.

1. Descarga el repositorio con **Code → Download ZIP**, extráelo en su propia carpeta, separada de Dropper.
2. Ejecuta **instalar.bat** una vez. Instala dependencias, Chromium y el codificador incluido con imageio-ffmpeg. No requiere OBS.
3. Abre **iniciar.bat**.
4. Primero usa **5. Generar demo**. Crea tres posts ficticios y un video local: no entra en AgencyKey ni envía nada.
5. Usa **1. Configurar posts**. Pega el perfil y los enlaces de 3–5 posts consecutivos existentes, **del más reciente al más antiguo**, uno por línea. Termina con una línea vacía. No uses solo los extremos: hacen falta todos los IDs para detectar omisiones. Los posts de prueba deben estar sin fijar y en ese orden en el feed.
6. Usa **2. Conectar AgencyKey**. Inicia sesión en el navegador que se abre, entra al feed y vuelve a la consola para pulsar Enter. La conexión no graba el login.
7. Usa **3. Grabar prueba local**. No muevas ni navegues manualmente la ventana durante el recorrido. La grabación usa su propia ventana, no captura tu escritorio. Los resultados están en `output/FECHA-ID/` dentro de la carpeta de datos indicada al abrir.
8. Abre `comprobante.mp4` y verifica texto, fotos completas, dirección y límites. `report.json` indica si se completó. El tamaño no se puede garantizar antes de grabar.
9. Si el video está correcto, usa **4. Enviar último video**. Introduce el token del **bot de pruebas** en la consola (no se guarda ni se muestra), confirma su usuario y envíale desde Telegram el código que aparece. Regresa y pulsa Enter. El video va exclusivamente al chat privado que envió ese código. El bot debe estar sin webhook ni otro proceso de recepción activo. El programa no elimina webhooks ni cambia ajustes.
10. Repite con 30 posts existentes. Si vence la sesión, vuelve a la opción 2.

Si la opción 4 selecciona una grabación incompleta, vuelve a grabar o usa `python recorder.py send --report output/FECHA-ID/report.json` para indicar otro comprobante. Nunca se envía automáticamente desde la opción de grabar. La demo se etiqueta como SIMULACIÓN si decides enviarla.

## Pruebas y límites

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
python recorder.py demo --headless
```

Las pruebas automáticas no usan cuentas reales. Cubren un feed reciclado con imágenes de carga tardía, posts altos, orden incorrecto, posts faltantes/fijados y rechazo de videos incompletos o modificados. GitHub Actions ejecuta las pruebas en Windows y Ubuntu. La compilación de Windows comprueba además el EXE real: arranque del menú, configuración persistente, descarga de Chromium desde el propio ejecutable y generación de un MP4 con el codificador incluido; solo después publica la descarga privada.

La compatibilidad real con AgencyKey todavía debe verificarse en tu PC. La captura aportada confirma el identificador de un post, no todos los detalles de navegación. El piloto asume que la rueda del ratón sobre el centro del feed desplaza las publicaciones y reserva 115 px para el encabezado. Un cambio de interfaz puede exigir ajustar estos valores. Imágenes como fondos CSS/canvas y medios que requieren pulsar para cargar no se validan automáticamente. No se reproduce video ni se expanden textos con botones. Si la interfaz requiere esas acciones se ajustará el piloto después de observarlo.

Los posts fijados se excluyen como límites. Los posts ajenos intercalados aparecen en el video continuo. La búsqueda inicial tiene límite de 120 s y el recorrido de 10 minutos; una imagen visible que no carga en 30 s aborta el comprobante. Un fallo borra el video crudo y conserva un informe incompleto; no repite publicaciones. Un error de envío deja el archivo local disponible. Antes de reintentar un envío con resultado incierto, comprueba Telegram.

La sesión se guarda localmente en `private/session.json`; trátala como acceso a tu cuenta. Sesión, configuración local, videos y resultados están excluidos de Git. No añadas tokens al código o a commits. Para desconectar localmente, cierra el programa y elimina `private/session.json`. El token de Telegram se pide solo al enviar y no se persiste. El límite local conservador de envío es 49 MB; no divide un comprobante en varios archivos.

## Comandos

`python recorder.py` abre el menú. También existen `configure`, `login`, `record`, `send` y `demo`. `record --headless` graba sin ventana cuando ya hay sesión válida. El inicio manual es intencional para este piloto; el disparo al finalizar un Drop y la cola entre bots no están implementados.

## Compilar el EXE

Solo en Windows, ejecuta `compilar_windows.bat`, o:

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --noconfirm AgencyKeyRecorderTests.spec
python scripts/smoke_exe.py dist/AgencyKeyRecorderTests.exe
```

El resultado es `dist/AgencyKeyRecorderTests.exe`. El navegador no se incluye en el archivo: se descarga al usarlo. `.github/workflows/windows-exe.yml` compila, prueba, conserva un artefacto y publica una versión nueva con su EXE en Releases. Si falla una prueba, no publica el ejecutable.

Para automatización de pruebas puede definirse `AGENCYKEY_RECORDER_DATA_DIR` con una carpeta de datos separada. `AgencyKeyRecorderTests.exe install-browser` prepara explícitamente el navegador. `AgencyKeyRecorderTests.exe demo --headless` ejecuta la demo sin abrir una ventana de navegador.

## Alcance de cambios

Todo pertenece a **Hers-NSB/AgencyKey-Recorder-Tests**. No existe importación, edición, despliegue ni escritura sobre el repositorio Dropper.
