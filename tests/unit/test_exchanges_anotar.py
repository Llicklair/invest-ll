"""Anotar en el registro una orden de un conector: lo que deja la evidencia de pruebas."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.exchanges import activacion
from invest_ll.exchanges.activacion import ConfigExchanges
from invest_ll.exchanges.anotar import anotar, comision_en_la_cotizada, resultado_de
from invest_ll.exchanges.falso import ConectorFalso
from invest_ll.exchanges.fichas import BYBIT
from invest_ll.live.broker import OrderStatus
from invest_ll.live.ledger import ExecutionLedger

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

D = Decimal


def _ejecutada() -> ConectorFalso:
    falso = ConectorFalso("bybit", "pruebas", saldo_inicial={"USDT": D(1000)})
    falso.poner_precio("BTC/USDT", D(50000))
    return falso


def test_una_orden_de_pruebas_anotada_es_la_evidencia(tmp_path: Path) -> None:
    falso = _ejecutada()
    orden = falso.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="bot-1")
    ledger = ExecutionLedger(tmp_path / "ledger")

    entrada = anotar(orden, exchange="bybit", red="pruebas", bot="rebote", ledger=ledger)

    assert (entrada.mode_name, entrada.exchange, entrada.bot) == ("pruebas", "bybit", "rebote")
    assert entrada.result.status is OrderStatus.FILLED
    assert entrada.result.commission == D("0.5")
    estado = activacion.leer(
        BYBIT, entorno={}, config=ConfigExchanges(tmp_path / "config"), registro=ledger
    )
    assert estado.ordenes["pruebas"] == 1


def test_real_se_anota_como_real(tmp_path: Path) -> None:
    orden = _ejecutada().enviar("BTC/USDT", "compra", D("0.01"), id_cliente="bot-1")
    entrada = anotar(orden, exchange="bybit", red="real", ledger=ExecutionLedger(tmp_path))
    assert entrada.was_real_money


def test_una_abierta_no_se_anota() -> None:
    falso = _ejecutada()
    abierta = falso.enviar(
        "BTC/USDT", "compra", D("0.01"), id_cliente="l1", tipo="limite", precio=D(40000)
    )
    with pytest.raises(ValueError, match="sigue abierta"):
        resultado_de(abierta)


def test_estados() -> None:
    orden = _ejecutada().enviar("BTC/USDT", "compra", D("0.01"), id_cliente="bot-1")
    assert resultado_de(replace(orden, estado="desconocido")).status is OrderStatus.UNKNOWN
    cancelada = replace(orden, estado="cancelada", ejecutada=D(0))
    assert resultado_de(cancelada).status is OrderStatus.REJECTED
    parcial = replace(orden, estado="parcial", ejecutada=D("0.004"))
    assert resultado_de(parcial).status is OrderStatus.PARTIAL


def test_la_comision_en_la_moneda_cotizada() -> None:
    orden = _ejecutada().enviar("BTC/USDT", "compra", D("0.01"), id_cliente="bot-1")
    en_btc = replace(orden, comision=D("0.00001"), comision_moneda="BTC")
    assert comision_en_la_cotizada(en_btc) == D("0.5")
    en_bnb = replace(orden, comision=D("0.001"), comision_moneda="BNB")
    assert comision_en_la_cotizada(en_bnb) is None
    assert resultado_de(en_bnb).commission is None
