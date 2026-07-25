# Arranque de INVEST LL en Windows.
#
# NO arranca "frontend y backend" por separado: no hay dos. El panel de Streamlit llama al motor
# directamente en el mismo proceso, sin API por medio. Este script comprueba que todo esta en su
# sitio antes de levantarlo, que es donde de verdad se pierde tiempo cuando algo falla.
#
# Uso:  .\scripts\start.ps1              arranca el panel
#       .\scripts\start.ps1 -SoloCheck   solo comprueba, no arranca

param(
    [switch]$SoloCheck,
    [int]$Puerto = 8601
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Escribir-Paso($texto) { Write-Host "  $texto" }
function Escribir-Bien($texto) { Write-Host "  [OK] $texto" -ForegroundColor Green }
function Escribir-Aviso($texto) { Write-Host "  [!] $texto" -ForegroundColor Yellow }
function Escribir-Mal($texto) { Write-Host "  [X] $texto" -ForegroundColor Red }

Write-Host ""
Write-Host "INVEST LL" -ForegroundColor Cyan
Write-Host ("=" * 60)

# --- 1. Herramientas ---
Write-Host ""
Write-Host "Entorno"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Escribir-Mal "uv no esta instalado. Instalalo desde https://docs.astral.sh/uv/"
    exit 1
}
Escribir-Bien "uv disponible"

Escribir-Paso "Sincronizando dependencias..."
uv sync --quiet
if ($LASTEXITCODE -ne 0) {
    Escribir-Mal "uv sync fallo. Si dice 'Acceso denegado', cierra el panel si esta abierto."
    exit 1
}
Escribir-Bien "dependencias al dia"

# --- 2. Modo de operacion ---
# Esto es lo primero que hay que saber al arrancar: si el sistema puede mandar ordenes reales.
Write-Host ""
Write-Host "Modo de operacion"
$modo = uv run python -c "from invest_ll.live.mode import resolve_mode; m = resolve_mode(); print(m.name); print('REAL' if m.sends_real_orders else 'NO')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Escribir-Mal "no se pudo determinar el modo"
    exit 1
}
$lineas = $modo -split "`n" | ForEach-Object { $_.Trim() }
if ($lineas[1] -eq "REAL") {
    Escribir-Aviso "MODO $($lineas[0]) - este sistema PUEDE enviar ordenes reales"
    Escribir-Aviso "cada orden seguira pidiendo confirmacion por separado"
} else {
    Escribir-Bien "simulacion - ninguna orden sale al exterior"
}

# --- 3. Datos ---
Write-Host ""
Write-Host "Datos de mercado"
$activos = uv run python -c "from invest_ll.dashboard.data import discover_assets; a = discover_assets(); print(len(a)); print(' '.join(sorted({x.symbol for x in a}))[:200])" 2>$null
$partes = $activos -split "`n" | ForEach-Object { $_.Trim() }
$cuantos = [int]$partes[0]

if ($cuantos -eq 0) {
    Escribir-Aviso "no hay ningun historico descargado"
    Write-Host ""
    Write-Host "  Descarga alguno antes de empezar:"
    Write-Host "    uv run invest-ll-fetch AAPL --market equity --interval DAY_1 ``"
    Write-Host "        --start 2020-01-01 --end 2026-01-01"
    Write-Host ""
} else {
    Escribir-Bien "$cuantos historicos: $($partes[1])"
}

# --- 4. Decisiones cacheadas ---
Write-Host ""
Write-Host "Decisiones del LLM"
if (Test-Path "decisions") {
    $carpetas = Get-ChildItem "decisions" -Directory -ErrorAction SilentlyContinue
    if ($carpetas) {
        foreach ($c in $carpetas) {
            $n = (Get-ChildItem $c.FullName -Filter *.json -ErrorAction SilentlyContinue).Count
            Escribir-Bien "$($c.Name): $n decisiones (repetir el experimento no cuesta nada)"
        }
    } else {
        Escribir-Paso "ninguna generada todavia (usa invest-ll-generate)"
    }
} else {
    Escribir-Paso "ninguna generada todavia (usa invest-ll-generate)"
}

if ($SoloCheck) {
    Write-Host ""
    Write-Host "Comprobacion terminada. No se ha arrancado nada."
    exit 0
}

# --- 5. Paneles viejos ---
# Un panel viejo tiene los modulos cacheados en memoria: tras editar codigo da ImportError de
# cosas que existen, y como cada arranque buscaba un puerto nuevo, el navegador seguia mirando
# el panel muerto. Se mata lo que hubiera y se usa SIEMPRE el mismo puerto.
Write-Host ""
Write-Host "Paneles anteriores"
$viejos = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*streamlit*" }
if ($viejos) {
    foreach ($proceso in $viejos) {
        Stop-Process -Id $proceso.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Escribir-Bien "cerrados $(@($viejos).Count) proceso(s) de un arranque anterior"
    Start-Sleep -Seconds 2
} else {
    Escribir-Bien "ninguno abierto"
}

# --- 6. El panel ---
Write-Host ""
Write-Host ("=" * 60)
Write-Host "Abriendo el panel en http://localhost:$Puerto" -ForegroundColor Cyan
Write-Host "Ctrl+C para pararlo."
Write-Host ""

uv run streamlit run src/invest_ll/dashboard/app.py --server.port $Puerto
