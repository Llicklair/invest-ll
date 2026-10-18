@echo off
rem =====================================================================
rem  INVEST LL - doble clic para levantar el panel.
rem
rem  Lo que hace, en orden:
rem    1. MATA los paneles viejos de este repositorio que hubiera abiertos.
rem       Sin esto, el navegador seguia mirando un panel de hace horas con
rem       el codigo viejo cacheado, y uv sync fallaba con el .exe abierto.
rem    2. Comprueba el entorno (uv, dependencias, modo de operacion).
rem    3. Compila el frontend (web/) si todavia no esta compilado.
rem    4. Abre el panel en http://localhost:8601: la API (FastAPI) y el
rem       frontend en un solo proceso. Ctrl+C para pararlo.
rem    5. Los bots NO se paran al cerrarlo: viven en su motor aparte, que el
rem       panel arranca si hace falta (invest-ll-motor estado / parar).
rem
rem  Los detalles viven en scripts\start.ps1 (con .\scripts\start.ps1
rem  -SoloCheck compruebas sin arrancar).
rem =====================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
pause
