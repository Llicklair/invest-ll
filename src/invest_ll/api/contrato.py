"""El OpenAPI del panel, que es el contrato con el frontend.

`web/openapi.json` se genera desde aquí y el frontend saca sus tipos de él
(`npm run tipos` en `web/`). Si cambias una ruta o un modelo, regenera el fichero a propósito:

    uv run python -m invest_ll.api.contrato

`tests/unit/test_api_contrato.py` falla si el fichero y la API se desvían: un frontend tipado
contra un contrato viejo compila y luego pinta `undefined` donde había dinero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from invest_ll.api.app import RAIZ_REPO, crear_app

FICHERO = RAIZ_REPO / "web" / "openapi.json"


def openapi() -> dict[str, Any]:
    return crear_app(frontend=None).openapi()


def como_texto(esquema: dict[str, Any]) -> str:
    return json.dumps(esquema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def escribir(destino: Path = FICHERO) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(como_texto(openapi()), encoding="utf-8")
    return destino


if __name__ == "__main__":  # pragma: no cover
    print(f"Escrito {escribir()}")
