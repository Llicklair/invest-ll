@echo off
rem =====================================================================
rem  INVEST LL - doble clic para instalar en un equipo nuevo.
rem
rem  Comprueba uv y Node.js (y ofrece instalarlos con winget), prepara
rem  Python 3.13 y las dependencias, compila el panel y lo comprueba.
rem  No arranca nada ni toca dinero. Se puede repetir sin miedo.
rem  Los detalles viven en scripts\instalar.ps1.
rem =====================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1" %*
pause
