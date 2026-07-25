@echo off
rem =====================================================================
rem  INVEST LL - doble clic para levantar el panel.
rem
rem  Lo que hace, en orden:
rem    1. Comprueba el entorno (uv, dependencias, modo de operacion).
rem    2. MATA los paneles viejos que hubiera abiertos. Sin esto, cada
rem       arranque abria un puerto nuevo y el navegador seguia mirando
rem       un panel de hace horas con el codigo viejo cacheado.
rem    3. Abre el panel en http://localhost:8601 (Ctrl+C para pararlo).
rem
rem  Los detalles viven en scripts\start.ps1 (con .\scripts\start.ps1
rem  -SoloCheck compruebas sin arrancar).
rem =====================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
pause
