"""El conector falso que usan los tests de todos: que haga lo que promete el protocolo y que deje
provocar rechazos, cortes y caídas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from invest_ll.exchanges.conector import Conector, EstadoDesconocidoError, ExchangeError
from invest_ll.exchanges.falso import ConectorFalso, con_velas, redondear_abajo
from invest_ll.vivo.fuente import Libro, Nivel, Vela

D = Decimal
T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _falso() -> ConectorFalso:
    falso = ConectorFalso("binance", "pruebas", saldo_inicial={"USDT": D(1000)})
    falso.poner_precio("BTC/USDT", D(50000))
    return falso


def test_cumple_el_protocolo() -> None:
    conector: Conector = _falso()
    assert (conector.exchange, conector.red) == ("binance", "pruebas")


def test_una_compra_a_mercado_mueve_el_saldo_y_cobra_comision() -> None:
    falso = _falso()
    orden = falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="o1")
    assert orden.estado == "ejecutada"
    assert orden.comision == D("0.5")
    assert orden.comision_moneda == "USDT"
    assert falso.saldo() == {"USDT": D("499.5"), "BTC": D("0.01")}


def test_un_reintento_no_duplica() -> None:
    falso = _falso()
    falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="o1")
    falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="o1")
    assert len(falso.creadas) == 1


def test_redondea_y_exige_los_minimos() -> None:
    falso = _falso()
    assert falso.enviar("BTC/USDT", "compra", D("0.0123456"), id_cliente="o1").cantidad == D(
        "0.01234"
    )
    with pytest.raises(ExchangeError, match="importe mínimo"):
        falso.enviar("BTC/USDT", "compra", D("0.00005"), id_cliente="o2")
    with pytest.raises(ExchangeError, match="se queda en cero"):
        falso.enviar("BTC/USDT", "compra", D("0.000001"), id_cliente="o3")
    assert redondear_abajo(D("1.239"), D("0.01")) == D("1.23")


def test_sin_saldo_la_orden_queda_rechazada() -> None:
    falso = _falso()
    assert falso.enviar("BTC/USDT", "compra", D(1), id_cliente="o1").estado == "rechazada"


def test_rechazar_la_siguiente() -> None:
    falso = _falso()
    falso.rechazar_siguiente("Filtro LOT_SIZE")
    with pytest.raises(ExchangeError, match="LOT_SIZE"):
        falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="o1")
    assert falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="o1").estado == "ejecutada"


@pytest.mark.parametrize("ejecutada", [True, False])
def test_cortar_la_siguiente_y_resolverla_con_orden(ejecutada: bool) -> None:
    falso = _falso()
    falso.cortar_siguiente(ejecutada=ejecutada)
    with pytest.raises(EstadoDesconocidoError):
        falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="o1")
    resuelta = falso.orden("BTC/USDT", id_cliente="o1")
    assert (resuelta is not None) == ejecutada
    if resuelta is not None:
        assert resuelta.estado == "ejecutada"


def test_caido_no_contesta() -> None:
    falso = _falso()
    falso.caer()
    with pytest.raises(ExchangeError, match="No hay conexión"):
        falso.saldo()
    falso.levantar()
    assert falso.saldo()


def test_las_limites_esperan_y_se_casan_al_moverse_el_precio() -> None:
    falso = _falso()
    orden = falso.enviar(
        "BTC/USDT", "compra", D("0.01"), id_cliente="l1", tipo="limite", precio=D(45000)
    )
    assert orden.estado == "abierta"
    assert [o.id_cliente for o in falso.ordenes_abiertas()] == ["l1"]
    falso.poner_precio("BTC/USDT", D(44000))
    assert [o.id_cliente for o in falso.casar("BTC/USDT")] == ["l1"]
    assert falso.orden("BTC/USDT", id_cliente="l1").estado == "ejecutada"  # type: ignore[union-attr]
    assert falso.ordenes_abiertas() == []


def test_cancelar() -> None:
    falso = _falso()
    falso.enviar("BTC/USDT", "venta", D("0.01"), id_cliente="l1", tipo="limite", precio=D(70000))
    cancelada = falso.cancelar("BTC/USDT", id_cliente="l1")
    assert cancelada is not None
    assert cancelada.estado == "cancelada"
    assert falso.cancelar("BTC/USDT", id_cliente="no") is None


def test_libro_y_velas() -> None:
    falso = _falso()
    falso.libros["ETH/USDT"] = Libro(
        coin="ETH/USDT",
        compras=tuple(Nivel(D(3000 - i), D(1)) for i in range(30)),
        ventas=tuple(Nivel(D(3001 + i), D(1)) for i in range(30)),
        at=T0,
    )
    libro = falso.libro("ETH/USDT", niveles=5)
    assert libro is not None
    assert len(libro.compras) == 5
    assert falso.precio("ETH/USDT") == D("3000.5")

    velas = [
        Vela(
            coin="BTC/USDT",
            intervalo="1h",
            inicio=T0 + timedelta(hours=i),
            fin=T0 + timedelta(hours=i + 1),
            apertura=D(1),
            maximo=D(1),
            minimo=D(1),
            cierre=D(i),
            volumen=D(1),
            cerrada=True,
        )
        for i in range(10)
    ]
    con_velas(falso, reversed(velas))
    assert [v.cierre for v in falso.velas("BTC/USDT", "1h", limite=3)] == [D(7), D(8), D(9)]
    desde = falso.velas("BTC/USDT", "1h", desde=T0 + timedelta(hours=2), limite=2)
    assert [v.cierre for v in desde] == [D(2), D(3)]


def test_un_par_que_no_tiene() -> None:
    with pytest.raises(ExchangeError, match="no tiene el par DOGE/USDT"):
        _falso().precio("DOGE/USDT")
