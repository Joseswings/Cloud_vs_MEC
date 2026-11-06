# Comparador IoT MEC–Cloud para Windows

Aplicación de escritorio para Windows que compara el tiempo de respuesta de dos servicios IoT mediante peticiones HTTP a `GET /api/iot/health`. Muestra las mediciones de MEC y Cloud en una gráfica común, calcula mediana y P95 y permite exportar los intentos a CSV.

## Ejecutar en Windows

Si tienes `Cloud_vs_MEC.exe`, ábrelo con doble clic. El ejecutable es para Windows x64 e incluye Python y Tkinter. Consulta [EMPAQUETADO.md](EMPAQUETADO.md) para reconstruirlo.

Para ejecutar desde el código, necesitas **Python 3.10 o superior** con Tcl/Tk. Abre PowerShell en la carpeta raíz del repositorio y ejecuta:

```powershell
py -3 --version
py -3 -m tkinter
py -3 app.py
```

El segundo comando abre una ventana de prueba de Tkinter. Ciérrala para continuar. La aplicación usa la biblioteca estándar de Python.

## Uso

1. Conecte la laptop al Wi-Fi del proyecto. Los destinos iniciales son MEC `http://192.168.88.252:8090/api/iot/health` y Cloud `http://192.168.88.250:8090/api/iot/health`.
2. Seleccione Base, Cloud degradado o Recuperado. Ajuste URL, intervalo, timeout y límite antes de iniciar.
3. Pulse **Iniciar**. Los valores iniciales son intervalo de 1 segundo, timeout de 5 segundos y 100 intentos por destino **en toda la sesión**, sumando condiciones. Aumente el límite para continuar si se alcanzó.
4. **Detener** impide nuevas consultas. El intento en curso puede finalizar hasta el timeout. Iniciar vuelve a estar disponible al terminar ese trabajador.
5. Cambiar la condición detiene las nuevas consultas, deja finalizar el intento actual con su etiqueta anterior y abre una serie vacía. Pulse Iniciar para medir la nueva condición. Cada cambio, incluso al regresar a Base, obtiene un identificador de serie distinto.
6. **Exportar CSV** guarda todos los intentos ya completados de todas las series de la sesión. Puede exportar durante una prueba; ese archivo es una instantánea y no incluirá los intentos que terminen después.
7. **Nueva sesión** solicita confirmar el descarte y genera otro UUID. Exporte antes de descartar. Un intento antiguo todavía en curso jamás se incorpora a la nueva sesión; se espera su finalización antes de volver a iniciar.

“Cloud degradado” es exclusivamente una etiqueta. La aplicación **no activa ni verifica tc/netem**. La ruta de red y la degradación deben estar configuradas externamente en el laboratorio. La app tampoco verifica que Cloud cruce un tramo determinado.

Las URLs quedan bloqueadas durante la ejecución. Cambiar una URL entre ejecuciones abre una serie estadística nueva al iniciar. El nombre de condición en CSV incluye el número de serie, por ejemplo `Base · serie 1`, para que volver a una condición no mezcle pruebas independientes.

## Demostración local

Con Python instalado, abre PowerShell en la raíz del repositorio y ejecuta:

```powershell
py -3 .\tests\demo_http.py --cloud-503-cada 8
```

Mantén la terminal abierta y configura el comparador con estos destinos:

| Destino | URL local |
| --- | --- |
| MEC | `http://127.0.0.1:18091/api/iot/health` |
| Cloud | `http://127.0.0.1:18092/api/iot/health` |

Selecciona **Base**, establece un intervalo de **0.5 s** y un límite de **24 intentos por destino**. Pulsa **Iniciar**. El script aplica demoras programadas de aproximadamente 25 ms para MEC y 125 ms para Cloud, con pequeñas variaciones. Con la opción del ejemplo, Cloud devuelve HTTP 503 cada ocho peticiones. Para una demostración con respuestas correctas, ejecuta el script sin esa opción. Detén los servidores con **Ctrl+C** al terminar.

La gráfica refleja peticiones HTTP medidas en la laptop contra servidores simulados. Si adjuntas una captura, identifícala como **«Demostración local con demoras programadas»**. La comparación de rendimiento de los equipos del laboratorio requiere una prueba en su red.

## Método de medición

