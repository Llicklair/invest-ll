"""T007 — el motor no toca la red (FR-001..FR-003, SC-003). ★

El test más importante de la feature 002, y el que más valor tendrá dentro de seis meses cuando
nadie recuerde por qué existe esta separación.

Dos comprobaciones, porque ninguna basta sola:

- **Estática**: detecta el import el día que alguien lo añade, aunque todavía no se use. Así es
  como empiezan estas cosas — un import "temporal" para depurar algo.
- **Dinámica**: demuestra que en ejecución tampoco se abre una conexión por una vía que el análisis
  estático no vea (un import diferido dentro de una función, por ejemplo).
"""

from __future__ import annotations

import ast
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.builders import series_from_closes, v_shape

# Paquetes que el motor no puede conocer. Los tres primeros son red directa; ccxt y yfinance son
# red envuelta; `invest_ll.fetch` es nuestra propia capa de descarga.
PROHIBIDOS = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "httplib",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ccxt",
        "yfinance",
    }
)

RAIZ_MOTOR = Path(__file__).resolve().parents[2] / "src" / "invest_ll"
SUBPAQUETES_MOTOR = ("engine", "report", "strategy")


def modulos_del_motor() -> list[Path]:
    ficheros: list[Path] = []
    for sub in SUBPAQUETES_MOTOR:
        ficheros.extend((RAIZ_MOTOR / sub).rglob("*.py"))
    return ficheros


def imports_de(fichero: Path) -> set[str]:
    """Todos los módulos importados, incluidos los que están dentro de funciones."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module)
    return nombres


def raices(nombres: set[str]) -> set[str]:
    return {nombre.split(".")[0] for nombre in nombres}


def test_hay_modulos_que_analizar() -> None:
    """Si el análisis no encuentra ficheros, pasaría en vacío y no probaría nada."""
    assert len(modulos_del_motor()) >= 5


@pytest.mark.parametrize("fichero", modulos_del_motor(), ids=lambda p: p.name)
def test_ningun_modulo_del_motor_importa_red(fichero: Path) -> None:
    """FR-001: el motor no puede adquirir dependencias de red."""
    encontrados = raices(imports_de(fichero)) & PROHIBIDOS
    assert not encontrados, (
        f"{fichero.relative_to(RAIZ_MOTOR)} importa {sorted(encontrados)}. "
        "El motor de backtesting no puede tocar la red (Principio I, FR-006 de la 001)."
    )


@pytest.mark.parametrize("fichero", modulos_del_motor(), ids=lambda p: p.name)
def test_el_motor_no_importa_la_capa_de_descarga(fichero: Path) -> None:
    """FR-003: la comunicación entre ambos es por ficheros, no por llamadas."""
    for nombre in imports_de(fichero):
        assert not nombre.startswith("invest_ll.fetch"), (
            f"{fichero.relative_to(RAIZ_MOTOR)} importa la capa de descarga. "
            "El motor consume ficheros; no invoca la descarga."
        )


def test_la_capa_de_descarga_no_importa_el_motor_de_ejecucion() -> None:
    """La dependencia va en un solo sentido.

    `fetch` sí puede usar `data` (necesita Bar, Interval y PriceSeries para producir lo que el
    motor espera), pero no debe depender de `engine` ni de `report`: si lo hiciera, la separación
    sería mutua y el sentido de la flecha dejaría de estar claro.
    """
    fetch = RAIZ_MOTOR / "fetch"
    if not fetch.exists():  # pragma: no cover - antes de crear el paquete
        pytest.skip("la capa de descarga aún no existe")

    for fichero in fetch.rglob("*.py"):
        for nombre in imports_de(fichero):
            assert not nombre.startswith(("invest_ll.engine", "invest_ll.report")), (
                f"{fichero.name} importa {nombre}: la descarga no debe depender del motor"
            )


def test_un_backtest_completo_funciona_con_la_red_cortada() -> None:
    """La prueba definitiva: si termina, no hubo conexión.

    El fixture global ya bloquea `socket`, pero aquí se bloquea de nuevo de forma explícita para
    que este test siga probando lo que dice probar aunque alguien cambie el conftest.
    """
    original = socket.socket

    def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError("el motor de backtesting abrió una conexión de red")

    socket.socket = prohibido  # type: ignore[assignment]
    try:
        report = run_backtest(
            series_from_closes(v_shape(120)),
            MovingAverageCrossover(short=5, long=20),
            initial_capital=Decimal(10000),
            friction=FrictionConfig(
                commission_rate=Decimal("0.001"), slippage_rate=Decimal("0.0005")
            ),
            risk=RiskConfig(position_fraction=Decimal("0.5")),
        )
    finally:
        socket.socket = original  # type: ignore[assignment]

    assert report.trade_count >= 0
    assert report.render()
