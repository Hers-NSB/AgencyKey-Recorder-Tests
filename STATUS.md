# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica mensajes reenviados por Telegram mediante AgencyKey y envía un comprobante grabado con Chrome local. La web configura los bots y solicita a la app de Windows la verificación manual de Mi perfil.

## Actualización en revisión

Rama `fix/profile-connection-recovery`, [PR #30](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/30), sin fusionar a main.

- La app conserva una pestaña de Chrome entre verificaciones y vuelve a abrir el contexto cuando cambia la conexión compartida de AgencyKey.
- Las cargas incompletas y los cortes temporales se reintentan hasta completar o cancelar desde la web. Se exige ID y usuario correctos; no se buscan posts durante la comprobación manual.
- La web retoma la comprobación pendiente al recargarse, reintenta las consultas interrumpidas y reutiliza el identificador de solicitud para evitar duplicados.
- La app conserva el resultado en memoria hasta poder enviarlo. El servidor renueva la reserva del trabajo; otra instancia puede retomarlo tras cinco minutos sin comunicación. Una instancia anterior no puede completar la reserva nueva.
- Cambiar la configuración de la modelo invalida el trabajo anterior. Antes de grabar, la navegación y la identificación del perfil se recuperan tras errores temporales; la búsqueda de posts y los controles del video siguen separados.
- El workflow de Windows ahora también compila y comprueba el EXE en las PR, sin crear una release de producción.

## Validación

[CI 44189795770](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44189795770) correcta en Ubuntu y Windows: 205 pruebas Python, 35 del servidor/sesión, 2 de interfaz web y la grabación de demostración. Ocho pruebas locales de recuperación correctas tras añadir la comprobación de JSON truncado. El último commit y el ejecutable se comprueban de nuevo en la CI de la PR.

La prueba visual local no pudo iniciar Chromium por restricciones del entorno; las pruebas visuales se ejecutaron correctamente en GitHub. No se usaron cuentas reales para publicar posts ni enviar videos.

## Publicado actualmente

Web de producción: servicio v6 en https://agencykey-recorder-tests.datosenviados07.workers.dev/admin. EXE publicado: [recorder-40-1](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-40-1). Esta PR prepara el servicio v7; no despliega la web ni sustituye ese EXE.

## Siguiente acción

Revisar el resultado de la CI y la compilación de Windows de la PR #30. Tras integrar y publicar la versión aprobada, cerrar la app anterior y abrir el EXE nuevo. Con la app abierta y el bot detenido, cambiar el mismo bot de Lilith (600912674) a Luna (479099623), verificar Mi perfil desde la web y comprobar la recuperación con conexión lenta. Después probar un comprobante real. Los reportes web y app permanecen independientes.
