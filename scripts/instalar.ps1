# INVEST LL - instalar en un equipo nuevo (Windows 10/11).
#
#   Doble clic en instalar.cmd, o desde una terminal:
#       powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\instalar.ps1
#       ... -SinPreguntar   instala lo que falte sin preguntar y no crea el acceso directo
#
# Lo que hace, en orden (se puede repetir sin miedo: lo que ya esta, lo deja):
#   1. Comprueba uv y Node.js; si faltan, ofrece instalarlos con winget (preguntando antes).
#   2. Prepara Python 3.13 y las dependencias (uv sync; uv descarga Python si no lo hay).
#   3. Compila el frontend (npm ci + npm run build en web/).
#   4. Activa el detector de secretos antes de cada commit (si es un clon de git).
#   5. Ofrece un acceso directo en el escritorio a levantar.cmd.
#   6. Comprueba todo con start.ps1 -SoloCheck. No arranca nada ni toca dinero.
#
# Los textos van sin tildes a proposito: PowerShell 5.1 lee los .ps1 sin BOM como ANSI.

param(
    [switch]$SinPreguntar
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

function Paso($texto) { Write-Host ""; Write-Host $texto -ForegroundColor Cyan }
function Bien($texto) { Write-Host "  [OK] $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  [!] $texto" -ForegroundColor Yellow }
function Mal($texto) { Write-Host "  [X] $texto" -ForegroundColor Red }

function Preguntar($pregunta) {
    if ($SinPreguntar) { return $true }
    $r = Read-Host "  $pregunta (S/n)"
    return ($r -eq "" -or $r -match "^[sSyY]")
}

function Refrescar-Path {
    # Lo que instala winget o el instalador de uv no esta en el PATH de esta ventana hasta abrir otra.
    $maquina = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $usuario = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$maquina;$usuario;$env:USERPROFILE\.local\bin;$env:ProgramFiles\nodejs"
}

function Con-Winget($id, $nombre) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Mal "no esta winget para instalar $nombre. Instalalo a mano y vuelve a ejecutar esto."
        return $false
    }
    winget install --exact --id $id --accept-source-agreements --accept-package-agreements --silent
    Refrescar-Path
    return $LASTEXITCODE -eq 0
}

function Version-Node {
    try {
        $v = (node --version) -replace "^v", ""
        return [version]($v -split "-")[0]
    } catch {
        return $null
    }
}

Write-Host ""
Write-Host "INVEST LL - instalacion" -ForegroundColor Cyan
Write-Host ("=" * 60)
Write-Host "  Carpeta: $Raiz"

# -- 1. Herramientas ------------------------------------------------------------------------------
Paso "1. Herramientas"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Aviso "falta uv (instala Python y las dependencias del proyecto)"
    if (Preguntar "Instalo uv ahora con winget?") {
        if (-not (Con-Winget "astral-sh.uv" "uv")) { exit 1 }
    } else {
        Mal "sin uv no se puede seguir: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }
}
Bien "uv $((uv --version) -replace '^uv ', '')"

$minimoNode = [version]"20.9.0"
$node = Version-Node
if ($null -eq $node -or $node -lt $minimoNode) {
    if ($null -eq $node) { Aviso "falta Node.js (para compilar el panel)" }
    else { Aviso "Node.js $node es antiguo: hace falta $minimoNode o mas" }
    if (Preguntar "Instalo Node.js LTS ahora con winget?") {
        if (-not (Con-Winget "OpenJS.NodeJS.LTS" "Node.js")) { exit 1 }
        $node = Version-Node
    }
}
if ($null -eq $node -or $node -lt $minimoNode) {
    Aviso "sin Node.js $minimoNode+ no se compila el panel: arrancara solo la API"
    $hayNode = $false
} else {
    Bien "Node.js $node"
    $hayNode = $true
}

# -- 2. Python y dependencias ---------------------------------------------------------------------
Paso "2. Python 3.13 y dependencias"
uv sync
if ($LASTEXITCODE -ne 0) {
    Mal "uv sync fallo. Si dice 'os error 32' o 'Acceso denegado', hay un panel o el motor abiertos:"
    Mal "cierralos (invest-ll-motor parar) y vuelve a ejecutar esto."
    exit 1
}
Bien "entorno listo en .venv"

# -- 3. Frontend ----------------------------------------------------------------------------------
Paso "3. Panel (frontend)"
if ($hayNode) {
    npm --prefix web ci --no-audit --no-fund
    if ($LASTEXITCODE -eq 0) { npm --prefix web run build }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "web\out\index.html")) {
        Mal "no se pudo compilar el panel (mira los errores de npm arriba)"
        exit 1
    }
    Bien "panel compilado en web\out"
} else {
    Aviso "sin compilar (falta Node.js)"
}

# -- 4. Detector de secretos ----------------------------------------------------------------------
Paso "4. Detector de secretos antes de cada commit"
if ((Test-Path ".git") -and (Get-Command git -ErrorAction SilentlyContinue)) {
    git config core.hooksPath .githooks
    Bien "activado (scripts\sin_secretos.py revisa cada commit)"
} else {
    Aviso "no es un clon de git: no hace falta"
}

# -- 5. Acceso directo ----------------------------------------------------------------------------
Paso "5. Acceso directo"
$escritorio = [Environment]::GetFolderPath("Desktop")
$acceso = Join-Path $escritorio "INVEST LL.lnk"
if (Test-Path $acceso) {
    Bien "ya esta en el escritorio"
} elseif (-not $SinPreguntar -and (Preguntar "Pongo un acceso directo 'INVEST LL' en el escritorio?")) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($acceso)
    $lnk.TargetPath = Join-Path $Raiz "levantar.cmd"
    $lnk.WorkingDirectory = $Raiz
    $lnk.Description = "Abre el panel de INVEST LL en http://localhost:8601"
    $lnk.Save()
    Bien "creado: $acceso"
} else {
    Aviso "sin acceso directo (el panel se abre con levantar.cmd)"
}

# -- 6. Comprobacion ------------------------------------------------------------------------------
Paso "6. Comprobacion"
& (Join-Path $PSScriptRoot "start.ps1") -SoloCheck
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host ("=" * 60)
Write-Host "Listo. Para abrir el panel: doble clic en levantar.cmd (http://localhost:8601)." -ForegroundColor Green
Write-Host "Arranca en simulacion: nada sale a ningun exchange hasta que tu lo conectes y lo actives."
Write-Host "Las claves se guardan en el Administrador de credenciales de Windows, nunca en ficheros."
exit 0
