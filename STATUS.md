# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica lotes de Telegram y graba el comprobante con Chrome local. El panel web en Cloudflare administra bots y solicita las verificaciones a la app de Windows.

## Versión disponible

PR [#27](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/27) fusionado con autorización del usuario. Código en main: `2357cc56371824a5fd291fe3a73efc3071c9d6aa`.

Publicado y verificado: [recorder-38-1](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-38-1). Descargar [AgencyKeyRecorderTests.exe](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/download/recorder-38-1/AgencyKeyRecorderTests.exe).

Incluye reintentos de Mi perfil al recargarse el panel, encuadre para feeds cortos sin desplazamiento y exportación del registro con los últimos 20 diagnósticos mediante Ver registro → Guardar registro. Los fallos de verificación web y de grabación guardan etapa, error/traceback, identidad, geometría, imágenes y captura cuando está disponible. Se ocultan campos de entrada y se omiten capturas de inicio de sesión. No se exportan archivos de sesión, cookies, configuración ni HTML.

## Comprobación

199 pruebas Python por sistema pasaron en Ubuntu y Windows, junto con la demo y las pruebas del Worker y del panel. La [compilación publicada](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44121309750) pasó también sus pruebas, la compilación del EXE, su prueba sin comandos Python y la comparación de los archivos descargados con los generados.

SHA-256 del EXE: `1faf46191e26b6c43d1f9b0769f60744e633856692695b922e6e999620ffee2f`.

## Prueba pendiente del usuario

Cerrar el EXE anterior y abrir el nuevo. Actualizar en la app solo descarga configuraciones; no reemplaza el ejecutable. Cambiar el mismo bot de Lilith (600912674) a Luna (479099623, @luna_lonely), ejecutar Verificar Mi perfil desde la web y probar un comprobante. Si falla, abrir Ver registro → Guardar registro y adjuntar `recorder-diagnostico.zip` al chat.

El registro original confirmó las tres publicaciones de Luna; fallaron la primera verificación y después el encuadre del post 2899389023. La causa concreta en la sesión real sigue pendiente de esta prueba. No se realizaron publicaciones ni se reenviaron videos en cuentas reales durante el desarrollo. Cloudflare no requiere otro despliegue: las correcciones se ejecutan en la nueva app local.
