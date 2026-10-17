"""Lo que el conector MCP le pide al panel en marcha, por su API local (http://127.0.0.1:8601/api).

Los bots viven en el proceso del panel (su motor, su fuente de precios): desplegar, listar y parar
un bot se hace a través de él, nunca tocando `bots/` por detrás. Si el panel no está abierto, el
error lo dice en llano.

**Solo tres operaciones, y ninguna con dinero real.** Listar los bots, crear un bot FICTICIO con
una estrategia a medida (el modo va fijo en el cuerpo: `ficticio`, sin exchange ni límites) y parar
un bot. No hay forma de pedir desde aquí activar real, cambiar límites, tocar claves o conexiones:
la lista de rutas es cerrada (`RUTAS`) y `tests/unit/test_mcp_servidor.py` la vigila. Solo habla
con este equipo (127.0.0.1 o localhost).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Final, cast
from urllib.parse import urlsplit

import httpx

from invest_ll.errors import InvestLLError

URL: Final = "http://127.0.0.1:8601/api"
RUTAS: Final = (("GET", "/bots"), ("POST", "/bots"), ("POST", "/bots/{id}/parar"))
"""Todo lo que el conector puede pedirle al panel."""
TIMEOUT: Final = 30.0
_BOT: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class PanelError(InvestLLError):
    """El panel dijo que no, o no está abierto. El texto, en llano."""


class Panel:
    """Cliente de la API local del panel, limitado a `RUTAS`."""

    def __init__(self, base: str = URL, *, cliente: httpx.Client | None = None) -> None:
        host = urlsplit(base).hostname
        if host not in ("127.0.0.1", "localhost"):
            raise PanelError("El conector solo habla con el panel de este equipo (127.0.0.1).")
        self.base = base.rstrip("/")
        self._cliente = cliente or httpx.Client(timeout=TIMEOUT)

    def bots(self) -> dict[str, Any]:
        return self._pedir("GET", "/bots")

    def desplegar_ficticio(
        self, *, estrategia: str, nombre: str, monedas: list[str], capital: Decimal
    ) -> dict[str, Any]:
        """Un bot con dinero FICTICIO que ejecuta la estrategia a medida `estrategia`."""
        cuerpo = {
            "plantilla": "medida",
            "estrategia": estrategia,
            "nombre": nombre,
            "monedas": monedas,
            "capital": format(capital.normalize(), "f"),
            "modo": "ficticio",
        }
        return self._pedir("POST", "/bots", cuerpo)

    def parar_bot(self, bot_id: str) -> dict[str, Any]:
        if not _BOT.match(bot_id):
            raise PanelError(f"«{bot_id[:40]}» no es el id de un bot.")
        return self._pedir("POST", f"/bots/{bot_id}/parar")

    def _pedir(
        self, metodo: str, ruta: str, cuerpo: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self.base}{ruta}"
        try:
            respuesta = self._cliente.request(metodo, url, json=cuerpo)
        except httpx.ConnectError:
            raise PanelError(
                f"El panel de INVEST LL no está abierto ({self.base}). Ábrelo (levantar.cmd o "
                "invest-ll-panel) y vuelve a intentarlo: los bots solo viven con el panel abierto."
            ) from None
        except httpx.HTTPError as error:
            raise PanelError(f"No se pudo hablar con el panel: {error}") from None
        try:
            leido: object = respuesta.json()
        except ValueError:
            leido = {}
        datos = cast("dict[str, Any]", leido) if isinstance(leido, dict) else {}
        if respuesta.status_code >= 400:
            detalle = datos.get("detail")
            raise PanelError(
                str(detalle) if detalle else f"El panel respondió {respuesta.status_code}."
            )
        return datos
