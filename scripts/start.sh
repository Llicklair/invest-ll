#!/usr/bin/env bash
# Arranque de INVEST LL en Linux y macOS. Equivalente a scripts/start.ps1.
#
# El panel son dos piezas pero UN proceso: la API (FastAPI, src/invest_ll/api) sirve tambien el
# frontend ya compilado (Next.js exportado a web/out) en el mismo puerto. Este script comprueba que
# todo esta en su sitio, compila el frontend si falta y arranca `invest-ll-panel`.
#
# Uso:  bash scripts/start.sh              arranca el panel
#       bash scripts/start.sh --solo-check solo comprueba, no arranca ni compila nada
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ="$(pwd)"

SOLO_CHECK=0
PUERTO=8601
for arg in "$@"; do
    case "$arg" in
        --solo-check) SOLO_CHECK=1 ;;
        --puerto=*) PUERTO="${arg#*=}" ;;
    esac
done

paso() { printf '  %s\n' "$1"; }
bien() { printf '  \033[32m[OK]\033[0m %s\n' "$1"; }
aviso() { printf '  \033[33m[!]\033[0m %s\n' "$1"; }
mal() { printf '  \033[31m[X]\033[0m %s\n' "$1"; }

echo ""
printf '\033[36mINVEST LL\033[0m\n'
printf '%.0s=' {1..60}; echo ""

# --- 1. Herramientas ---
echo ""
echo "Entorno"
if ! command -v uv > /dev/null 2>&1; then
    mal "uv no esta instalado. Instalalo desde https://docs.astral.sh/uv/"
    exit 1
fi
bien "uv disponible"

# --- 2. Paneles viejos ---
# Un panel viejo sirve el codigo de antes y ocupa el puerto: se cierra antes de sincronizar, y se
# usa SIEMPRE el mismo puerto. Solo al arrancar: --solo-check no toca nada.
if [ "$SOLO_CHECK" -eq 0 ]; then
    echo ""
    echo "Paneles anteriores"
    # Los de ESTE repositorio (su .venv): invest-ll-panel, uvicorn sobre invest_ll y los de
    # Streamlit de antes de retirarlo. pgrep no se encuentra a si mismo; este script se excluye.
    viejos=$(pgrep -f "$RAIZ/.venv/.*(invest-ll-panel|uvicorn.*invest_ll|streamlit.*invest_ll)" \
        | grep -v "^$$\$" || true)
    if [ -n "$viejos" ]; then
        # shellcheck disable=SC2086
        kill $viejos 2> /dev/null || true
        sleep 2
        bien "cerrados $(echo "$viejos" | wc -l | tr -d ' ') proceso(s) de un arranque anterior"
    else
        bien "ninguno abierto"
    fi
fi

echo ""
paso "Sincronizando dependencias..."
uv sync --quiet
bien "dependencias al dia"

# --- 3. Modo de operacion ---
# Lo primero que hay que saber: si el sistema puede mandar ordenes reales.
echo ""
echo "Modo de operacion"
modo_nombre=$(uv run python -c "from invest_ll.live.mode import resolve_mode; print(resolve_mode().name)")
modo_real=$(uv run python -c "from invest_ll.live.mode import resolve_mode; print(resolve_mode().sends_real_orders)")

if [ "$modo_real" = "True" ]; then
    aviso "MODO $modo_nombre - este sistema PUEDE enviar ordenes reales"
    aviso "cada orden seguira pidiendo confirmacion por separado"
else
    bien "simulacion - ninguna orden sale al exterior"
fi

# --- 4. Datos ---
echo ""
echo "Datos de mercado"
cuantos=$(uv run python -c "from invest_ll.fetch.available import discover_assets; print(len(discover_assets()))")

if [ "$cuantos" -eq 0 ]; then
    aviso "no hay ningun historico descargado"
    echo ""
    echo "  Descarga alguno antes de empezar:"
    echo "    uv run invest-ll-fetch AAPL --market equity --interval DAY_1 \\"
    echo "        --start 2020-01-01 --end 2026-01-01"
    echo ""
else
    simbolos=$(uv run python -c "from invest_ll.fetch.available import discover_assets; print(' '.join(sorted({a.symbol for a in discover_assets()}))[:200])")
    bien "$cuantos historicos: $simbolos"
fi

# --- 5. Decisiones cacheadas ---
echo ""
echo "Decisiones del LLM"
if [ -d decisions ] && [ -n "$(ls -A decisions 2>/dev/null)" ]; then
    for carpeta in decisions/*/; do
        [ -d "$carpeta" ] || continue
        n=$(find "$carpeta" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
        bien "$(basename "$carpeta"): $n decisiones (repetir el experimento no cuesta nada)"
    done
else
    echo "  ninguna generada todavia (usa invest-ll-generate)"
fi

# --- 6. Frontend ---
# Se compila solo si falta: `npm ci` + `npm run build` dejan web/out, que sirve la propia API.
echo ""
echo "Frontend"
if [ ! -f web/package.json ]; then
    aviso "no hay frontend en web/ todavia: se arrancara solo la API (http://localhost:$PUERTO/docs)"
elif [ -f web/out/index.html ]; then
    bien "compilado (web/out)"
elif [ "$SOLO_CHECK" -eq 1 ]; then
    aviso "sin compilar: se compilara al arrancar (npm ci + npm run build en web/)"
elif ! command -v npm > /dev/null 2>&1; then
    aviso "sin compilar y npm no esta instalado: se arrancara solo la API"
    paso "instala Node.js y luego: npm --prefix web ci && npm --prefix web run build"
else
    paso "Compilando el frontend (la primera vez tarda un rato)..."
    if npm --prefix web ci && npm --prefix web run build && [ -f web/out/index.html ]; then
        bien "frontend compilado en web/out"
    else
        aviso "no se pudo compilar el frontend: se arrancara solo la API (mira los errores de npm arriba)"
    fi
fi

if [ "$SOLO_CHECK" -eq 1 ]; then
    echo ""
    echo "Comprobacion terminada. No se ha arrancado nada."
    exit 0
fi

# --- 7. El panel ---
echo ""
printf '%.0s=' {1..60}; echo ""
printf '\033[36mAbriendo el panel en http://localhost:%s\033[0m\n' "$PUERTO"
echo "Ctrl+C para pararlo."
echo ""

uv run invest-ll-panel --puerto "$PUERTO"
