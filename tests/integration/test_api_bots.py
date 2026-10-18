"""Las rutas de los bots (`/api/bots`) con el TestClient: el contrato v3 servido de verdad.

Con el motor del panel puesto (`motor.usar`) sobre una `FuenteFalsa` y un reloj que avanza a mano,
como lo tendría el panel con `en_vivo=True`; y sin él, que es como las sirven los tests y la
generación del contrato: leyendo y escribiendo `bots/` sin hacer operar a nadie.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.bots import motor
from invest_ll.bots.motor import Motor

from ..unit.bots_apoyo import Mercado

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from .api_apoyo import Api

TENDENCIA: dict[str, Any] = {
    "plantilla": "tendencia",
    "nombre": "Tendencia BTC",
    "monedas": ["BTC"],
    "capital": "1000",
    "parametros": {},
}


@pytest.fixture
def mercado(cliente: Api) -> Iterator[Mercado]:
    """El motor del panel en marcha (sin su bucle: la prueba da las vueltas) sobre `bots/` del
    directorio temporal del test."""
    m = Mercado()
    m.precio("BTC", 67010)
    m.precio("ETH", 2400)
    motor.usar(Motor(m.fuente, Path("bots"), reloj=m.reloj, zona=UTC))
    yield m
    motor.usar(None)


def activo() -> Motor:
    m = motor.activo()
    assert m is not None
    return m


def desplegar(cliente: Api, **cambios: Any) -> dict[str, Any]:
    r = cliente.post("/api/bots", json={**TENDENCIA, **cambios})
    assert r.status_code == 201, r.text
    return r.json()


class TestPlantillas:
    def test_las_cuatro_con_sus_parametros(self, cliente: Api) -> None:
        r = cliente.get("/api/bots/plantillas")
        assert r.status_code == 200
        plantillas = {p["clave"]: p for p in r.json()["plantillas"]}
        assert list(plantillas) == ["btc-freno", "tendencia", "rejilla", "periodica"]
        tendencia = plantillas["tendencia"]
        assert tendencia["evidencia"] == {
            "tipo": "ninguna",
            "texto": "Ninguna: es un experimento. No se ha probado ni sobre el pasado ni en real.",
        }
        assert [p["defecto"] for p in tendencia["parametros"]] == ["20", "50", "1h"]
        assert tendencia["parametros"][2]["opciones"] == ["15m", "30m", "1h", "2h", "4h"]
        assert plantillas["btc-freno"]["evidencia"]["tipo"] == "prueba_real"
        assert plantillas["rejilla"]["riesgo_texto"] == "Movida"


class TestSinMotor:
    def test_sin_bots_la_lista_esta_vacia(self, cliente: Api) -> None:
        r = cliente.get("/api/bots")
        assert r.status_code == 200
        datos = r.json()
        assert datos["bots"] == []
        assert datos["nota"] == "Dinero ficticio. Los bots siguen aunque cierres el panel, mientras el ordenador esté encendido."
        assert datos["ganancia_pct"] is None

    def test_sin_precios_no_se_puede_desplegar_y_lo_dice(self, cliente: Api) -> None:
        r = cliente.post("/api/bots", json=TENDENCIA)
        assert r.status_code == 422
        assert r.json()["detail"].startswith("Hyperliquid no da precio de BTC ahora mismo")

    def test_lee_los_bots_del_disco_aunque_el_motor_no_este(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = desplegar(cliente)
        motor.usar(None)
        r = cliente.get("/api/bots")
        assert r.status_code == 200
        (resumen,) = r.json()["bots"]
        assert resumen["id"] == bot["id"]
        assert resumen["valor"] == "1000.00"
        assert resumen["aviso"].startswith("Sin precios de Hyperliquid")
        assert Path("bots", bot["id"], "definicion.json").is_file()


class TestConElMotor:
    def test_desplegar_lo_pone_en_marcha(self, cliente: Api, mercado: Mercado) -> None:
        bot = desplegar(cliente)
        assert bot["estado"] == "en_marcha"
        assert bot["nombre_plantilla"] == "Tendencia rápida"
        assert bot["capital"] == "1000"
        assert bot["valor"] == "1000.00"
        assert bot["efectivo"] == "1000.00"
        assert bot["parametros"] == {"media_corta": "20", "media_larga": "50", "intervalo": "1h"}
        assert bot["evidencia"]["tipo"] == "ninguna"
        assert bot["riesgo"] == 4
        assert [e["tipo"] for e in bot["eventos"]] == ["arranque"]
        assert bot["eventos"][0]["texto"] == "Desplegado con 1.000,00 USDC ficticios en Bitcoin."
        assert len(bot["curva"]) == 1
        assert bot["operaciones"] == 0
        assert bot["lista_operaciones"] == []
        assert ("BTC", True, ("1h",)) in mercado.fuente.seguidas

    @pytest.mark.parametrize(
        ("cambios", "detalle"),
        [
            ({"plantilla": "magia"}, "No hay ninguna plantilla «magia»"),
            ({"parametros": {"media_corta": "uno"}}, "«Media corta» tiene que ser un número"),
            ({"monedas": ["NOEXISTE"]}, "Hyperliquid no da precio de NOEXISTE"),
            ({"nombre": ""}, "Revisa los datos: «nombre» es demasiado corto"),
            ({"capital": "0"}, "Revisa los datos: «capital» tiene que ser mayor que 0"),
        ],
    )
    def test_lo_que_no_vale_es_un_422_en_llano(
        self, cliente: Api, mercado: Mercado, cambios: dict[str, Any], detalle: str
    ) -> None:
        r = cliente.post("/api/bots", json={**TENDENCIA, **cambios})
        assert r.status_code == 422
        assert r.json()["detail"].startswith(detalle), r.json()["detail"]

    def test_un_bot_que_opera_se_ve_en_la_lista_y_en_su_ficha(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = desplegar(
            cliente,
            plantilla="periodica",
            nombre="Cada día",
            monedas=["BTC", "ETH"],
            parametros={"importe": "200"},
        )
        activo().paso()
        mercado.precio("BTC", 70000)
        mercado.reloj.avanzar(timedelta(minutes=5))
        activo().paso()

        lista = cliente.get("/api/bots").json()
        (resumen,) = lista["bots"]
        assert resumen["operaciones"] == 2
        assert float(resumen["valor"]) > 1000
        assert resumen["ganancia_pct"] > 0
        assert resumen["mantener_pct"] > resumen["ganancia_pct"]
        assert resumen["peor_caida"] <= 0
        assert resumen["ultima_actividad"] is not None
        assert lista["capital"] == "1000"
        assert lista["valor"] == resumen["valor"]

        ficha = cliente.get(f"/api/bots/{bot['id']}").json()
        compras = ficha["lista_operaciones"]
        assert [o["coin"] for o in compras] == ["ETH", "BTC"]
        assert compras[1]["nombre"] == "Bitcoin"
        assert compras[1]["motivo"].startswith("Compré 0,00149")
        assert "toca la compra de cada 24 horas (200,00 USDC repartidos)" in compras[1]["motivo"]
        assert {p["coin"] for p in ficha["posiciones"]} == {"BTC", "ETH"}
        assert float(ficha["efectivo"]) == pytest.approx(800, abs=0.01)
        assert ficha["curva_mantener"]

    def test_parar_reanudar_y_borrar(self, cliente: Api, mercado: Mercado) -> None:
        bot = desplegar(cliente)
        r = cliente.post(f"/api/bots/{bot['id']}/parar")
        assert r.status_code == 200
        assert r.json()["estado"] == "parado"
        assert r.json()["eventos"][0]["tipo"] == "parada"
        r = cliente.post(f"/api/bots/{bot['id']}/reanudar")
        assert r.json()["estado"] == "en_marcha"
        assert cliente.delete(f"/api/bots/{bot['id']}").status_code == 204
        assert cliente.get(f"/api/bots/{bot['id']}").status_code == 404
        assert not Path("bots", bot["id"]).exists()

    @pytest.mark.parametrize(
        ("metodo", "ruta"),
        [
            ("get", "/api/bots/no-existe"),
            ("post", "/api/bots/no-existe/parar"),
            ("post", "/api/bots/no-existe/reanudar"),
            ("delete", "/api/bots/no-existe"),
            ("get", "/api/bots/MAL..id"),
        ],
    )
    def test_lo_que_no_existe_es_un_404_en_llano(
        self, cliente: Api, mercado: Mercado, metodo: str, ruta: str
    ) -> None:
        r = getattr(cliente, metodo)(ruta)
        assert r.status_code == 404
        assert r.json()["detail"].startswith("No hay ningún bot")


REJILLA: dict[str, Any] = {
    "plantilla": "rejilla",
    "nombre": "Rejilla BTC",
    "monedas": ["BTC"],
    "capital": "1000",
    "parametros": {"precio_bajo": "60000", "precio_alto": "70000", "escalones": "4"},
}


class TestEnDirecto:
    """v5 (docs/panel-v5.md §4): el feed de movimientos, las métricas y qué hará después."""

    def operar(self, cliente: Api, mercado: Mercado) -> dict[str, Any]:
        bot = desplegar(cliente, **REJILLA)
        m = activo()
        m.paso()  # a 67.010 compra el escalón de 67.500 a 70.000
        mercado.precio("BTC", 71000)
        mercado.reloj.avanzar(timedelta(seconds=1))
        m.paso()  # a 71.000 lo vende
        return bot

    def test_la_actividad_lleva_cada_movimiento_con_su_resultado(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = self.operar(cliente, mercado)
        r = cliente.get("/api/actividad")
        assert r.status_code == 200
        movimientos = r.json()["movimientos"]
        tipos = [x["tipo"] for x in movimientos]
        assert tipos[0] == "venta"  # el más reciente primero
        assert {"compra", "arranque"} <= set(tipos)
        venta = movimientos[0]
        assert venta["bot_id"] == bot["id"]
        assert venta["bot_nombre"] == "Rejilla BTC"
        assert venta["modo"] == "ficticio"
        assert venta["nombre_moneda"] == "Bitcoin"
        assert Decimal(venta["resultado"]) > 0
        compra = next(x for x in movimientos if x["tipo"] == "compra")
        assert compra["resultado"] is None
        uno = cliente.get("/api/actividad", params={"bot": bot["id"], "limite": 1}).json()
        assert [x["id"] for x in uno["movimientos"]] == [venta["id"]]
        assert cliente.get("/api/actividad", params={"bot": "no-existe"}).status_code == 404

    def test_la_ficha_trae_sus_metricas_y_que_hara_despues(
        self, cliente: Api, mercado: Mercado
    ) -> None:
        bot = self.operar(cliente, mercado)
        d = cliente.get(f"/api/bots/{bot['id']}").json()
        metricas = d["metricas"]
        assert (metricas["compras"], metricas["ventas"], metricas["cerradas"]) == (1, 1, 1)
        assert metricas["aciertos"] == 1.0
        assert Decimal(metricas["realizada"]) > 0
        assert "una venta cerrada" in metricas["aviso"]
        pendientes = d["pendientes"]
        # Lo vendió todo: los cuatro escalones esperan para comprar, el más alto primero.
        assert [p["tipo"] for p in pendientes] == ["compra"] * 4
        assert [p["precio"] for p in pendientes] == ["67500", "65000", "62500", "60000"]
        assert pendientes[0]["distancia"] == pytest.approx(67500 / 71000 - 1)

