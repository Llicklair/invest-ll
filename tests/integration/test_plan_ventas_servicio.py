"""Las ventas del bróker con la estrategia de verdad: sin fijar a mano lo que quiere.

Sobre paneles sintéticos donde un fondo (EEM) lleva más de un año bajando, la Prudente con freno
lo deja fuera por sí sola (`objetivo.de_hoy`), y "qué toca hoy" (`servicio.calcular_hoy`) pide
venderlo a quien lo compró con el plan. Con los mismos datos, Equilibrada y Bolsa de EE.UU. no
piden vender nada.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from invest_ll.estrategias import datos, objetivo
from invest_ll.estrategias.catalogo import ficha
from invest_ll.plan import servicio
from invest_ll.plan.almacen import Parte, Plan
from invest_ll.plan.hoy import FUENTE_PLAN
from invest_ll.portfolio.models import Activity, ActivityType

from ..fixtures.paneles_v2 import escribir_paneles

D = Decimal
CREADO = datetime(2026, 10, 1, 9, tzinfo=UTC)
COMPRA = date(2026, 10, 1)
HOY = date(2026, 10, 17)


@pytest.fixture(autouse=True)
def eem_bajando(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    escribir_paneles(cripto=False, cae="EEM")


def _plan(clave: str) -> Plan:
    return Plan(
        partes=(Parte(estrategia=clave, inicial=D("10000"), mensual=D("0")),),
        dia_del_mes=1,
        creado=CREADO,
        actualizado=CREADO,
    )


def _compras(reparto: dict[str, str]) -> list[Activity]:
    """Lo que el plan compró el 1 de octubre, en unidades del fondo de referencia (como `hecho`)."""
    compras: list[Activity] = []
    for simbolo, euros in reparto.items():
        visto = datos.cierre_hasta(simbolo, COMPRA)
        assert visto is not None
        compras.append(
            Activity(
                timestamp=datetime(COMPRA.year, COMPRA.month, COMPRA.day, tzinfo=UTC),
                type=ActivityType.BUY,
                symbol=simbolo,
                quantity=(D(euros) / visto.precio).quantize(D("0.00000001"), ROUND_HALF_UP),
                unit_price=visto.precio,
                source=FUENTE_PLAN,
            )
        )
    return compras


def test_la_prudente_deja_fuera_el_fondo_que_baja_y_pide_venderlo() -> None:
    prudente = ficha("bolsa-prudente")
    assert prudente is not None
    quiere = objetivo.de_hoy(prudente)
    assert quiere is not None
    assert "EEM" not in quiere.pesos, "el freno de tendencia lo ha sacado"
    assert quiere.pesos.get("SHY", 0) > 0

    # Compró antes de que saliera: un 20 % en EEM y el resto como quiere hoy la estrategia.
    resto = {s: str((D(8000) * D(str(w))).quantize(D("0.01"))) for s, w in quiere.pesos.items()}
    actividades = _compras({"EEM": "2000", **resto})

    r = servicio.calcular_hoy(
        _plan("bolsa-prudente"), actividades, hoy=HOY, pausa=None, actividades_bolsa=actividades
    )

    venta, *compras = r.acciones
    assert (venta.donde, venta.simbolo, venta.lado, venta.todo) == ("broker", "EEM", "sell", True)
    assert venta.titulo.startswith("Vende todo tu ETF de mercados emergentes (unos ")
    assert venta.explicacion.startswith("Lleva meses bajando: tu estrategia sale de él")
    assert venta.cantidad == actividades[0].quantity.quantize(D("0.0001"), rounding=ROUND_DOWN)
    assert compras, "lo que saca va a la lista de la compra"
    assert all(c.lado == "buy" and c.simbolo != "EEM" for c in compras)
    liberado = sum((c.importe for c in compras), D(0))
    assert liberado == pytest.approx(venta.importe, abs=D("0.05")), "se reinvierte entero"
    assert r.resumen.startswith("Hoy toca: 1 venta y ")


@pytest.mark.parametrize(
    ("clave", "reparto"),
    [
        ("bolsa-equilibrada", {"SPY": "6000", "IEF": "4000"}),
        ("bolsa-eeuu", {"SPY": "10000"}),
    ],
)
def test_equilibrada_y_eeuu_no_piden_vender_con_los_mismos_datos(
    clave: str, reparto: dict[str, str]
) -> None:
    actividades = _compras(reparto)
    r = servicio.calcular_hoy(
        _plan(clave), actividades, hoy=HOY, pausa=None, actividades_bolsa=actividades
    )
    assert [a for a in r.acciones if a.lado == "sell"] == []
