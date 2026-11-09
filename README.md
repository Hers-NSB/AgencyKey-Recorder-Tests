# AgencyKey Recorder Tests — Chrome

Grabador independiente para comprobar publicaciones existentes en AgencyKey. **No modifica Dropper, no publica posts y no utiliza sus claves.** La activación automática al finalizar un Drop sigue fuera de esta prueba.

## Ejecutable Windows

1. Abre [la última versión privada](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/latest), con tu sesión de GitHub iniciada.
2. Descarga **AgencyKeyRecorderTests.exe** y ábrelo con doble clic. Requiere Windows de 64 bits y **Google Chrome instalado**; no necesita Python ni OBS.
3. Primero selecciona **5. Generar demo**. Usa posts ficticios locales. **No descarga Chromium, otro navegador ni codificadores durante el primer uso.**
4. Usa **1. Configurar posts** para indicar el perfil de AgencyKey y todos los enlaces o IDs de 3–5 publicaciones existentes consecutivas, del más reciente al más antiguo. Un enlace por línea; línea vacía para terminar. Evita posts fijados en la prueba inicial.
5. Usa **2. Conectar AgencyKey**. Inicia sesión en la ventana de Chrome que abre el grabador; después regresa a la consola y pulsa Enter. Esta ventana usa una sesión separada y no abre el perfil personal habitual de Chrome.
6. Usa **3. Grabar prueba local**. Espera sin navegar manualmente en esa ventana. El programa recorre el feed hacia abajo, verifica el orden de los IDs, espera las imágenes visibles y muestra cada post al menos 3 segundos. Los posts largos se recorren por segmentos.
7. Revisa `comprobante.mp4` y `report.json` en la carpeta del resultado. El MP4 es continuo, H.264, **854×480**, sin audio.
8. Usa **4. Enviar último video** cuando quieras enviarlo al bot de pruebas. Introduce el token en la consola, confirma el usuario del bot y envíale desde Telegram el código que se muestra. Solo el chat privado que envió ese código recibirá el video. El token no se guarda. El bot debe estar sin webhook ni otro receptor activo; no se cambian esos ajustes.
9. Repite con unos 30 posts existentes. **0** cierra la app.

Solo la carga de publicaciones reales y el envío a Telegram requieren Internet. Chrome puede realizar su propio tráfico de actualización; el grabador no descarga navegadores. Si falta Chrome, muestra el error y no instala otro.

## Datos y actualizaciones

El EXE conserva configuración, sesión y videos en `%LOCALAPPDATA%\AgencyKeyRecorderTests`, fuera de su carpeta temporal. La ruta aparece en el menú. Cambiar el EXE conserva esos datos. Para cerrar la sesión local, cierra el programa y elimina `private/session.json` dentro de esa carpeta.

Usa el EXE nuevo en lugar del anterior. La carpeta `browsers` de la versión anterior no se utiliza ni se elimina automáticamente. Las sesiones, resultados, tokens y videos no se suben a GitHub. El inicio de sesión no se graba. La demo se etiqueta como simulación si decides enviarla.

El ejecutable incluye una herramienta pequeña para grabar y un codificador FFmpeg mínimo para convertir VP8/WebM a H.264/MP4. Se excluyen del empaquetado el FFmpeg general de imageio y los módulos de instalación de navegadores. No hay descarga oculta de dependencias en el primer uso. Las fuentes exactas y licencias del codificador se publican como descarga opcional `encoder-sources.tar.gz`.

## Comprobaciones y límites

La automatización prueba el feed reciclado, las imágenes de carga tardía, los posts largos, el orden incorrecto, los posts faltantes/fijados, el rechazo de videos incompletos o modificados y el uso de Chrome sin instalar navegadores. GitHub Actions comprueba también el EXE real en Windows: menú, configuración persistente, Chrome instalado, codificador incluido y MP4 completo. Solo entonces publica la descarga. El tamaño final debe ser menor que los 87.121.379 bytes de la primera versión.

La sesión real de AgencyKey debe probarse en tu PC. La interfaz observada usa `postId_ID` y un feed que recicla elementos. El piloto reserva 115 px para el encabezado y desplaza la rueda sobre el centro del feed. Un cambio de interfaz puede requerir ajustes. Solo espera elementos `<img>` visibles; fondos CSS/canvas, reproducción de video y botones para expandir texto no se verifican automáticamente.

Los posts fijados no definen los límites y los posts ajenos intercalados aparecen en el video continuo. La búsqueda inicial tiene límite de 120 segundos y el recorrido de 10 minutos. Una imagen que no carga en 30 segundos aborta el comprobante. No se envían videos incompletos; un fallo no vuelve a publicar nada. El límite local conservador de envío es 49 MB. Antes de repetir un envío con resultado incierto, comprueba Telegram.

## Ejecutar el código fuente

Requiere Python 3.12 y Chrome instalado. `instalar.bat` prepara el entorno y la pequeña herramienta de grabación de Playwright; no descarga Chromium. `iniciar.bat` abre el menú. Para usar el código fuente se conserva imageio-ffmpeg como codificador de respaldo; ese paquete grande **no se incluye en el EXE**.

```powershell
python -m pip install -r requirements.txt
python -m playwright install ffmpeg
python recorder.py check-chrome
python -m unittest discover -s tests -v
python recorder.py demo --headless
```

Comandos: `configure`, `login`, `record`, `send`, `demo`, `check-chrome`; sin comando abre el menú. `--headless` sirve para pruebas sin ventana. `send --report RUTA/report.json` selecciona un comprobante concreto. Para aislar datos de pruebas puede definirse `AGENCYKEY_RECORDER_DATA_DIR`.

## Compilar

`.github/workflows/windows-exe.yml` compila el codificador mínimo desde fuentes fijadas, lo transfiere a Windows, prepara la pequeña herramienta de grabación, ejecuta las pruebas, empaqueta el EXE y publica una versión privada. No descarga otro navegador: los runners usan su Chrome instalado.

Para compilar localmente, descarga el artefacto `minimal-windows-encoder` de una ejecución y extrae su contenido en `vendor/encoder/`. Ejecuta `compilar_windows.bat`, o:

```powershell
python -m pip install -r requirements-build.txt
python -m playwright install ffmpeg
python -m PyInstaller --clean --noconfirm AgencyKeyRecorderTests.spec
python scripts/smoke_exe.py dist/AgencyKeyRecorderTests.exe
```

El codificador de Windows se construye con MinGW en Ubuntu mediante `scripts/build_minimal_ffmpeg.sh`. Sus fuentes fijadas están declaradas en el workflow; el paquete de fuentes publicado incluye ambas bibliotecas, licencias y el script de compilación. El resultado es `dist/AgencyKeyRecorderTests.exe`.

Todo el trabajo pertenece a **Hers-NSB/AgencyKey-Recorder-Tests**.
