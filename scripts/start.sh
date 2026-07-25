#!/usr/bin/env bash
# Arranque de INVEST LL en Linux y macOS. Equivalente a scripts/start.ps1.
#
# NO arranca "frontend y backend" por separado: no hay dos. El panel de Streamlit llama al motor
# directamente en el mismo proceso, sin API por medio.
#
# Uso:  bash scripts/start.sh              arranca el panel
#       bash scripts/start.sh --solo-check solo comprueba, no arranca
set -euo pipefail

cd "$(dirname "$0")/.."

SOLO_CHECK=0
PUERTO=8501
for arg in "$@"; do
    case "$arg" in
        --solo-check) SOLO_CHECK=1 ;;
        --puerto=*) PUERTO="${arg#*=}" ;;
    esac
done

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

echo "  Sincronizando dependencias..."
uv sync --quiet
bien "dependencias al dia"

# --- 2. Modo de operacion ---
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

# --- 3. Datos ---
echo ""
echo "Datos de mercado"
cuantos=$(uv run python -c "from invest_ll.dashboard.data import discover_assets; print(len(discover_assets()))")

if [ "$cuantos" -eq 0 ]; then
    aviso "no hay ningun historico descargado"
    echo ""
    echo "  Descarga alguno antes de empezar:"
    echo "    uv run invest-ll-fetch AAPL --market equity --interval DAY_1 \\"
    echo "        --start 2020-01-01 --end 2026-01-01"
    echo ""
else
    simbolos=$(uv run python -c "from invest_ll.dashboard.data import discover_assets; print(' '.join(sorted({a.symbol for a in discover_assets()}))[:200])")
    bien "$cuantos historicos: $simbolos"
fi

# --- 4. Decisiones cacheadas ---
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

if [ "$SOLO_CHECK" -eq 1 ]; then
    echo ""
    echo "Comprobacion terminada. No se ha arrancado nada."
    exit 0
fi

# --- 5. El panel ---
echo ""
printf '%.0s=' {1..60}; echo ""
printf '\033[36mAbriendo el panel en http://localhost:%s\033[0m\n' "$PUERTO"
echo "Ctrl+C para pararlo."
echo ""

uv run streamlit run src/invest_ll/dashboard/app.py --server.port "$PUERTO"
