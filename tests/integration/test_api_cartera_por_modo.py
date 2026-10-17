"""Cada modo, su cartera; y lo que se ejecuta pasa solo a la del modo en que salió.

Real (y simulación) → `portfolio/`; pruebas → `portfolio-pruebas/`. Los precios de la red de
pruebas no son los del mercado: mezclarlos con dinero de verdad corrompería el historial.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from invest_ll.api import cartera as rutas_cartera
from invest_ll.live.broker import Confirmation, OrderRequest, OrderResult, OrderStatus

from .test_api_cartera import BrokerFalso

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.live.mode import OperatingMode

    from .api_apoyo import Api

D = Decimal
REAL = Path("portfolio/activities.jsonl")
PRUEBAS = Path("portfolio-pruebas/activities.jsonl")
ORDEN = {"par": "BTC/USDT", "lado": "buy", "cantidad": "0.001", "escrito": "0.001"}


class SinComision(BrokerFalso):
    """El exchange no dijo la comisión: `from_orders` no la importa, y hay que decirlo."""

    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult:
        resultado = super().submit(request, confirmation=confirmation)
        return OrderResult(
            request=resultado.request,
            status=resultado.status,
            filled_quantity=resultado.filled_quantity,
            fill_price=resultado.fill_price,
            executed_at=resultado.executed_at,
            broker_reference=resultado.broker_reference,
            commission=None,
        )


@pytest.fixture
def en_pruebas(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> Api:
    monkeypatch.setenv("INVEST_LL_MODE", "testnet")
    monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "clave")
    monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "secreto")
    return cliente


def _broker(
    monkeypatch: pytest.MonkeyPatch,
    clase: type[BrokerFalso] = BrokerFalso,
    estado: OrderStatus = OrderStatus.FILLED,
) -> None:
    def fabrica(modo: OperatingMode) -> BrokerFalso:
        return clase(modo, estado)

    monkeypatch.setattr(rutas_cartera, "broker_para", fabrica)


def test_lo_ejecutado_en_pruebas_pasa_solo_a_la_cartera_de_pruebas(
    en_pruebas: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _broker(monkeypatch)

    r = en_pruebas.post("/api/ordenes", json=ORDEN)

    assert r.status_code == 200
    assert r.json()["descripcion"] == "BTC/USDT: ejecutada 0.001 a 90000.", "sin nada que avisar"
    assert PRUEBAS.exists()
    assert not REAL.exists(), "las pruebas no entran en la cartera real"
    (mov,) = en_pruebas.get("/api/cartera/movimientos").json()["movimientos"]
    assert (mov["tipo"], mov["simbolo"], mov["activo"]) == ("compra", "BTC/USDT", "Bitcoin")
    assert mov["origen"] == "ledger:pruebas:ref-1"
    assert D(mov["comision"]) == D("0.09")
    cartera = en_pruebas.get("/api/cartera").json()
    assert cartera["abiertas"][0]["activo"] == "BTC/USDT"


def test_sin_comision_no_entra_y_se_dice(en_pruebas: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    _broker(monkeypatch, SinComision)

    r = en_pruebas.post("/api/ordenes", json=ORDEN)

    assert r.status_code == 200
    assert "No ha pasado a tu cartera" in r.json()["descripcion"]
    assert "sin comision registrada" in r.json()["descripcion"]
    assert en_pruebas.get("/api/cartera/movimientos").json()["movimientos"] == []


def test_una_rechazada_no_toca_la_cartera(en_pruebas: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    _broker(monkeypatch, estado=OrderStatus.REJECTED)
    r = en_pruebas.post("/api/ordenes", json=ORDEN)
    assert r.json()["estado"] == "rejected"
    assert r.json()["descripcion"] == "BTC/USDT: rechazada."
    assert not PRUEBAS.exists()


def test_anotar_a_mano_va_a_la_cartera_del_modo(en_pruebas: Api) -> None:
    deposito = {"tipo": "deposito", "fecha": "2026-09-01", "cantidad": "5000"}
    assert en_pruebas.post("/api/cartera/movimientos", json=deposito).status_code == 201
    assert PRUEBAS.exists() and not REAL.exists()
    (mov,) = en_pruebas.get("/api/cartera/movimientos").json()["movimientos"]
    assert (mov["tipo"], mov["activo"], mov["precio"], mov["importe"]) == (
        "ingreso",
        None,
        None,
        "5000",
    )


def test_en_simulacion_se_ve_la_real_la_mas_reciente_primero(cliente: Api) -> None:
    for fecha, cantidad in (("2026-09-01", "100"), ("2026-09-10", "50")):
        cliente.post(
            "/api/cartera/movimientos",
            json={"tipo": "deposito", "fecha": fecha, "cantidad": cantidad},
        )
    cuerpo = cliente.get("/api/cartera/movimientos").json()
    assert cuerpo["cartera"] == "real"
    assert [m["cantidad"] for m in cuerpo["movimientos"]] == ["50", "100"]
    assert REAL.exists()
