# Estado actual · 2026-11-17

AgencyKey Recorder Tests publica mensajes reenviados por Telegram mediante AgencyKey y envía un comprobante grabado con Chrome local. La web configura los bots y solicita a la app de Windows la verificación manual de Mi perfil.

## Actualización en revisión

Rama `fix/profile-connection-recovery`, [PR #30](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/pull/30), sin fusionar a main.

- La app conserva una pestaña de Chrome entre verificaciones y vuelve a abrir el contexto cuando cambia la conexión compartida de AgencyKey.
- Las cargas incompletas y los cortes temporales se reintentan hasta completar o cancelar desde la web. Se exige ID y usuario correctos; no se buscan posts durante la comprobación manual.
- La web retoma la comprobación pendiente al recargarse, reintenta las consultas interrumpidas y reutiliza el identificador de solicitud para evitar duplicados.
- La app conserva el resultado en memoria hasta poder enviarlo. El servidor renueva la reserva del trabajo; otra instancia puede retomarlo tras cinco minutos sin comunicación. Una instancia anterior no puede completar la reserva nueva.
- Cambiar la configuración o la conexión de la modelo invalida el trabajo anterior, incluso si se repite una solicitud cuya respuesta se perdió. Una nueva sesión de administrador puede retomar las verificaciones recuperables. Antes de grabar, la navegación y la identificación del perfil se recuperan tras errores temporales; la búsqueda de posts y los controles del video siguen separados.
- El workflow de Windows ahora también compila y comprueba el EXE en las PR, sin crear una release de producción.

## Validación

[CI final 44191023652](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44191023652) correcta en Ubuntu y Windows: 206 pruebas Python, 35 del servidor/sesión, 2 de interfaz web y la grabación de demostración. El build del Worker también es correcto.

[Compilación de Windows 44190385391](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44190385391) correcta: EXE compilado y probado sin comandos Python. [Descarga de prueba](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/actions/runs/44190385391/artifacts/14376701417). El código Python de ese EXE coincide con el de la revisión final; las modificaciones posteriores afectan al Worker, sus pruebas y este estado. La CI vuelve a compilar el último commit en el workflow 44191023562.

La prueba visual local no pudo iniciar Chromium por restricciones del entorno; las pruebas visuales se ejecutaron correctamente en GitHub. No se usaron cuentas reales para publicar posts ni enviar videos.

## Publicado actualmente

Web de producción: servicio v6 en https://agencykey-recorder-tests.datosenviados07.workers.dev/admin. EXE publicado: [recorder-40-1](https://github.com/Hers-NSB/AgencyKey-Recorder-Tests/releases/tag/recorder-40-1). Esta PR prepara el servicio v7; no despliega la web ni sustituye ese EXE.

## Siguiente acción

Revisar e integrar la PR #30 y desplegar el servicio v7 junto con la app actualizada. Tras publicar la versión aprobada, cerrar la app anterior y abrir el EXE nuevo. Con la app abierta y el bot detenido, cambiar el mismo bot de Lilith (600912674) a Luna (479099623), verificar Mi perfil desde la web y comprobar la recuperación con conexión lenta. Después probar un comprobante real. Los reportes web y app permanecen independientes.
