"""La suite entera corre sin red y sin gastar una llamada al modelo (T078 · FR-036, SC-011).

Es una garantia estructural, no una convencion: `conftest.py` bloquea los sockets, asi que
cualquier codigo que intentara salir fallaria de forma ruidosa. Estos tests comprueban que la
garantia sigue en pie y que nadie la ha desactivado sin darse cuenta.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FUENTE = RAIZ / "src" / "invest_ll"


def test_los_sockets_estan_bloqueados_en_esta_suite() -> None:
    """Si esto falla, el resto de garantias de aislamiento dejan de valer nada."""
    with pytest.raises(Exception, match=r"(?i)socket|network|red|bloquea"):
        socket.socket().connect(("example.com", 80))


def test_solo_dos_modulos_pueden_salir_a_la_red() -> None:
    """La red esta confinada. Cualquier modulo nuevo que la use tiene que declararse aqui,
    lo cual obliga a pensarlo en vez de que ocurra por descuido."""
    permitidos = {
        "fetch",  # descarga de historico (feature 002)
        "decision",  # el proveedor del LLM
        "analysis",  # datos fundamentales
        "live",  # ejecucion de ordenes
    }
    # Dentro de un subpaquete que no sale a la red, un unico modulo que si: lo demas del
    # subpaquete (interpretar mensajes, la cuenta de practica) se prueba sin red.
    modulos_permitidos = {
        "vivo/red.py",  # la conexion con Hyperliquid (panel v3, precios en vivo)
        "exchanges/red_ccxt.py",  # construir el exchange de ccxt (panel v4, conectores)
    }
    clientes = (
        "anthropic",
        "ccxt",
        "yfinance",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "websockets",
        "aiohttp",
    )

    infractores: list[str] = []
    for fichero in FUENTE.rglob("*.py"):
        subpaquete = fichero.relative_to(FUENTE).parts[0]
        if subpaquete in permitidos or fichero.relative_to(FUENTE).as_posix() in modulos_permitidos:
            continue
        arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
        for nodo in ast.walk(arbol):
            nombres: list[str] = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres = [nodo.module]
            for nombre in nombres:
                if nombre.split(".")[0] in clientes:
                    infractores.append(f"{fichero.relative_to(FUENTE)} importa {nombre}")

    assert not infractores, "modulos que salen a la red sin estar declarados: " + str(infractores)
    for modulo in modulos_permitidos:
        assert (FUENTE / modulo).exists(), f"{modulo} ya no existe: quitalo de la lista"


def test_la_conexion_en_vivo_solo_se_importa_al_arrancar_el_panel() -> None:
    """`vivo/red.py` sale a la red; nadie lo importa al cargar un modulo, solo
    `servicio.arrancar()` (que solo llama el lanzador del panel, nunca los tests)."""
    importadores: list[str] = []
    for fichero in FUENTE.rglob("*.py"):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
        for nodo in arbol.body:  # solo lo de nivel de modulo: lo que se ejecuta al importar
            if not isinstance(nodo, ast.ImportFrom | ast.Import):
                continue
            nombres = (
                [a.name for a in nodo.names]
                if isinstance(nodo, ast.Import)
                else [f"{nodo.module}.{a.name}" for a in nodo.names] + [nodo.module or ""]
            )
            if "invest_ll.vivo.red" in nombres:
                importadores.append(str(fichero.relative_to(FUENTE)))
    assert not importadores, f"importan la conexion en vivo al cargarse: {importadores}"


def test_ningun_test_llama_al_modelo_de_verdad() -> None:
    """FR-036: los tests no pueden gastar llamadas de pago.

    Se comprueba que ningun test construye un cliente de Anthropic real.
    """
    # Este fichero se excluye: contiene los patrones que busca, por definicion.
    yo = Path(__file__).resolve()
    infractores: list[str] = []
    for fichero in (RAIZ / "tests").rglob("*.py"):
        if fichero.resolve() == yo:
            continue
        texto = fichero.read_text(encoding="utf-8")
        if "anthropic.Anthropic(" in texto or "AnthropicProvider(Anthropic" in texto:
            infractores.append(fichero.name)
    assert not infractores, f"tests que construyen un cliente real: {infractores}"


def test_las_credenciales_no_estan_en_el_repositorio() -> None:
    """FR-033: se leen del entorno y nunca se commitean."""
    # Los patrones se construyen por partes para que este fichero no se detecte a si mismo.
    sospechosos = ("sk-" + "ant-", "ANTHROPIC_API_KEY=" + "sk", "BINANCE_" + "SECRET=")
    yo = Path(__file__).resolve()
    infractores: list[str] = []
    for fichero in list(FUENTE.rglob("*.py")) + list((RAIZ / "tests").rglob("*.py")):
        if fichero.resolve() == yo:
            continue
        texto = fichero.read_text(encoding="utf-8")
        for patron in sospechosos:
            if patron in texto:
                infractores.append(f"{fichero.name}: {patron}")
    assert not infractores, f"posibles credenciales en el codigo: {infractores}"
