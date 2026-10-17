"""La API del panel: pestaña Simular. Nada de aquí mueve dinero.

Invariantes: la pausa de entradas bloquea la propuesta (409) y su registro; registrar la propuesta
anota compras en el ledger y no envía nada; el informe de un backtest sale en el orden del informe
de texto, con el win rate al final y la comparación contra no hacer nada.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.portfolio.triggers import TriggerStore

from .api_apoyo import COSTES, GLD, TLT, Api, guardar, subida, zigzag

D = Decimal
HASTA = date(2026, 9, 30)


@pytest.fixture
def con_dos_activos(cliente: Api) -> Api:
    guardar("GLD", zigzag(300, desde=200), hasta=HASTA)
    guardar("TLT", subida(300, desde=80, paso=0.2), hasta=HASTA)
    return cliente


def _propuesta() -> dict[str, object]:
    return {"activos": [GLD, TLT], "importe": "500", "frecuencia": "monthly", **COSTES}


def _pausar() -> None:
    TriggerStore().halt(reason="me voy de viaje", at=datetime(2026, 10, 1, tzinfo=UTC))


class TestOpciones:
    def test_frecuencias_estrategias_y_sugeridos_compatibles(self, con_dos_activos: Api) -> None:
        cuerpo = con_dos_activos.get("/api/simular/opciones").json()
        assert cuerpo["frecuencias"] == ["monthly", "quarterly", "weekly"]
        assert cuerpo["estrategias"] == ["cruce-medias", "precio-vs-media", "ruptura-maximos"]
        assert sorted(cuerpo["sugeridos"]) == [GLD, TLT]
        assert cuerpo["pausa"] is None


class TestPropuesta:
    def test_propone_con_precio_fecha_y_comandos(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post("/api/simular/propuesta", json=_propuesta())

        assert r.status_code == 200
        cuerpo = r.json()
        assert "Propuesta de cartera" in cuerpo["texto"]
        compras = {c["symbol"]: c for c in cuerpo["compras"]}
        assert compras["GLD"]["importe"] == "250.00"
        assert compras["GLD"]["fecha"] == "2026-09-30"
        assert isinstance(compras["GLD"]["cantidad"], str)
        assert D(compras["GLD"]["cantidad"]) == (
            D("250.00") / D(compras["GLD"]["precio"])
        ).quantize(D("0.0001"))
        assert any(
            c.startswith("uv run invest-ll-execute --symbol GLD --side buy")
            for c in cuerpo["comandos"]
        )

    def test_la_pausa_bloquea_la_propuesta_con_409(self, con_dos_activos: Api) -> None:
        _pausar()
        r = con_dos_activos.post("/api/simular/propuesta", json=_propuesta())
        assert r.status_code == 409
        assert "me voy de viaje" in r.json()["detail"]
        assert "invest-ll-triggers resume" in r.json()["detail"]

    def test_una_frecuencia_desconocida_es_422(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post(
            "/api/simular/propuesta", json={**_propuesta(), "frecuencia": "diaria"}
        )
        assert r.status_code == 422
        assert "frecuencia desconocida" in r.json()["detail"]

    def test_un_activo_inexistente_es_404(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post(
            "/api/simular/propuesta", json={**_propuesta(), "activos": ["yfinance:NO:DAY_1"]}
        )
        assert r.status_code == 404

    def test_los_costes_son_obligatorios(self, con_dos_activos: Api) -> None:
        sin_costes = {k: v for k, v in _propuesta().items() if k != "comision"}
        assert con_dos_activos.post("/api/simular/propuesta", json=sin_costes).status_code == 422


class TestRegistrarPropuesta:
    def test_anota_las_compras_con_precio_y_avisa_de_las_demas(self, con_dos_activos: Api) -> None:
        compras = [
            {
                "symbol": "GLD",
                "importe": "250",
                "precio": "200",
                "fecha": "2026-09-30",
                "cantidad": "1.25",
            },
            {"symbol": "XYZ", "importe": "250", "precio": None, "fecha": None, "cantidad": None},
        ]

        r = con_dos_activos.post("/api/simular/propuesta/registrar", json={"compras": compras})

        assert r.status_code == 200
        assert r.json()["registradas"] == 1
        assert r.json()["problemas"] == ["XYZ: sin precio descargado, registralo a mano"]
        cartera = con_dos_activos.get("/api/cartera").json()
        assert [p["activo"] for p in cartera["abiertas"]] == ["GLD"]
        assert '"source": "propuesta"' in Path("portfolio/activities.jsonl").read_text(
            encoding="utf-8"
        )
        assert not Path("ledger/orders.jsonl").exists(), "registrar no envia ninguna orden"

    def test_con_pausa_tampoco_se_anota(self, con_dos_activos: Api) -> None:
        _pausar()
        compras = [
            {"symbol": "GLD", "importe": "250", "precio": "200", "fecha": None, "cantidad": "1"}
        ]
        r = con_dos_activos.post("/api/simular/propuesta/registrar", json={"compras": compras})
        assert r.status_code == 409
        assert not Path("portfolio/activities.jsonl").exists()


class TestUnActivo:
    def test_informe_en_el_orden_del_texto(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post(
            "/api/simular/activo",
            json={"activo": GLD, "estrategia": "cruce-medias", "corta": 5, "larga": 20, **COSTES},
        )

        assert r.status_code == 200
        informe = r.json()
        assert isinstance(informe["resultado_neto"], str)
        assert informe["operaciones"] > 0
        assert informe["curva"], "la curva de patrimonio viaja para dibujarla"
        assert informe["comprar_y_mantener"] is not None
        assert informe["metricas"]["columnas"] == ["metrica", "valor"]
        assert informe["metricas"]["filas"][-1][0].startswith("Win rate"), "el win rate, al final"
        assert len(informe["registro"]["filas"]) == informe["operaciones"]

    def test_parametros_imposibles_son_422_con_el_texto_del_dominio(
        self, con_dos_activos: Api
    ) -> None:
        r = con_dos_activos.post(
            "/api/simular/activo",
            json={"activo": GLD, "estrategia": "cruce-medias", "corta": 30, "larga": 10, **COSTES},
        )
        assert r.status_code == 422
        assert r.json()["detail"].startswith("No se pudo evaluar")

    @pytest.mark.parametrize("estrategia", ["precio-vs-media", "ruptura-maximos"])
    def test_las_otras_estrategias(self, con_dos_activos: Api, estrategia: str) -> None:
        r = con_dos_activos.post(
            "/api/simular/activo", json={"activo": TLT, "estrategia": estrategia, **COSTES}
        )
        assert r.status_code == 200


class TestCartera:
    def test_analisis_de_diversificacion(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post("/api/simular/cartera/analisis", json={"activos": [GLD, TLT]})
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["fechas_comunes"] == 300
        assert cuerpo["hasta"] == "2026-09-30"
        assert cuerpo["pares"][0]["par"] == "GLD / TLT"

    def test_un_activo_solo_no_es_una_cartera(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post("/api/simular/cartera/analisis", json={"activos": [GLD]})
        assert r.status_code == 422

    def test_aportaciones(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post(
            "/api/simular/cartera/aportaciones",
            json={"activos": [GLD, TLT], "aportacion": "500", "cada": 21, **COSTES},
        )
        assert r.status_code == 200
        cuerpo = r.json()
        assert D(cuerpo["aportado"]) == D(500) * 15  # 300 sesiones / 21 = 15 aportaciones
        assert cuerpo["texto"].startswith("Aportaciones periodicas - GLD / TLT")
        assert "todo de golpe" in cuerpo["texto"], "la comparacion con el todo de golpe viaja"

    def test_rotacion(self, con_dos_activos: Api) -> None:
        r = con_dos_activos.post(
            "/api/simular/cartera/rotacion",
            json={"activos": [GLD, TLT], "lookback": 20, **COSTES},
        )
        assert r.status_code == 200
        assert r.json()["metricas"]["filas"][-1][0].startswith("Win rate")


class TestLLM:
    def test_sin_decisiones_grabadas_lo_dice(self, cliente: Api) -> None:
        cuerpo = cliente.post("/api/simular/llm", json=COSTES).json()
        assert cuerpo["disponible"] is False
        assert "invest-ll-generate" in cuerpo["motivo"]
        assert cuerpo["advertencia"], "la advertencia de contaminacion viaja siempre"

    def test_sin_los_cuatro_historicos_lo_dice(self, con_dos_activos: Api) -> None:
        Path("decisions/llm-trimestral").mkdir(parents=True)
        cuerpo = con_dos_activos.post("/api/simular/llm", json=COSTES).json()
        assert cuerpo["disponible"] is False
        assert "GLD/TLT/XLE/XLF" in cuerpo["motivo"]
