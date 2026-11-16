# Diagnóstico de Mi perfil

1. En Windows, con Python 3.12 y Google Chrome, ejecuta `instalar.bat` desde la raíz del repositorio.
2. Abre `diagnostico_perfil/iniciar.bat`. Inicia sesión en la ventana de AgencyKey y pulsa Enter en el diagnóstico.
3. Introduce el ID o enlace de la modelo que asignaste al bot y su `@usuario`. Repite con una segunda modelo y vuelve a la primera.
4. Compara el resultado y los perfiles reconocidos en cada prueba. Pulsa Enter en el campo de ID para salir.

Cada prueba abre Chrome sin ventana con un contexto nuevo y la misma copia en memoria de la sesión iniciada para el diagnóstico. Es el mismo verificador que usa el panel web. La herramienta consulta los perfiles en AgencyKey sin contactar Telegram ni cambiar la configuración del bot. Si el panel falla y el diagnóstico funciona, la diferencia puede estar en la sesión guardada o los datos que el panel envía a la PC.

La consola muestra los cambios de ruta, visibilidad del iframe, encabezado, opción «Mi perfil» y los pares de ID y usuario que cumplen el filtro del verificador. Un encabezado visible sin un par reconocido ayuda a revisar la ruta del iframe. Dos pares reconocidos a la vez impiden que el verificador acepte la identidad. La sesión y los resultados no se escriben en archivos.
