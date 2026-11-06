# Validación de la entrega

Fecha: 5 de noviembre de 2026. Windows, Python 3.14 con Tkinter.

## Resultado automático

`python -m unittest discover -v`: **19 pruebas aprobadas**, con subcasos adicionales para los distintos fallos HTTP. Se ejecutaron servidores reales de prueba en localhost. El aislamiento inicial del entorno impedía las conexiones locales; la ejecución autorizada fuera de ese aislamiento completó las pruebas.

Se verificaron respuestas correctas, JSON inválido, identidad/status incorrectos, HTTP 503, desconexión, cuerpo incompleto, conexión rechazada, timeout, lectura del cuerpo completo y timeout total ante entrega por goteo. También estadísticas, CSV sin sobrescritura silenciosa, conexiones nuevas sin proxies, alternancia por ronda, límite, detención, continuidad del otro destino tras fallos, separación de series e aislamiento de una sesión nueva.

Se instanciaron las ventanas Tk y se verificó la notificación nativa de suspensión mediante `SendMessageW(WM_POWERBROADCAST, PBT_APMSUSPEND)`. No se suspendió físicamente la laptop. Esa comprobación física y la revisión visual manual en diferentes escalas de pantalla quedan pendientes en el laboratorio.

## Acceso a los servicios reales

Se realizó una consulta directa de solo lectura por destino desde este equipo a las 14:42 del 5 de noviembre de 2026 (Guatemala), con timeout de comprobación de **1 segundo**:

| Destino | Resultado | HTTP |
|---|---|---|
| MEC, 192.168.88.252:8090 | Timeout | Sin respuesta |
| Cloud, 192.168.88.250:8090 | Timeout | Sin respuesta |

Estos intentos fallidos no permiten comparar el rendimiento ni determinar la causa de inaccesibilidad. No se incorporaron a la sesión inicial de la aplicación. El timeout inicial de la aplicación sigue siendo **5 segundos**.

**La validación final contra MEC y Cloud queda pendiente** con la laptop conectada al Wi-Fi del proyecto. Deben comprobarse las identidades del JSON, las tres condiciones experimentales y las rutas configuradas en el laboratorio. La aplicación no activa ni verifica tc/netem y no se modificaron configuraciones de red ni servicios del proyecto.
