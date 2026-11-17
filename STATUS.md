# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica los lotes de Telegram y graba un comprobante del perfil usando Chrome local. El panel web en Cloudflare administra bots y solicita verificaciones a la app de Windows.

## Incidencia y alcance autorizado

Después de cambiar el mismo bot de Lilith (600912674) a Luna (479099623, @luna_lonely), el registro del usuario confirma tres publicaciones correctas. Falló primero la verificación del perfil; al repetirla pasó, pero falló el encuadre inicial del post 2899389023. El registro original no demuestra la causa dentro de Chrome.

Rama: `fix/profile-retry-and-diagnostic-export`, basada en main `cb84952`. PR [#27](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/27), abierto y sin fusionar.

- Reintentar Mi perfil hasta tres activaciones, separadas por tres segundos, mientras se comprueba la identidad. Conservar el rechazo de cuentas o modelos distintas.
- Admitir un inicio visible fuera de 95–145 px cuando no hay desplazamiento posible y el comienzo del post tiene espacio visible suficiente. Conservar la comprobación de ID, imágenes y visibilidad.
- Guardar diagnósticos antes de cerrar Chrome al fallar la verificación web o la grabación: etapa, error/traceback, rutas sin parámetros, identidad, geometría, imágenes y captura con campos ocultos. Omitir la captura de inicio de sesión.
- Exportar el registro y los últimos 20 diagnósticos mediante Ver registro → Guardar registro → `recorder-diagnostico.zip`. No exportar almacenamiento del navegador, cookies, configuración ni HTML.

## Validación y límites

175 pruebas sin navegador pasaron durante la implementación. Tras los últimos ajustes, 35 pruebas del área afectada pasaron; compilación Python y `git diff --check` correctos. Se añadieron cuatro regresiones con navegador para recarga, feed corto, inicio oculto y captura del fallo.

Las pruebas locales con navegador están bloqueadas por el entorno: Chromium aborta en `socket() failed: Operation not permitted (1)`. La CI de Ubuntu del PR (ejecución 44118230038, código 48d0b67) ya validó las 199 pruebas Python, incluidas las cuatro regresiones con Chrome, la demo y las pruebas del Worker y del panel. Windows sigue en ejecución. El último ajuste de exportación preserva el JSON al ocultar valores Bearer; sus 35 pruebas locales pasan y la CI debe comprobar el commit final.

No se ha probado contra la sesión real del usuario, no se han creado posts ni reenviado videos.

## Siguiente acción

Revisar los resultados de `.github/workflows/tests.yml` del PR. Tras su aprobación y fusión manual, el workflow existente de main genera el nuevo EXE. El EXE actual no se modifica al pulsar Actualizar (solo descarga configuraciones). Para la prueba real, usar el nuevo EXE, cambiar Lilith → Luna en el mismo bot y ejecutar Verificar Mi perfil y un comprobante. Si falla, exportar el ZIP desde la app y adjuntarlo al chat. No desplegar cambios en Cloudflare: esta corrección se ejecuta en la app local y conserva el contrato con el Worker.
