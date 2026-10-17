# Arranque de INVEST LL en Windows.
#
# El panel son dos piezas pero UN proceso: la API (FastAPI, src/invest_ll/api) sirve tambien el
# frontend ya compilado (Next.js exportado a web/out) en el mismo puerto. Este script comprueba que
# todo esta en su sitio, compila el frontend si falta y arranca `invest-ll-panel`.
#
# Uso:  .\scripts\start.ps1              arranca el panel
#       .\scripts\start.ps1 -SoloCheck   solo comprueba, no arranca ni compila nada

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

# --- 2. Paneles viejos ---
# Un panel viejo tiene los modulos cacheados en memoria: tras editar codigo sirve lo de antes, y
# mientras su ejecutable esta abierto `uv sync` falla con "os error 32". Se cierran ANTES de
# sincronizar, y se usa SIEMPRE el mismo puerto para que el navegador no mire uno muerto.
# Solo al arrancar: -SoloCheck no toca nada.
if (-not $SoloCheck) {
    Write-Host ""
    Write-Host "Paneles anteriores"
    # Los de ESTE repositorio (su .venv, no el de otra copia o worktree): invest-ll-panel, uvicorn
    # sobre invest_ll, y los de Streamlit que quedaran de antes de retirarlo. Se excluye este mismo
    # proceso por si su linea de ordenes contuviera lo que se busca.
    $venv = Join-Path $raiz ".venv"
    $viejos = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and $_.CommandLine -and
            $_.CommandLine -like "*$venv\*" -and (
                $_.CommandLine -like "*invest-ll-panel*" -or
                ($_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*invest_ll*") -or
                ($_.CommandLine -like "*streamlit*" -and $_.CommandLine -like "*invest_ll*")
            )
        }
    if ($viejos) {
        foreach ($proceso in $viejos) {
            # El arbol entero: matar solo el padre deja el Python hijo vivo y con el puerto.
            # La lista trae padre e hijo: al matar el arbol del padre, el hijo ya no existe y
            # taskkill lo dice por stderr. Con $ErrorActionPreference = "Stop", PowerShell 5.1
            # convierte esa linea en un error que paraba el arranque entero: aqui no lo es.
            if (Get-Process -Id $proceso.ProcessId -ErrorAction SilentlyContinue) {
                cmd /c "taskkill /PID $($proceso.ProcessId) /T /F >nul 2>&1"
            }
        }
        # Esperar de verdad a que mueran y suelten el puerto y los .exe del .venv: con una pausa
        # fija de 2 s, a veces el puerto seguia en escucha (o uv sync chocaba con un .exe aun
        # abierto) y el arranque se paraba con un error que no lo era.
        $pids = @($viejos | ForEach-Object { $_.ProcessId })
        for ($i = 0; $i -lt 30; $i++) {
            $vivos = @(Get-Process -Id $pids -ErrorAction SilentlyContinue)
            $escucha = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
            if (-not $vivos -and -not $escucha) { break }
            Start-Sleep -Milliseconds 500
        }
        Escribir-Bien "cerrados $(@($viejos).Count) proceso(s) de un arranque anterior"
    } else {
        Escribir-Bien "ninguno abierto"
    }

    $ocupado = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
    if ($ocupado) {
        $dueno = Get-Process -Id $ocupado[0].OwningProcess -ErrorAction SilentlyContinue
        Escribir-Mal "el puerto $Puerto sigue ocupado por $($dueno.ProcessName) (PID $($ocupado[0].OwningProcess))"
        Escribir-Paso "no es un panel de este repositorio: cierralo tu o arranca con -Puerto <otro>"
        exit 1
    }
}

Write-Host ""
Escribir-Paso "Sincronizando dependencias..."
uv sync --quiet
if ($LASTEXITCODE -ne 0) {
    Escribir-Mal "uv sync fallo. Si dice 'os error 32' o 'Acceso denegado', hay un panel abierto: cierralo."
    exit 1
}
Escribir-Bien "dependencias al dia"

# --- 3. Modo de operacion ---
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

# --- 4. Datos ---
Write-Host ""
Write-Host "Datos de mercado"
$activos = uv run python -c "from invest_ll.fetch.available import discover_assets; a = discover_assets(); print(len(a)); print(' '.join(sorted({x.symbol for x in a}))[:200])" 2>$null
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

# --- 5. Decisiones cacheadas ---
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

# --- 6. Frontend ---
# Se compila solo si falta: `npm ci` + `npm run build` dejan web/out, que sirve la propia API.
Write-Host ""
Write-Host "Frontend"
$web = Join-Path $raiz "web"
$compilado = Join-Path $web "out\index.html"
if (-not (Test-Path (Join-Path $web "package.json"))) {
    Escribir-Aviso "no hay frontend en web/ todavia: se arrancara solo la API (http://localhost:$Puerto/docs)"
} elseif (Test-Path $compilado) {
    Escribir-Bien "compilado (web/out)"
} elseif ($SoloCheck) {
    Escribir-Aviso "sin compilar: se compilara al arrancar (npm ci + npm run build en web/)"
} elseif (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Escribir-Aviso "sin compilar y npm no esta instalado: se arrancara solo la API"
    Escribir-Paso "instala Node.js y luego: npm --prefix web ci; npm --prefix web run build"
} else {
    Escribir-Paso "Compilando el frontend (la primera vez tarda un rato)..."
    npm --prefix web ci
    if ($LASTEXITCODE -eq 0) { npm --prefix web run build }
    if ($LASTEXITCODE -eq 0 -and (Test-Path $compilado)) {
        Escribir-Bien "frontend compilado en web/out"
    } else {
        Escribir-Aviso "no se pudo compilar el frontend: se arrancara solo la API (mira los errores de npm arriba)"
    }
}

if ($SoloCheck) {
    Write-Host ""
    Write-Host "Comprobacion terminada. No se ha arrancado nada."
    exit 0
}

# --- 7. El panel ---
Write-Host ""
Write-Host ("=" * 60)
Write-Host "Abriendo el panel en http://localhost:$Puerto" -ForegroundColor Cyan
Write-Host "Ctrl+C para pararlo."
Write-Host ""

uv run invest-ll-panel --puerto $Puerto
