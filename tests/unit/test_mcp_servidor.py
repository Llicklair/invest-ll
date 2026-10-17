"""El conector MCP (`invest-ll-mcp`): sus once herramientas, una llamada de cada (con el panel
simulado y un exchange falso, sin red) y, sobre todo, lo que NO puede: activar dinero real,
cambiar límites o tocar claves. Ni con una herramienta, ni pidiéndoselo al panel."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from invest_ll.estrategias_custom.biblioteca import Biblioteca
from invest_ll.estrategias_custom.disenar import HERRAMIENTAS
from invest_ll.mcp import panel as modulo_panel
from invest_ll.mcp.panel import RUTAS, Panel, PanelError
from invest_ll.mcp.servidor import Herramientas, crear_servidor

from .medida_apoyo import CRUCE, ConectorFalso, onda, serie

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Coroutine

    from mcp.server.mcpserver import MCPServer

FUENTE = Path(__file__).resolve().parents[2] / "src" / "invest_ll" / "mcp"
PROHIBIDAS = ("activar", "real", "limite", "clave", "conexion", "credencial", "retirar")
_SOCKET_REAL = socket.socket
"""Se captura al importar, antes de que la suite corte la red (ver tests/integration/conftest.py)."""


def correr[T](corutina: Coroutine[Any, Any, T]) -> T:
    """Un bucle de asyncio para el servidor MCP. Todo bucle crea al arrancar un par de sockets
    para despertarse (sin red: entre sí, en la propia máquina); se le deja crearlos con el socket
    real y se vuelve a cortar en cuanto arranca."""
    bloqueado = socket.socket
    socket.socket = _SOCKET_REAL  # type: ignore[misc]
    try:
        bucle = asyncio.SelectorEventLoop()
    finally:
        socket.socket = bloqueado  # type: ignore[misc]
    try:
        return bucle.run_until_complete(corutina)
    finally:
        bucle.close()


class PanelSimulado:
    """La API del panel, contestada por un `httpx.MockTransport`: sin sockets."""

    def __init__(self) -> None:
        self.peticiones: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(peticion.content) if peticion.content else None
        self.peticiones.append((peticion.method, peticion.url.path, cuerpo))
        if peticion.method == "GET" and peticion.url.path == "/api/bots":
            bot = {
                "id": "cruce-aaaaaa",
                "nombre": "Cruce",
                "modo": "ficticio",
                "estado": "en_marcha",
            }
            return httpx.Response(200, json={"bots": [bot], "nota": "Dinero ficticio."})
        if peticion.method == "POST" and peticion.url.path == "/api/bots":
            assert cuerpo is not None
            return httpx.Response(
                201, json={"id": "mi-bot-123abc", **cuerpo, "estado": "en_marcha"}
            )
        if peticion.url.path.endswith("/parar"):
            return httpx.Response(
                200, json={"id": peticion.url.path.split("/")[3], "estado": "parado"}
            )
        return httpx.Response(404, json={"detail": "No existe esa dirección en el panel."})


def _conector() -> ConectorFalso:
    c = ConectorFalso()
    c.poner("BTC/USDT", serie("BTC", onda(400, periodo=30)))
    return c


def _servidor(
    tmp_path: Path, transporte: Callable[[httpx.Request], httpx.Response]
) -> tuple[MCPServer, Herramientas]:
    conector = _conector()
    h = Herramientas(
        biblioteca=Biblioteca(tmp_path / "medida"),
        panel=Panel(cliente=httpx.Client(transport=httpx.MockTransport(transporte))),
        conector_publico=lambda _e: conector,
        disponibles=lambda: ["falso"],
    )
    return crear_servidor(h), h


def llamar(s: MCPServer, nombre: str, argumentos: dict[str, Any] | None = None) -> Any:
    resultado = correr(s.call_tool(nombre, argumentos or {}))
    contenido = getattr(resultado, "content", None)
    assert contenido, resultado
    return json.loads(contenido[0].text)


@pytest.fixture
def panel() -> PanelSimulado:
    return PanelSimulado()


@pytest.fixture
def servidor(tmp_path: Path, panel: PanelSimulado) -> MCPServer:
    return _servidor(tmp_path, panel)[0]


class TestLoQueNoPuede:
    def test_son_exactamente_las_once(self, servidor: MCPServer) -> None:
        nombres = [t.name for t in correr(servidor.list_tools())]
        assert sorted(nombres) == sorted(HERRAMIENTAS)
        assert len(nombres) == 11

    def test_ninguna_herramienta_activa_real_cambia_limites_ni_toca_claves(
        self, servidor: MCPServer
    ) -> None:
        for t in correr(servidor.list_tools()):
            assert not any(p in t.name for p in PROHIBIDAS), t.name
            parametros = set(t.input_schema.get("properties", {}))
            assert not parametros & {"modo", "limites", "red", "claves", "confirmacion"}, t.name

    def test_el_panel_solo_tiene_tres_rutas(self) -> None:
        assert RUTAS == (("GET", "/bots"), ("POST", "/bots"), ("POST", "/bots/{id}/parar"))
        publicos = {n for n in dir(Panel) if not n.startswith("_")}
        assert publicos == {"bots", "desplegar_ficticio", "parar_bot"}

    def test_ningun_fichero_del_conector_nombra_las_rutas_de_dinero_real(self) -> None:
        rutas_prohibidas = (
            "activar-real",
            "/limites",
            "limite-diario",
            "bots-real",
            "parar-todo",
            "/conexiones",
            "/claves",
        )
        for fichero in FUENTE.rglob("*.py"):
            texto = fichero.read_text(encoding="utf-8")
            for ruta in rutas_prohibidas:
                assert ruta not in texto, f"{fichero.name} nombra {ruta}"

    def test_desplegar_siempre_es_ficticio_sin_exchange_ni_limites(
        self, servidor: MCPServer, panel: PanelSimulado
    ) -> None:
        estrategia = llamar(servidor, "guardar", {"definicion": CRUCE})["id"]
        # Aunque Claude intente colar el modo, el exchange o los límites, no llegan al panel.
        colado = {
            "estrategia": estrategia,
            "nombre": "Mi bot",
            "modo": "real",
            "exchange": "binance",
            "limites": {"capital_max": "1000000"},
        }
        llamar(servidor, "desplegar_ficticio", colado)
        metodo, ruta, cuerpo = panel.peticiones[-1]
        assert (metodo, ruta) == ("POST", "/api/bots")
        assert cuerpo is not None
        assert cuerpo["modo"] == "ficticio"
        assert cuerpo["plantilla"] == "medida"
        assert not set(cuerpo) & {"exchange", "limites"}

    def test_el_panel_solo_habla_con_este_equipo(self) -> None:
        with pytest.raises(PanelError, match="este equipo"):
            Panel("http://example.com/api")
        Panel("http://localhost:8601/api")

    def test_parar_bot_no_acepta_rutas(self, tmp_path: Path, panel: PanelSimulado) -> None:
        s, _ = _servidor(tmp_path, panel)
        with pytest.raises(ToolError, match="no es el id de un bot"):
            llamar(s, "parar_bot", {"bot": "../bots-real/parar-todo"})
        assert panel.peticiones == []


class TestUnaLlamadaDeCada:
    def test_exchanges_monedas_y_velas(self, servidor: MCPServer) -> None:
        assert llamar(servidor, "exchanges") == {"exchanges": ["falso"]}
        pares = llamar(servidor, "monedas", {"exchange": "falso", "buscar": "bt"})["pares"]
        assert [p["par"] for p in pares] == ["BTC/USDT"]
        velas = llamar(servidor, "velas", {"exchange": "falso", "moneda": "BTC", "cuantas": 5})
        assert velas["par"] == "BTC/USDT"
        assert len(velas["velas"]) <= 5

    def test_esquema(self, servidor: MCPServer) -> None:
        datos = llamar(servidor, "esquema")
        assert set(datos) == {"explicacion", "esquema", "ejemplos"}
        assert len(datos["ejemplos"]) == 4

    def test_validar(self, servidor: MCPServer) -> None:
        bien = llamar(servidor, "validar", {"definicion": CRUCE})
        assert bien["valida"] is True
        assert bien["velas_necesarias"] == 6
        mal = llamar(servidor, "validar", {"definicion": {**CRUCE, "entrar": {"eval": "1"}}})
        assert mal["valida"] is False
        assert "no es una condición" in mal["errores"][0]

    def test_guardar_estrategias_y_probar(self, servidor: MCPServer) -> None:
        guardada = llamar(servidor, "guardar", {"definicion": json.dumps(CRUCE), "nota": "primera"})
        assert guardada["version"] == 1
        assert guardada["estado"] == "borrador"
        lista = llamar(servidor, "estrategias")["estrategias"]
        assert [e["id"] for e in lista] == [guardada["id"]]
        periodo = {"desde": "2025-01-15", "hasta": "2026-02-01"}
        prueba = llamar(
            servidor, "probar", {"estrategia": guardada["id"], "exchange": "falso", **periodo}
        )
        assert prueba["versiones_probadas"] == 1
        assert prueba["aviso_sobreajuste"] is None
        assert "curva" not in prueba
        # Muchas operaciones: las primeras y las últimas (la última puede seguir abierta).
        detalle = prueba["operaciones_detalle"]
        assert prueba["operaciones"] > 20
        assert len(detalle) == 21
        assert "más) …" in detalle[10]
        assert isinstance(prueba["abiertas_al_final"], list)
        ficha = llamar(servidor, "estrategias", {"estrategia": guardada["id"]})
        assert ficha["estado"] == "probada"
        assert ficha["definicion"]["intervalo"] == "1d"
        assert ficha["ultima_prueba"]["operaciones"] == prueba["operaciones"]

    def test_guardar_lo_que_no_vale_vuelve_en_llano(self, servidor: MCPServer) -> None:
        with pytest.raises(ToolError, match="La estrategia no vale"):
            llamar(servidor, "guardar", {"definicion": {**CRUCE, "intervalo": "1m"}})
        with pytest.raises(ToolError, match="no es un JSON válido"):
            llamar(servidor, "guardar", {"definicion": "{roto"})

    def test_probar_una_que_no_existe(self, servidor: MCPServer) -> None:
        with pytest.raises(ToolError, match="No hay ninguna estrategia"):
            llamar(servidor, "probar", {"estrategia": "no-existe-000000"})

    def test_bots_desplegar_y_parar(self, servidor: MCPServer, panel: PanelSimulado) -> None:
        estrategia = llamar(servidor, "guardar", {"definicion": CRUCE})["id"]
        hecho = llamar(servidor, "desplegar_ficticio", {"estrategia": estrategia, "capital": 500})
        assert hecho["bot"] == "mi-bot-123abc"
        assert hecho["modo"] == "ficticio"
        assert panel.peticiones[-1][2] == {
            "plantilla": "medida",
            "estrategia": estrategia,
            "nombre": "Cruce de medias",
            "monedas": ["BTC"],
            "capital": "500",
            "modo": "ficticio",
        }
        assert llamar(servidor, "bots")["bots"][0]["id"] == "cruce-aaaaaa"
        assert llamar(servidor, "parar_bot", {"bot": "mi-bot-123abc"}) == {
            "bot": "mi-bot-123abc",
            "estado": "parado",
        }
        assert [(m, r) for m, r, _ in panel.peticiones] == [
            ("POST", "/api/bots"),
            ("GET", "/api/bots"),
            ("POST", "/api/bots/mi-bot-123abc/parar"),
        ]


class TestSinPanel:
    def test_si_el_panel_no_esta_abierto_lo_dice(self, tmp_path: Path) -> None:
        def cerrado(peticion: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("conexión rechazada", request=peticion)

        s, _ = _servidor(tmp_path, cerrado)
        with pytest.raises(ToolError, match="no está abierto"):
            llamar(s, "bots")

    def test_lo_que_el_panel_rechaza_llega_en_llano(self, tmp_path: Path) -> None:
        def rechaza(peticion: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"detail": "No hay ninguna plantilla «medida»."})

        s, h = _servidor(tmp_path, rechaza)
        estrategia = h.guardar(CRUCE, "", None)["id"]
        with pytest.raises(ToolError, match="plantilla «medida»"):
            llamar(s, "desplegar_ficticio", {"estrategia": estrategia})

    def test_sin_conectores_de_exchanges_lo_dice(self, tmp_path: Path) -> None:
        def sin(_exchange: str) -> ConectorFalso:
            raise NotImplementedError

        h = Herramientas(biblioteca=Biblioteca(tmp_path), panel=Panel(), conector_publico=sin)
        with pytest.raises(ToolError, match="aún no trae los conectores"):
            llamar(crear_servidor(h), "monedas", {"exchange": "binance"})


def test_se_arranca_como_modulo() -> None:
    """`python -m invest_ll.mcp` (como lo lanza el panel) y el script `invest-ll-mcp`."""
    proceso = subprocess.run(
        [sys.executable, "-m", "invest_ll.mcp", "--help"],
        capture_output=True,
        timeout=120,
        check=False,
    )
    salida = proceso.stdout.decode("utf-8", errors="replace")
    assert proceso.returncode == 0, proceso.stderr
    assert "No puede activar dinero real" in salida
    pyproject = (FUENTE.parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'invest-ll-mcp = "invest_ll.mcp.servidor:main"' in pyproject
    assert modulo_panel.URL == "http://127.0.0.1:8601/api"
