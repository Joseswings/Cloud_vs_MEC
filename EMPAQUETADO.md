# Ejecutable de Windows

Abra **Cloud_vs_MEC.exe** con doble clic. Está en la misma carpeta que `app.py` e incluye Python, Tcl/Tk y los módulos de la aplicación. No requiere instalar Python, ejecutar PowerShell ni instalar paquetes para utilizarlo. No abre una consola.

Es un ejecutable de archivo único para **Windows x64**. Al arrancar extrae sus componentes en una carpeta temporal del usuario; la primera apertura puede tardar unos segundos. La aplicación comienza sin mediciones y mantiene los mismos destinos, controles y método de medición del código Python.

La validación final de los servicios MEC/Cloud y de la suspensión física sigue pendiente en el Wi-Fi del proyecto, como se explica en `VALIDACION.md`.

Verificación del empaquetado: el ejecutable se abrió desde la carpeta del Escritorio y mostró la interfaz completa, sin consola y sin mediciones iniciales. Tamaño: 13 350 399 bytes. Se revisó visualmente la ventana del ejecutable con la habilidad Computer Use; la validación HTTP y estadística del código fuente consta en `VALIDACION.md`.

## Reconstruir desde el código (opcional)

Compilado en Windows con Python 3.14.6 y PyInstaller 6.22.3. Para volver a compilar, abre PowerShell en la raíz del repositorio:

```powershell
py -3 -m venv .build-env
& '.\.build-env\Scripts\python.exe' -m pip install 'pyinstaller==6.22.3'
& '.\.build-env\Scripts\python.exe' -m PyInstaller --clean --onefile --windowed --name Cloud_vs_MEC --distpath dist --workpath build app.py
```

El resultado de una reconstrucción queda en `dist\Cloud_vs_MEC.exe`; esto evita reemplazar automáticamente el ejecutable entregado en la carpeta principal. El código fuente, las pruebas y la biblioteca estándar no requieren PyInstaller para su ejecución normal con Python.
