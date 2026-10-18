"""Las rutas de los bots de pruebas y reales con el TestClient (docs/panel-v4-real.md §3), con el
motor puesto sobre exchanges falsos (`ConectorFalso`): nada sale a un exchange de verdad.

Lo que se vigila es lo que protege el dinero: la activación tecleada exacta, «SIN PRUEBA EN
FICTICIO», subir límites pide la activación y subir el límite diario pide «DINERO REAL», y «Parar
todo lo real» funciona sin confirmar nada.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.bots import motor
from invest_ll.bots.motor import Motor
from invest_ll.exchanges import registro
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.falso import ConectorFalso, con_velas, mercado_falso

from ..unit.bots_apoyo import INICIO, Mercado, onda, serie

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from invest_ll.exchanges.conector import Conector, OrdenExchange, Red

    from .api_apoyo import Api

D = Decimal
LIMITES: dict[str, Any] = {
    "capital_max": "500",
    "orden_max": "100",
    "perdida_max_pct": 0.2,
    "vender_al_parar": True,
    "operaciones_max_dia": 10,
}
REJILLA: dict[str, Any] = {
    "plantilla": "rejilla",
    "nombre": "Rejilla BTC",
    "monedas": ["BTC"],
    "capital": "300",
    "parametros": {"precio_bajo": "90", "precio_alto": "110", "escalones": "4"},
}


def sin_anotar(_orden: OrdenExchange, _exchange: str, _red: Red, _bot: str) -> None:
    """El registro de órdenes no se toca en estas pruebas."""


@pytest.fixture
def mercado(cliente: Api) -> Iterator[Mercado]:
    """El motor con Hyperliquid falso y Binance falso en pruebas y en real, cada uno con 1000 USDT."""
    m = Mercado()
    m.precio("BTC", 100)
    falsos: dict[tuple[str, str], ConectorFalso] = {}
    for red in ("pruebas", "real"):
        f = ConectorFalso(exchange_="binance", red_=red, saldo_inicial={"USDT": D(1000)})
        f.poner_precio("BTC/USDT", D(100))
        falsos[("binance", red)] = f

    def conector(exchange: str, red: Red) -> Conector:
        f = falsos.get((exchange, red))
        if f is None:
            raise ExchangeError(f"{exchange} no está activo en {red}.")
        return f

    motor.usar(
        Motor(
            m.fuente,
            Path("bots"),
            reloj=m.reloj,
            zona=UTC,
            conector_de=conector,
            anotar_orden=sin_anotar,
            globales=Path("config") / "bots_real.json",
        )
    )
    yield m
    motor.usar(None)


def desplegar(cliente: Api, **cambios: Any) -> dict[str, Any]:
    r = cliente.post("/api/bots", json={**REJILLA, **cambios})
    assert r.status_code == 201, r.text
    return r.json()


def de_pruebas(cliente: Api) -> dict[str, Any]:
    return desplegar(cliente, modo="pruebas", exchange="binance", limites=LIMITES)


def activar(cliente: Api, bot: dict[str, Any], **cambios: Any) -> Any:
    cuerpo = {
        "confirmacion": f"ACTIVAR {bot['nombre']}",
        "sin_ficticio": "SIN PRUEBA EN FICTICIO",
        "sin_examen": "SIN EXAMEN",
        **cambios,
    }
    return cliente.post(f"/api/bots/{bot['id']}/activar-real", json=cuerpo)


class TestDesplegar:
    def test_en_pruebas_trae_su_modo_limites_y_consumo(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = de_pruebas(cliente)
        assert (bot["modo"], bot["exchange"]) == ("pruebas", "binance")
        assert bot["limites"]["orden_max"] == "100"
        assert bot["consumo"] == {"gastado": "0.00", "perdida_pct": 0.0, "operaciones_hoy": 0}
        assert bot["pausa"] is None
        lista = cliente.get("/api/bots").json()
        assert [t["modo"] for t in lista["por_modo"]] == ["pruebas"]
        assert lista["capital"] == "0", "los totales de arriba son solo de los ficticios"
        assert "de pruebas o real" in lista["nota"]

    def test_en_real_no_se_crea(self, cliente: Api, mercado: Mercado) -> None:
        r = cliente.post(
            "/api/bots", json={**REJILLA, "modo": "real", "exchange": "binance", "limites": LIMITES}
        )
        assert r.status_code == 422
        assert "no se crea con dinero real" in r.json()["detail"]

    def test_sin_limites_no_se_crea_en_pruebas(self, cliente: Api, mercado: Mercado) -> None:
        r = cliente.post("/api/bots", json={**REJILLA, "modo": "pruebas", "exchange": "binance"})
        assert r.status_code == 422
        assert "límites" in r.json()["detail"]


class TestActivarReal:
    def test_la_confirmacion_tiene_que_ser_exacta(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        for mal in ("activar Rejilla BTC", "ACTIVAR", "ACTIVAR Rejilla BTC ", "ACTIVAR otra"):
            r = activar(cliente, bot, confirmacion=mal)
            assert r.status_code == 422, mal
            assert "ACTIVAR Rejilla BTC" in r.json()["detail"]
        assert cliente.get(f"/api/bots/{bot['id']}").json()["modo"] == "pruebas"

    def test_sin_un_mes_en_ficticio_pide_saberlo(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        r = activar(cliente, bot, sin_ficticio=None)
        assert r.status_code == 422
        assert "SIN PRUEBA EN FICTICIO" in r.json()["detail"]
        assert "0,0 días en ficticio (menos de 30)" in r.json()["detail"]

    def test_con_un_mes_en_ficticio_no_hace_falta(self, cliente: Api, mercado: Mercado) -> None:
        desplegar(cliente, nombre="Rejilla ficticia")
        mercado.reloj.avanzar(timedelta(days=30, minutes=1))
        bot = de_pruebas(cliente)
        assert bot["probado_en_ficticio_dias"] >= 30
        r = activar(cliente, bot, sin_ficticio=None)
        assert r.status_code == 200, r.text

    def test_activado_empieza_de_cero_en_rojo(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        r = activar(cliente, bot)
        assert r.status_code == 200, r.text
        real = r.json()
        assert (real["modo"], real["exchange"], real["capital"]) == ("real", "binance", "500")
        assert real["eventos"][0]["tipo"] == "real"
        lista = cliente.get("/api/bots").json()
        assert lista["real"]["bots_reales"] == 1
        assert [t["modo"] for t in lista["por_modo"]] == ["real"]
        actividad = cliente.get("/api/actividad", params={"bot": bot["id"]}).json()
        assert actividad["movimientos"][0]["modo"] == "real"

    def test_un_ficticio_necesita_exchange_y_limites(self, cliente: Api, mercado: Mercado) -> None:
        bot = desplegar(cliente)
        r = activar(cliente, bot)
        assert r.status_code == 422
        assert "exchange" in r.json()["detail"]
        r = activar(cliente, bot, exchange="binance")
        assert r.status_code == 422
        assert "límites" in r.json()["detail"]
        r = activar(cliente, bot, exchange="binance", limites=LIMITES)
        assert r.status_code == 200, r.text

    def test_sin_el_exchange_activo_en_real_no_se_activa(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = desplegar(cliente)
        r = activar(cliente, bot, exchange="kraken", limites=LIMITES)
        assert r.status_code == 422
        assert "no está activo" in r.json()["detail"]


class TestLimites:
    def test_bajar_siempre_y_subir_en_real_pide_la_activacion(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = activar(cliente, de_pruebas(cliente)).json()
        ruta = f"/api/bots/{bot['id']}/limites"
        r = cliente.put(ruta, json={"limites": {**LIMITES, "orden_max": "50"}})
        assert r.status_code == 200, r.text
        assert r.json()["limites"]["orden_max"] == "50"
        r = cliente.put(ruta, json={"limites": {**LIMITES, "orden_max": "200"}})
        assert r.status_code == 422
        assert "ACTIVAR Rejilla BTC" in r.json()["detail"]
        r = cliente.put(
            ruta,
            json={
                "limites": {**LIMITES, "orden_max": "200"},
                "confirmacion": "ACTIVAR Rejilla BTC",
            },
        )
        assert r.status_code == 200
        assert r.json()["limites"]["orden_max"] == "200"

    def test_en_pruebas_se_suben_sin_confirmar(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        r = cliente.put(
            f"/api/bots/{bot['id']}/limites", json={"limites": {**LIMITES, "orden_max": "300"}}
        )
        assert r.status_code == 200


class TestPararTodo:
    def test_para_lo_real_sin_confirmar_y_se_reanuda_uno_a_uno(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = activar(cliente, de_pruebas(cliente)).json()
        otro = de_pruebas(cliente)
        r = cliente.post("/api/bots-real/parar-todo")
        assert r.status_code == 200
        assert r.json() == {"parados": [bot["id"]], "ordenes_canceladas": 0, "avisos": []}
        estado = cliente.get("/api/bots-real").json()
        assert estado["parado_todo"] is True
        assert estado["parado_desde"] is not None
        assert estado["aviso"].startswith("Todo lo real está parado.")
        assert cliente.get(f"/api/bots/{otro['id']}").json()["estado"] == "en_marcha"

        r = cliente.post(f"/api/bots/{bot['id']}/reanudar")
        assert r.status_code == 409
        assert "Parar todo lo real" in r.json()["detail"]

        r = cliente.post("/api/bots-real/reanudar-todo")
        assert r.status_code == 200
        assert r.json()["parado_todo"] is False
        assert cliente.get(f"/api/bots/{bot['id']}").json()["estado"] == "parado"
        assert cliente.post(f"/api/bots/{bot['id']}/reanudar").status_code == 200


class TestLimiteDiario:
    def test_ponerlo_y_bajarlo_libre_y_subirlo_con_dinero_real(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        ruta = "/api/bots-real/limite-diario"
        r = cliente.put(ruta, json={"limite": "100"})
        assert r.status_code == 200
        assert r.json()["limite_diario"] == "100"
        assert cliente.put(ruta, json={"limite": "50"}).status_code == 200
        r = cliente.put(ruta, json={"limite": "200"})
        assert r.status_code == 422
        assert "DINERO REAL" in r.json()["detail"]
        r = cliente.put(ruta, json={"limite": "200", "confirmacion": "DINERO REAL"})
        assert r.status_code == 200
        assert r.json()["limite_diario"] == "200"


class TestBorrar:
    def test_uno_de_exchange_en_marcha_no_se_borra(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        r = cliente.delete(f"/api/bots/{bot['id']}")
        assert r.status_code == 409
        assert "Páralo antes" in r.json()["detail"]
        cliente.post(f"/api/bots/{bot['id']}/parar")
        assert cliente.delete(f"/api/bots/{bot['id']}").status_code == 204


class TestExamen:
    """Antes del dinero real, su regla sobre seis tramos del último año (bots.examen)."""

    @staticmethod
    def binance_con_un_ano() -> ConectorFalso:
        horas = 400 * 24
        velas = serie(
            "BTC/USDT",
            "1h",
            onda(horas, centro=100, amplitud=15, periodo=240),
            INICIO - timedelta(hours=horas),
        )
        return con_velas(
            ConectorFalso(exchange_="binance", mercados_=(mercado_falso("BTC"),)), velas
        )

    def test_sin_examen_pide_saberlo(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        r = activar(cliente, bot, sin_examen=None)
        assert r.status_code == 422
        assert r.json()["detail"].startswith("No tiene examen sobre el pasado.")
        assert "SIN EXAMEN" in r.json()["detail"]

    def test_examinado_y_aprobado_no_hace_falta_escribirlo(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = de_pruebas(cliente)
        with registro.inyectados({"binance": self.binance_con_un_ano()}):
            r = cliente.post(f"/api/bots/{bot['id']}/examen")
        assert r.status_code == 200, r.text
        examen = r.json()
        assert (examen["exchange"], len(examen["tramos"])) == ("binance", 6)
        assert examen["aprobado"] is True, examen["veredicto"]
        assert examen["vigente"] is True
        assert cliente.get(f"/api/bots/{bot['id']}").json()["examen"] == examen
        assert activar(cliente, bot, sin_examen=None).status_code == 200

    def test_examinar_no_envia_nada(self, cliente: Api, mercado: Mercado) -> None:
        bot = de_pruebas(cliente)
        binance = self.binance_con_un_ano()
        with registro.inyectados({"binance": binance}):
            assert cliente.post(f"/api/bots/{bot['id']}/examen").status_code == 200
        assert binance.creadas == []
