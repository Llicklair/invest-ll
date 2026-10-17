"""La API del panel: pestaña Vigilar (alertas, triggers de retirada y pausa).

Invariantes: las alertas solo saltan por riesgo y, sin ninguna, se dice qué NO se ha mirado en vez
de "todo bien"; un trigger que salta propone la venta como texto y no envía nada; desarmar lo
inexistente y retirar una pausa que no existe son 404, no éxitos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from invest_ll.alerts.engine import NADA_QUE_CONTAR

from .api_apoyo import Api, guardar, subida

D = Decimal


def _armar(cliente: Api, simbolo: str = "GLD", regla: str = "loss-from-entry") -> str:
    r = cliente.post("/api/triggers", json={"simbolo": simbolo, "regla": regla, "umbral_pct": 15})
    assert r.status_code == 201, r.text
    return r.json()["trigger_id"]


class TestAlertas:
    def test_sin_nada_que_contar_no_dice_que_todo_va_bien(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/vigilar/alertas").json()
        assert cuerpo == {"alertas": [], "nada_que_contar": NADA_QUE_CONTAR}
        assert "no significa que todo vaya bien" in cuerpo["nada_que_contar"]

    def test_salta_por_caida_nunca_por_subida(self, cliente: Api) -> None:
        guardar("BTC/USDT", [*subida(50, desde=100, paso=2), 150.0], proveedor="ccxt-binance")
        guardar("ETH/USDT", subida(51, desde=100, paso=5), proveedor="ccxt-binance")

        cuerpo = cliente.get("/api/vigilar/alertas", params={"caida_pct": 20}).json()

        simbolos = {a["symbol"] for a in cuerpo["alertas"]}
        assert simbolos == {"BTC/USDT"}, "ETH solo sube: una alerta de subida no informa de nada"
        assert cuerpo["nada_que_contar"] is None

    def test_los_datos_viejos_piden_revision(self, cliente: Api) -> None:
        guardar("GLD", subida(30), hasta=date(2026, 1, 30))
        (alerta,) = [
            a
            for a in cliente.get("/api/vigilar/alertas").json()["alertas"]
            if a["nivel"] == "revisar"
        ]
        assert "sin actualizarse" in alerta["mensaje"]

    def test_umbrales_fuera_de_rango_los_rechaza_el_contrato(self, cliente: Api) -> None:
        assert cliente.get("/api/vigilar/alertas", params={"caida_pct": 0}).status_code == 422
        assert cliente.get("/api/vigilar/alertas", params={"dias": 0}).status_code == 422


class TestTriggers:
    def test_armar_listar_y_desarmar(self, cliente: Api) -> None:
        vacio = cliente.get("/api/triggers").json()
        assert vacio["triggers"] == []
        assert vacio["reglas"] == ["loss-from-entry", "drop-from-peak"]

        r = cliente.post(
            "/api/triggers", json={"simbolo": " gld ", "regla": "drop-from-peak", "umbral_pct": 20}
        )
        assert r.status_code == 201
        armado = r.json()
        assert (armado["symbol"], armado["nombre"]) == ("GLD", "Oro")
        assert armado["umbral"] == "0.2", "el umbral es dinero de riesgo: viaja como texto"
        assert "proponer la venta" in armado["descripcion"]

        assert [t["trigger_id"] for t in cliente.get("/api/triggers").json()["triggers"]] == [
            armado["trigger_id"]
        ]
        assert cliente.delete(f"/api/triggers/{armado['trigger_id']}").status_code == 204
        assert cliente.get("/api/triggers").json()["triggers"] == []

    def test_desarmar_lo_inexistente_es_404(self, cliente: Api) -> None:
        r = cliente.delete("/api/triggers/trg-99")
        assert r.status_code == 404
        assert "trg-99" in r.json()["detail"]

    def test_desarmar_dos_veces_es_404_la_segunda(self, cliente: Api) -> None:
        trigger_id = _armar(cliente)
        assert cliente.delete(f"/api/triggers/{trigger_id}").status_code == 204
        assert cliente.delete(f"/api/triggers/{trigger_id}").status_code == 404

    def test_una_regla_desconocida_es_422(self, cliente: Api) -> None:
        r = cliente.post(
            "/api/triggers", json={"simbolo": "GLD", "regla": "trailing", "umbral_pct": 15}
        )
        assert r.status_code == 422


class TestComprobarTriggers:
    def test_propone_la_venta_como_texto_con_la_fecha_del_precio(self, cliente: Api) -> None:
        guardar("GLD", [100.0, 95.0, 80.0], hasta=date(2026, 9, 30))  # -20% desde la entrada
        compra = {
            "tipo": "compra",
            "simbolo": "GLD",
            "fecha": "2026-09-01",
            "cantidad": "10",
            "precio": "100",
        }
        assert cliente.post("/api/cartera/movimientos", json=compra).status_code == 201
        trigger_id = _armar(cliente)
        sin_posicion = _armar(cliente, simbolo="TLT")

        cuerpo = cliente.get("/api/triggers/comprobar").json()

        (disparo,) = cuerpo["disparados"]
        assert disparo["trigger_id"] == trigger_id
        assert disparo["nombre"] == "Oro"
        assert D(disparo["medido"]) == D("-0.2")
        assert disparo["cantidad_propuesta"] == "10"
        assert disparo["precio_fecha"] == "2026-09-30"
        assert disparo["comando"] == (
            "uv run invest-ll-execute --symbol GLD --side sell --quantity 10"
        )
        assert cuerpo["sin_evaluar"] == [
            f"{sin_posicion}: no hay posicion abierta de TLT en el ledger"
        ]
        assert cuerpo["armados"] == 2
        assert not Path("ledger/orders.jsonl").exists(), "un disparo no envia nada"

    def test_sin_triggers_no_salta_nada(self, cliente: Api) -> None:
        assert cliente.get("/api/triggers/comprobar").json() == {
            "disparados": [],
            "sin_evaluar": [],
            "armados": 0,
        }


class TestPausa:
    def test_pausar_y_reanudar(self, cliente: Api) -> None:
        assert cliente.post("/api/pausa", json={"motivo": "vacaciones"}).status_code == 204
        assert "vacaciones" in cliente.get("/api/triggers").json()["pausa"]
        assert cliente.delete("/api/pausa").status_code == 204
        assert cliente.get("/api/triggers").json()["pausa"] is None

    def test_una_pausa_sin_motivo_es_422(self, cliente: Api) -> None:
        r = cliente.post("/api/pausa", json={"motivo": "   "})
        assert r.status_code == 422
        assert "motivo" in r.json()["detail"]

    def test_reanudar_sin_pausa_es_404(self, cliente: Api) -> None:
        assert cliente.delete("/api/pausa").status_code == 404
