"""Que la API y el contrato que usa el frontend (`web/openapi.json`) no se separen.

El frontend genera sus tipos de ese fichero. Si alguien cambia una ruta o un modelo sin
regenerarlo, el frontend sigue compilando contra la forma vieja y pinta `undefined` donde había
una cifra. Regenerar es un paso deliberado: `uv run python -m invest_ll.api.contrato`.
"""

from __future__ import annotations

import json

from invest_ll.api.contrato import FICHERO, como_texto, openapi


def test_el_contrato_del_frontend_esta_al_dia() -> None:
    assert FICHERO.exists(), "falta web/openapi.json: uv run python -m invest_ll.api.contrato"
    guardado = json.loads(FICHERO.read_text(encoding="utf-8"))
    assert como_texto(guardado) == como_texto(openapi()), (
        "web/openapi.json no coincide con la API. Si el cambio es a proposito, regeneralo con "
        "'uv run python -m invest_ll.api.contrato' y adapta el frontend."
    )


def test_el_dinero_viaja_como_texto() -> None:
    """Los importes del contrato son cadenas en las respuestas, nunca floats."""
    esquemas = openapi()["components"]["schemas"]
    posicion = esquemas.get("PosicionAbierta") or esquemas["PosicionAbierta-Output"]
    assert posicion["properties"]["cantidad"]["type"] == "string"
