"""La comprobación de verdad (`python -m invest_ll.exchanges.comprobar`), aquí sin red: con el
conector falso, que dice lo mismo que diría un exchange."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from invest_ll.exchanges import comprobar, registro
from invest_ll.exchanges.falso import ConectorFalso, con_velas, mercado_falso
from invest_ll.vivo.fuente import Libro, Nivel, Vela

D = Decimal
T0 = datetime(2026, 10, 17, tzinfo=UTC)


def _falso() -> ConectorFalso:
    falso = ConectorFalso("kraken", "real", mercados_=(mercado_falso("BTC", "USD"),))
    falso.poner_precio("BTC/USD", D(81000))
    falso.libros["BTC/USD"] = Libro(
        coin="BTC/USD", compras=(Nivel(D(80999), D(1)),), ventas=(Nivel(D(81001), D(1)),), at=T0
    )
    vela = Vela(
        coin="BTC/USD",
        intervalo="1h",
        inicio=T0,
        fin=T0 + timedelta(hours=1),
        apertura=D(1),
        maximo=D(1),
        minimo=D(1),
        cierre=D(81000),
        volumen=D(1),
        cerrada=False,
    )
    return con_velas(falso, [vela])


def test_un_exchange_que_responde() -> None:
    resultado = comprobar.comprobar("kraken", _falso())
    assert resultado.ok
    assert resultado.par == "BTC/USD"
    assert [nombre for nombre, _, _ in resultado.pasos] == ["mercados", "precio", "libro", "velas"]


def test_un_exchange_caido_lo_dice_y_no_sigue() -> None:
    falso = _falso()
    falso.caer("No hay conexión con Kraken.")
    resultado = comprobar.comprobar("kraken", falso)
    assert not resultado.ok
    assert resultado.pasos[0][2].startswith("No hay conexión con Kraken.")
    assert len(resultado.pasos) == 1


def test_el_par_de_btc_de_cada_uno() -> None:
    mercados = [
        mercado_falso("ETH", "USDC"),
        mercado_falso("XBT", "USD"),
        mercado_falso("BTC", "USDC"),
    ]
    assert comprobar.par_de_btc(mercados, "BTC/USDT") == "BTC/USDC"
    assert comprobar.par_de_btc(mercados[:2], "BTC/USDT") == "XBT/USD"
    assert comprobar.par_de_btc(mercados[:1], "BTC/USDT") is None


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    registro.inyectar("kraken", _falso())
    assert comprobar.main(["kraken"]) == 0
    salida = capsys.readouterr().out
    assert "kraken [bien] par BTC/USD" in salida
    assert "ok  velas" in salida
