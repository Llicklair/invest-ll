"""Tu dinero hoy: valor con su fecha, y sin inventar lo que falta."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.models import Activity, ActivityType
from invest_ll.portfolio.valoracion import valorar

D = Decimal


def _mov(
    tipo: ActivityType, simbolo: str | None, cantidad: str, precio: str = "1", comision: str = "0"
) -> Activity:
    return Activity(
        timestamp=datetime(2026, 9, 1, tzinfo=UTC),
        type=tipo,
        symbol=simbolo,
        quantity=D(cantidad),
        unit_price=D(precio),
        fee=D(comision),
    )


PRECIOS = {"SPY": (D(110), date(2026, 10, 16)), "BTC/USDT": (D(60000), date(2026, 10, 15))}


def test_valor_puesto_y_ganancia_con_la_fecha_mas_antigua() -> None:
    cartera = derive_portfolio(
        [
            _mov(ActivityType.DEPOSIT, None, "2000"),
            _mov(ActivityType.BUY, "SPY", "10", "100", "2"),
            _mov(ActivityType.BUY, "BTC/USDT", "0.01", "50000", "0.5"),
        ]
    )
    v = valorar(cartera, PRECIOS.get)

    # Efectivo: 2000 - 1002 - 500,5 = 497,5
    assert v.valor == D("1100") + D("600") + D("497.5")
    assert v.puesto == D("1002") + D("500.5") + D("497.5")
    assert v.ganancia == D("98") + D("99.5")
    assert v.fecha_precios == date(2026, 10, 15)
    assert v.incompleto is False
    assert (
        v.ganancia_pct is not None and abs(v.ganancia_pct - float(D("197.5") / D("2000"))) < 1e-12
    )


def test_el_efectivo_negativo_no_resta() -> None:
    """Sin depósitos anotados el efectivo derivado es negativo: no es una deuda."""
    cartera = derive_portfolio([_mov(ActivityType.BUY, "SPY", "10", "100")])
    v = valorar(cartera, PRECIOS.get)
    assert v.valor == D("1100")
    assert v.puesto == D("1000")


def test_sin_precio_de_algo_no_hay_total() -> None:
    cartera = derive_portfolio([_mov(ActivityType.BUY, "XYZ", "1", "10")])
    v = valorar(cartera, PRECIOS.get)
    assert v.valor is None
    assert v.ganancia is None
    assert v.incompleto is True
    assert v.puesto == D("10")


def test_solo_una_parte() -> None:
    cartera = derive_portfolio(
        [
            _mov(ActivityType.BUY, "SPY", "10", "100"),
            _mov(ActivityType.BUY, "BTC/USDT", "0.01", "50000"),
        ]
    )
    v = valorar(cartera, PRECIOS.get, solo=lambda s: s == "SPY", con_efectivo=False)
    assert (v.valor, v.puesto) == (D("1100"), D("1000"))
