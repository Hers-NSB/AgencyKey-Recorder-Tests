- Verificar Mi perfil compara la cuenta abierta en Chrome con la modelo asignada al bot, incluso con el muro vacío.
- El grabador verifica la misma identidad y busca las publicaciones del lote al terminar de publicar.
- El panel muestra las cuentas esperada y abierta cuando detecta una discrepancia.

## Prueba de verificación en Windows

- La app independiente confirmó con una sesión real la secuencia Luna → Sheryn → Luna. En el primer acceso a Luna, el iframe quedó oculto y reabrir el mismo perfil en la misma pestaña devolvió `ready`.
- El grabador conserva la pestaña preparada para el lote y reabre la misma ruta una vez ante `profile_unverified`. Antes de grabar, exige que coincidan el ID y el usuario. El grabador abre su pestaña con la sesión compartida guardada por el flujo de conexión.
- El botón **Verificar Mi perfil** del panel web también reabre esa ruta una vez ante `profile_unverified` cuando la solicitud la atiende el ejecutable de esta versión. El verificador conserva la comprobación de ID y usuario.
- Pendiente con una sesión real del grabador: verificar **Mi perfil** desde el panel antes de usar el bot en cada paso de Luna → Sheryn → Luna. Si el panel confirma la modelo, grabar y comprobar que el video corresponda a la cuenta asignada.
- Para retomar en otro chat, consultar la rama `test/recorder-profile-retry` y buscar la versión preliminar **Prueba de verificación de perfil** en Releases.