- `time.perf_counter_ns()` mide desde antes de abrir una conexión TCP nueva hasta terminar de leer el cuerpo completo, expresado en milisegundos. Se incluye el coste de conexión, intercambio HTTP y recepción; con nombres DNS también su resolución y con HTTPS su negociación TLS. No representa tiempo de procesamiento de una alerta.
- Se usa `http.client`, conexión nueva por petición y `Connection: close`, sin pool, redirecciones automáticas, reintentos ni proxies del sistema. Todo se ejecuta en la laptop; no se delegan consultas a otro servidor.
- Hay un solo trabajador secuencial fuera del hilo de Tk. Cada ronda alterna MEC→Cloud y Cloud→MEC. Nunca se solapan peticiones. El intervalo es el período mínimo entre comienzos de rondas; si las dos peticiones tardan más que él, la siguiente ronda empieza al acabar la anterior, sin ráfagas para recuperar tiempo perdido. Un Cloud lento puede espaciar también las rondas de MEC.
- El timeout se aplica al socket y un temporizador interrumpe el socket al agotar el plazo total del intento, incluida una respuesta que entregue datos lentamente. La resolución DNS del sistema para nombres editados podría no ser interrumpible inmediatamente; los destinos iniciales son IP literales y evitan esa limitación.
- Una respuesta correcta requiere HTTP 200, cuerpo JSON válido de tipo objeto, `status="ok"` y `service="IoT MEC"` o `service="IoT Cloud"`, según el destino.
- Se registran HTTP incorrecto, JSON inválido, identidad/status incorrectos, lectura incompleta, desconexión, timeout y errores de conexión. Los fallos se cuentan, muestran su detalle y nunca pasan a ser cero. El panel conserva el último error de la serie aunque una petición posterior resulte correcta.
- Mediana convencional: valor central o promedio de los dos centrales. P95: valores correctos ordenados, índice `ceil(0.95*n)-1`. Mínimo, máximo, mediana y P95 excluyen todos los fallos. Sin respuestas correctas se muestra `—`.
- La diferencia mostrada es **mediana Cloud − mediana MEC**, exclusivamente en la serie actual. Un valor positivo significa que la mediana observada de Cloud fue mayor; uno negativo significa que fue menor.
- La gráfica comparte escala de milisegundos y rondas ordenadas en el tiempo. Solo conecta respuestas correctas; rompe la línea ante fallos. Las cruces de fallo se dibujan en bandas inferiores separadas de la escala, nunca en 0 ms. La gráfica y los paneles muestran la serie actual; el CSV conserva todas.

## Suspensión de Windows

Se reciben notificaciones nativas `WM_POWERBROADCAST` de suspensión y reanudación. Se detienen nuevas consultas y se exige Iniciar para continuar cuando la red esté lista. Un intento que atraviese ese evento se registra con `resultado=suspension`, duración vacía y explicación; no se usa para estadísticas ni se presenta como respuesta HTTP normal. El usuario debe validar además una suspensión física real de su laptop: las pruebas automatizadas inyectan la notificación sin suspender el equipo.

## CSV

Orden exacto de columnas:

```text
session_id,condicion,ronda,destino,url,inicio_utc,http_status,resultado,duracion_ms,detalle_error
```

UTF-8 con BOM, separador coma, fechas UTC ISO 8601 y tiempos numéricos con punto decimal y seis decimales. `session_id` es un UUID; `ronda` continúa entre condiciones. `http_status` queda vacío si no se recibió un estado HTTP.

`duracion_ms` es el tiempo de una respuesta correcta **solo si `resultado=correcto`**. Para `timeout`, `http_error`, `json_invalido`, `respuesta_incorrecta` y `error_conexion` es la duración del **intento fallido**, excluida de todas las estadísticas de respuestas correctas. En `suspension` se deja vacío. Los archivos existentes requieren confirmación para sobrescribir; inicialmente se intenta creación exclusiva para evitar sobrescritura silenciosa.

La sesión se conserva en memoria hasta Nueva sesión o cierre de la aplicación. Exporte los datos antes de cerrar.

## Pruebas

Desde la carpeta del proyecto:

```powershell
py -3 -m unittest discover -v
```

Solo núcleo HTTP/estadístico, sin abrir Tk:

```powershell
py -3 -m unittest tests.test_core -v
```

Los servidores de prueba se enlazan exclusivamente a `127.0.0.1` en puertos disponibles. Cubren respuestas correctas, JSON inválido, identidad y status equivocados, HTTP 503, desconexión, conexión rechazada, cuerpo incompleto, timeout, cuerpo lento, límite total con entrega por goteo, conexión TCP nueva, ausencia de proxies, suspensión, estadísticas, CSV, alternancia, límite y detención. Las pruebas Tk cubren separación de series, aislamiento de sesiones y notificación nativa de suspensión. Los casos controlados y dobles de prueba están confinados a `tests/`; nunca se cargan en la aplicación.

## Validación en el laboratorio

Las pruebas locales no validan los caminos físicos MEC/Cloud ni tc/netem. Consulte [VALIDACION.md](VALIDACION.md) para el resultado de esta entrega. La validación final requiere la laptop conectada al Wi-Fi del proyecto, una ejecución Base, otra Cloud degradado y otra Recuperado, exportando las mediciones reales. Compruebe además el error visible al detener un servicio, la continuidad del otro y la suspensión/reanudación física.

## Estructura

- `app.py`: interfaz ttk, paneles, gráfica Canvas y control de sesiones.
- `meccloud/core.py`: medición HTTP, estadísticas, trabajador y exportación.
- `meccloud/power.py`: integración nativa con notificaciones de energía de Windows.
- `tests/`: pruebas automatizadas del núcleo y la interfaz.
- `tests/demo_http.py`: servidores HTTP para la demostración local.
