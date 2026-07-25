#!/usr/bin/env bash
# Las cuatro gates de la constitucion, en un comando que FALLA si alguna falla.
#
# Existe porque encadenarlas a mano con `{ ...; } && git commit` no funciona: el bloque devuelve
# el codigo del ULTIMO comando, asi que un fallo de ruff o de pyright pasa desapercibido si pytest
# esta en verde. Ha ocurrido tres veces en este proyecto, y las tres veces se commiteo en rojo.
#
# `set -e` es lo que lo arregla: cualquier gate que falle corta aqui.
#
# Uso:  bash scripts/gates.sh && git commit -m "..."
set -euo pipefail

echo "--- ruff check ---"
uv run ruff check .

echo "--- ruff format ---"
uv run ruff format --check .

echo "--- pyright ---"
uv run pyright

echo "--- pytest ---"
uv run pytest -q

echo ""
echo "Las cuatro gates en verde."
