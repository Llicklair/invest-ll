# Comprobador de la etapa 2: la red de pruebas.
#
# NO manda ninguna orden. Solo responde a la pregunta previa: "cuando lance una orden de verdad,
# va a salir hacia donde creo, con credenciales que el exchange acepta?". Descubrir que la
# respuesta era no en el momento de mandar la orden es el peor momento posible.
#
# Uso:  .\scripts\testnet.ps1
#
# Antes, en esta misma terminal:
#   $env:INVEST_LL_MODE = "testnet"
#   $env:INVEST_LL_TESTNET_KEY = "tu_clave_de_pruebas"
#   $env:INVEST_LL_TESTNET_SECRET = "tu_secreto_de_pruebas"

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Escribir-Paso($texto) { Write-Host "  $texto" }
function Escribir-Bien($texto) { Write-Host "  [OK] $texto" -ForegroundColor Green }
function Escribir-Aviso($texto) { Write-Host "  [!] $texto" -ForegroundColor Yellow }
function Escribir-Mal($texto) { Write-Host "  [X] $texto" -ForegroundColor Red }

Write-Host ""
Write-Host "INVEST LL - red de pruebas" -ForegroundColor Cyan
Write-Host ("=" * 60)

# --- 1. Herramientas ---
Write-Host ""
Write-Host "Entorno"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Escribir-Mal "uv no esta instalado. Instalalo desde https://docs.astral.sh/uv/"
    exit 1
}
Escribir-Bien "uv disponible"

# --- 2. El modo pedido ---
# Se comprueba aqui y no dentro de Python para poder explicar QUE falta, no solo que falta algo.
Write-Host ""
Write-Host "Modo pedido"
$modoPedido = $env:INVEST_LL_MODE
if ($modoPedido -ne "testnet") {
    Escribir-Mal "INVEST_LL_MODE vale '$modoPedido'; este script comprueba la red de pruebas."
    Write-Host ""
    Write-Host "  En esta misma terminal:"
    Write-Host '    $env:INVEST_LL_MODE = "testnet"'
    Write-Host '    $env:INVEST_LL_TESTNET_KEY = "tu_clave_de_pruebas"'
    Write-Host '    $env:INVEST_LL_TESTNET_SECRET = "tu_secreto_de_pruebas"'
    Write-Host ""
    Write-Host "  Las claves de pruebas se crean en https://testnet.binance.vision"
    Write-Host "  (entrando con GitHub). No son las de tu cuenta real, y tienen que ser"
    Write-Host "  del tipo HMAC-SHA256: una clave Ed25519 o RSA no sirve aqui."
    exit 1
}
Escribir-Bien "INVEST_LL_MODE=testnet"

if (-not $env:INVEST_LL_TESTNET_KEY -or -not $env:INVEST_LL_TESTNET_SECRET) {
    Escribir-Mal "faltan INVEST_LL_TESTNET_KEY / INVEST_LL_TESTNET_SECRET en el entorno."
    Write-Host "  Se leen del entorno y nunca se guardan en el repositorio."
    exit 1
}
Escribir-Bien "credenciales de pruebas presentes (no se muestran)"

# --- 3. La tuberia hasta el exchange ---
# Tres preguntas, en orden de lo que falla antes: a donde apunta, si hay red, si acepta las claves.
Write-Host ""
Write-Host "Conexion con la red de pruebas"
Escribir-Paso "comprobando a donde apunta, si hay red y si acepta las claves..."

$codigo = @'
import sys

from invest_ll.live.ccxt_broker import build_exchange
from invest_ll.live.mode import Testnet, resolve_mode

modo = resolve_mode()
if not isinstance(modo, Testnet):
    print(f"MAL|el modo resuelto es {modo.name}, no la red de pruebas")
    sys.exit(1)

ex = build_exchange(modo, exchange_id="binance")
api = ex.urls.get("api")
url = api.get("public") if isinstance(api, dict) else api
if "testnet" not in str(url).lower() and "vision" not in str(url).lower():
    print(f"MAL|apunta a {url}, que NO es la red de pruebas")
    sys.exit(1)
print(f"URL|{url}")

try:
    ex.fetch_time()
except Exception as error:  # noqa: BLE001 - aqui cualquier fallo es "no hay camino"
    print(f"MAL|sin red hacia la red de pruebas: {type(error).__name__}")
    sys.exit(1)
print("RED|hay camino hasta el exchange")

# Lectura de saldo. Es la llamada mas barata que exige credenciales validas: si el exchange
# las acepta aqui, las aceptara al mandar una orden.
try:
    saldo = ex.fetch_balance()
