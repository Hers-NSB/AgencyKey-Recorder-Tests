# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica lotes de Telegram y graba comprobantes con Chrome local. La web administra bots y solicita la verificación manual sin iniciar el bot.

## Versiones publicadas

PR [#28](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/28) fusionado y publicado con autorización del usuario. Código: main `422dd555d3230a342f05465568aa841b261ba14f`.

- [Panel web](https://agencykey-recorder-tests.datosenviados07.workers.dev/admin), versión de servicio 6. Despliegue Cloudflare `95186fb9-943f-4c09-8c4a-92aa372cb925`, versión `09903858-827e-4630-afdc-7ad34ff42fe7`. Bindings y secretos conservados, sin migración D1.
- [EXE recorder-39-1](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/download/recorder-39-1/AgencyKeyRecorderTests.exe), publicado y verificado. SHA-256: `48e5f5bd5e835af393d4784d795498d71b0d180a4eb46c538ba0bea12539e811`.

## Separación exigida por el usuario

La verificación manual es una función de la web, previa a iniciar el bot, publicar y grabar. Su resultado, Ver detalle y Descargar reporte aparecen en la fila de cada modelo. No remitir al usuario a Guardar registro de la app para este flujo.

La app actualizada debe permanecer abierta como motor de Chrome local, pero el bot puede estar detenido. La evidencia web se recoge en un directorio temporal y se devuelve a la web; no entra al ZIP de la app ni cambia el estado del bot. Los errores de publicación y grabación siguen en Ver registro → Guardar registro de la app.

El Worker conserva el último resultado por modelo y el diagnóstico cifrado, disponible solo para administradores. Cambiar configuración/modelo, reconectar AgencyKey o iniciar otra comprobación invalida los reportes anteriores. Las respuestas tardías no sobrescriben una nueva verificación. Un fallo de conexión del navegador con el panel tiene estado propio `web_request_error`, sin atribuirlo a Chrome o a la app; también se puede descargar su reporte local desde la web. Los estados sin evidencia de Chrome lo indican expresamente.

## Comprobación

La [CI del código publicado](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44130561550) pasó en Ubuntu y Windows: 202 pruebas Python, 35 del servidor/sesión y 2 de interfaz web por sistema, además de la demo. La prueba de interfaz comprueba detalle, ZIP válido con captura y CRC mediante zipfile de Python, recarga, recuperación, desconexión de la app, fallo de conexión web y vista móvil.

La [compilación del EXE](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44131163409) pasó sus pruebas, compilación, prueba del EXE sin comandos Python y comparación de los archivos descargados con los generados. Producción: health 200/versión 6, panel con controles nuevos y reporte protegido con 401 sin sesión.

## Siguiente prueba del usuario

Cerrar el EXE anterior, abrir recorder-39-1 y recargar la web. Pulsar Verificar Mi perfil antes de iniciar el bot; usar Ver detalle o Descargar reporte en esa misma fila si falla. Adjuntar `verificacion-web-ID.zip` al chat. Para errores de grabación/publicación usar el ZIP de la app, por separado.

Probar el cambio Lilith (600912674) → Luna (479099623, @luna_lonely) con el mismo bot. El fallo original de encuadre afectó al post 2899389023; no se ha reproducido contra la sesión real del usuario. Durante el desarrollo no se publicaron posts ni se reenviaron videos en sus cuentas.
