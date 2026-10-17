"""Operar de verdad desde el panel (`/api/operar/{exchange}`): con un exchange falso, nunca con
Hyperliquid de verdad. Lo que se comprueba es lo que protege cada orden: la red que se veía, la
cantidad tecleada, el estado desconocido sin adivinar y que todo quede en el registro."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.api import operar_real
from invest_ll.exchanges.falso import ConectorFalso, mercado_falso
from invest_ll.live.ledger import ExecutionLedger

if TYPE_CHECKING:  # pragma: no cover
    from .api_apoyo import Api

D = Decimal


@pytest.fixture
def falso(monkeypatch: pytest.MonkeyPatch) -> ConectorFalso:
    """Hyperliquid activo en su red de pruebas, con un mercado de contado de SOL y otro de PURR."""
    c = ConectorFalso(
        "hyperliquid",
        "pruebas",
        saldo_inicial={"USDC": D(1000)},
        mercados_=(
            mercado_falso("SOL", "USDC", paso_cantidad="0.01"),
            mercado_falso("PURR", "USDC"),
        ),
    )
    c.poner_precio("SOL/USDC", D(100))

    def red_activa(_f: object) -> str:
        return "pruebas"

    def conector(_exchange: str, _red: str) -> ConectorFalso:
        return c

    monkeypatch.setattr(operar_real, "_red_activa", red_activa)
    monkeypatch.setattr(operar_real, "_conector", conector)
    return c


def orden(**cambios: Any) -> dict[str, Any]:
    return {
        "coin": "SOL",
        "lado": "compra",
        "tipo": "mercado",
        "cantidad": "0.5",
        "red": "pruebas",
        "escrito": "0,5",
        **cambios,
    }


def test_sin_conectar_lo_dice_sin_error(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    def sin_red(_f: object) -> None:
        return None

    def que_falta(_f: object) -> list[str]:
        return ["Hyperliquid no está conectado: actívalo en Conexiones."]

    monkeypatch.setattr(operar_real, "_red_activa", sin_red)
    monkeypatch.setattr(operar_real, "_que_falta", que_falta)
    r = cliente.get("/api/operar/hyperliquid", params={"coin": "SOL"})
    assert r.status_code == 200
    datos = r.json()
    assert (datos["conectado"], datos["red"]) == (False, None)
    assert datos["que_falta"] == ["Hyperliquid no está conectado: actívalo en Conexiones."]
    assert cliente.post("/api/operar/hyperliquid/ordenes", json=orden()).status_code == 409


def test_estado_con_su_mercado_y_su_saldo(cliente: Api, falso: ConectorFalso) -> None:
    datos = cliente.get("/api/operar/hyperliquid", params={"coin": "SOL"}).json()
    assert (datos["conectado"], datos["red"]) == (True, "pruebas")
    assert datos["mercado"]["par"] == "SOL/USDC"
    assert datos["saldo"] == [{"moneda": "USDC", "cantidad": "1000"}]
    sin = cliente.get("/api/operar/hyperliquid", params={"coin": "DOGE"}).json()
    assert sin["mercado"] is None
    assert "no tiene mercado de contado de DOGE" in sin["aviso"]


def test_una_compra_a_mercado_se_ejecuta_y_se_anota(cliente: Api, falso: ConectorFalso) -> None:
    r = cliente.post("/api/operar/hyperliquid/ordenes", json=orden())
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["estado"] == "ejecutada"
    assert datos["ejecutada"] == "0.5"
    assert datos["texto"].startswith("Compraste 0,5 SOL a 100")
    assert "(red de pruebas)" in datos["texto"]
    assert datos["anotada"] is True
    [entrada] = ExecutionLedger().entries()
    assert (entrada.exchange, entrada.mode_name) == ("hyperliquid", "pruebas")
    assert len(falso.creadas) == 1
    assert falso.creadas[0].id_cliente == datos["id_cliente"]


@pytest.mark.parametrize("escrito", ["0,4", "", "medio", "0.55"])
def test_si_lo_tecleado_no_es_la_cantidad_no_sale_nada(
    cliente: Api, falso: ConectorFalso, escrito: str
) -> None:
    r = cliente.post("/api/operar/hyperliquid/ordenes", json=orden(escrito=escrito))
    assert r.status_code == 422
    assert "no coincide con la cantidad (0,5): no se ha enviado nada" in r.json()["detail"]
    assert falso.creadas == []


@pytest.mark.parametrize("escrito", ["0,5", "0.5", "0,50", " 0,5 "])
def test_lo_tecleado_vale_en_castellano_o_no(
    cliente: Api, falso: ConectorFalso, escrito: str
) -> None:
    assert (
        cliente.post("/api/operar/hyperliquid/ordenes", json=orden(escrito=escrito)).status_code
        == 200
    )


def test_si_la_red_no_es_la_que_se_veia_no_sale_nada(cliente: Api, falso: ConectorFalso) -> None:
    r = cliente.post("/api/operar/hyperliquid/ordenes", json=orden(red="real"))
    assert r.status_code == 409
    assert "está ahora en la red de pruebas: no se ha enviado nada" in r.json()["detail"]
    assert falso.creadas == []


def test_si_se_corta_a_medias_no_se_adivina(cliente: Api, falso: ConectorFalso) -> None:
    falso.cortar_siguiente(ejecutada=True)
    datos = cliente.post("/api/operar/hyperliquid/ordenes", json=orden()).json()
    assert datos["estado"] == "desconocido"
    assert "no se sabe si se ejecutó" in datos["texto"]
    assert datos["anotada"] is False


def test_si_el_exchange_la_rechaza_lo_dice(cliente: Api, falso: ConectorFalso) -> None:
    falso.rechazar_siguiente("Saldo insuficiente.")
    r = cliente.post("/api/operar/hyperliquid/ordenes", json=orden())
    assert r.status_code == 422
    assert r.json()["detail"] == "Hyperliquid no la aceptó: Saldo insuficiente."


def test_limite_abierta_y_cancelada(cliente: Api, falso: ConectorFalso) -> None:
    sin_precio = cliente.post("/api/operar/hyperliquid/ordenes", json=orden(tipo="limite"))
    assert sin_precio.status_code == 422
    puesta = cliente.post(
        "/api/operar/hyperliquid/ordenes", json=orden(tipo="limite", precio="90")
    ).json()
    assert puesta["estado"] == "abierta"
    assert puesta["anotada"] is False  # abierta: se anota cuando se resuelva
    assert "Sigue abierta" in puesta["texto"]
    abiertas = cliente.get("/api/operar/hyperliquid", params={"coin": "SOL"}).json()[
        "ordenes_abiertas"
    ]
    assert [o["id_cliente"] for o in abiertas] == [puesta["id_cliente"]]
    r = cliente.delete(f"/api/operar/hyperliquid/ordenes/{puesta['id_cliente']}?coin=SOL")
    assert r.status_code == 200
    assert r.json()["estado"] == "cancelada"
    assert cliente.delete("/api/operar/hyperliquid/ordenes/no-existe?coin=SOL").status_code == 404


def test_un_exchange_que_no_existe(cliente: Api) -> None:
    assert cliente.get("/api/operar/kucoin", params={"coin": "SOL"}).status_code == 404


def test_leer_tecleado() -> None:
    assert operar_real.leer_tecleado("1.234,5") == D("1234.5")
    assert operar_real.leer_tecleado("0.095") == D("0.095")
    assert operar_real.leer_tecleado("nan") is None