except Exception as error:  # noqa: BLE001 - el tipo lo traducimos a un mensaje util
    print(f"AUTH|{type(error).__name__}")
    sys.exit(1)

libres = {m: c for m, c in (saldo.get("free") or {}).items() if c}
print("AUTH|OK")

# Ordenar por cantidad no sirve: la red de pruebas reparte saldo en cientos de divisas, y las
# de importe mas alto son fiat exoticas que tapan la unica que hace falta para operar el par
# (BTC/USDT se paga en USDT). Se muestran primero las monedas de referencia.
REFERENCIA = ("USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB")
if libres:
    print(f"TOTAL|{len(libres)}")
    for moneda in REFERENCIA:
        if moneda in libres:
            print(f"SALDO|{moneda}|{libres[moneda]}")
else:
    print("SALDO|VACIO|0")
'@

$salida = $codigo | uv run python - 2>&1
$exito = $LASTEXITCODE -eq 0

$saldos = @()
foreach ($linea in $salida) {
    $partes = "$linea" -split "\|"
    switch ($partes[0]) {
        "URL"   { Escribir-Bien "apunta a $($partes[1])" }
        "RED"   { Escribir-Bien $partes[1] }
        "AUTH"  {
            if ($partes[1] -eq "OK") {
                Escribir-Bien "el exchange acepta tus credenciales de pruebas"
            } elseif ($partes[1] -eq "AuthenticationError") {
                Escribir-Mal "el exchange RECHAZA las credenciales."
                Escribir-Paso "Dos causas, por orden de frecuencia:"
                Escribir-Paso "  1. No son de testnet, son de tu cuenta real."
                Escribir-Paso "  2. No son HMAC-SHA256. Una clave Ed25519 o RSA no sirve aqui:"
                Escribir-Paso "     solo se pasan apiKey y secret, no hay donde meter una clave PEM."
                Escribir-Paso "Detalles en docs\operar-de-verdad.md, 'De donde salen las claves'."
            } else {
                Escribir-Mal "fallo al leer el saldo: $($partes[1])"
            }
        }
        "TOTAL" { Escribir-Bien "$($partes[1]) monedas con saldo ficticio" }
        "SALDO" {
            if ($partes[1] -eq "VACIO") {
                # El saldo ficticio se da automaticamente al registrarse, asi que estar a cero
                # normalmente significa que la red se reseteo (pasa ~una vez al mes, sin avisar).
                Escribir-Aviso "la cuenta de pruebas no tiene saldo. La red de pruebas se borra"
                Escribir-Paso "~una vez al mes sin avisar y reparte saldo nuevo: vuelve a entrar en"
                Escribir-Paso "testnet.binance.vision y, si hace falta, genera otra clave."
            } else {
                $saldos += "$($partes[1]) $($partes[2])"
            }
        }
        "MAL"   { Escribir-Mal $partes[1] }
        default { if ("$linea".Trim()) { Escribir-Paso "$linea" } }
    }
}

if ($saldos.Count -gt 0) {
    Write-Host ""
    Write-Host "Saldo ficticio en las monedas que se usan para operar"
    foreach ($s in $saldos) { Escribir-Paso $s }
    Write-Host ""
    Escribir-Paso "Los PRECIOS de la red de pruebas no son los del mercado real: tiene su propio"
    Escribir-Paso "libro de ordenes. Sirve para ensayar la mecanica, no para medir una estrategia."
}

Write-Host ""
Write-Host ("=" * 60)
if (-not $exito) {
    Escribir-Mal "la etapa 2 NO esta lista. Arregla lo de arriba antes de mandar ninguna orden."
    exit 1
}

Escribir-Aviso "A PARTIR DE AQUI LAS ORDENES SALEN DE VERDAD (con dinero ficticio)"
Write-Host ""
Write-Host "  Manda la primera, pequena, y mira el ciclo entero:"
Write-Host "    uv run invest-ll-execute --symbol BTC/USDT --side buy --quantity 0.001"
Write-Host ""
Write-Host "  Te pedira escribir la cantidad exacta para confirmar. Opera aqui hasta que no te"
Write-Host "  sorprenda nada: una orden rechazada, una parcial, un simbolo que se llama distinto."
Write-Host "  Ese es el objetivo, no 'que salga bien una vez'."
Write-Host ""
Write-Host "  Cuando la etapa 2 ya no te ensene nada: docs\operar-de-verdad.md, etapa 3."
Write-Host ""
exit 0
