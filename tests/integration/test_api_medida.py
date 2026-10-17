"""Las rutas de las estrategias a medida (`/api/medida`) con el TestClient: el contrato v4 servido
de verdad, con un exchange falso para probar sobre el pasado y un CLI de claude falso para diseñar
(ni red ni cuota)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.api import medida
from invest_ll.estrategias_custom.biblioteca import Biblioteca
from invest_ll.estrategias_custom.disenar import ClaudeNoDisponibleError, Disenador
from invest_ll.estrategias_custom.formato import EJEMPLOS

from ..unit.medida_apoyo import CRUCE, ConectorFalso, con, onda, serie
from ..unit.test_medida_disenar import RunnerFalso, salida_cli

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from .api_apoyo import Api

PRUEBA = {"exchange": "falso", "desde": "2025-02-01T00:00:00Z", "hasta": "2026-01-01T00:00:00Z"}


@pytest.fixture
def exchange(monkeypatch: pytest.MonkeyPatch) -> ConectorFalso:
    conector = ConectorFalso()
    conector.poner("BTC/USDT", serie("BTC", onda(400, periodo=30)))

    def publico(_exchange: str) -> ConectorFalso:
        return conector

    monkeypatch.setattr(medida, "conector_publico", publico)
    return conector


def guardar(cliente: Api, definicion: dict[str, Any] = CRUCE, **mas: Any) -> dict[str, Any]:
    r = cliente.post("/api/medida", json={"definicion": definicion, **mas})
    assert r.status_code == 201, r.text
    return r.json()


class TestBiblioteca:
    def test_vacia(self, cliente: Api) -> None:
        r = cliente.get("/api/medida")
        assert r.status_code == 200
        assert r.json() == {"estrategias": []}

    def test_esquema_con_ejemplos(self, cliente: Api) -> None:
        datos = cliente.get("/api/medida/esquema").json()
        assert datos["ejemplos"] == EJEMPLOS
        assert "$defs" in datos["esquema"]
        assert (
            "no es código" in datos["explicacion"].lower() or "No es código" in datos["explicacion"]
        )

    def test_guardar_y_ver_su_ficha(self, cliente: Api) -> None:
        f = guardar(cliente, nota="la primera")
        assert f["estado"] == "borrador"
        assert f["autor"] == "marcos"
        assert f["version"] == 1
        assert (
            f["reglas_en_llano"][1]
            == "Compra cuando la media de 3 velas cruza por encima de la de 5 velas."
        )
        assert f["versiones"][0]["nota"] == "la primera"
        assert f["bots"] == []
        assert f["ultima_prueba"] is None
        assert cliente.get(f"/api/medida/{f['id']}").json() == f
        assert [e["id"] for e in cliente.get("/api/medida").json()["estrategias"]] == [f["id"]]

    def test_una_version_nueva(self, cliente: Api) -> None:
        f = guardar(cliente)
        f2 = guardar(
            cliente, con(CRUCE, intervalo="4h"), id=f["id"], autor="claude", nota="4 horas"
        )
        assert f2["id"] == f["id"]
        assert f2["version"] == 2
        assert f2["autor"] == "claude"
        assert [v["version"] for v in f2["versiones"]] == [1, 2]

    def test_una_que_no_vale_es_un_422_en_llano(self, cliente: Api) -> None:
        r = cliente.post(
            "/api/medida", json={"definicion": con(CRUCE, entrar={">": ["eval('1')", 1]})}
        )
        assert r.status_code == 422
        assert "no admiten expresiones ni código" in r.json()["detail"]

    def test_version_de_una_que_no_existe_es_un_404(self, cliente: Api) -> None:
        r = cliente.post("/api/medida", json={"definicion": CRUCE, "id": "no-existe-000000"})
        assert r.status_code == 404

    def test_detalle_de_una_que_no_existe(self, cliente: Api) -> None:
        assert cliente.get("/api/medida/no-existe-000000").status_code == 404
        assert cliente.get("/api/medida/..%2F..%2Fbots").status_code == 404

    def test_borrar(self, cliente: Api) -> None:
        f = guardar(cliente)
        assert cliente.delete(f"/api/medida/{f['id']}").status_code == 204
        assert cliente.get(f"/api/medida/{f['id']}").status_code == 404
        assert cliente.delete(f"/api/medida/{f['id']}").status_code == 404

    def test_no_se_borra_si_un_bot_la_usa(self, cliente: Api) -> None:
        f = guardar(cliente)
        carpeta = Path("bots") / "cruce-aaaaaa"
        carpeta.mkdir(parents=True)
        definicion = {"id": "cruce-aaaaaa", "plantilla": "medida", "estrategia": f["id"]}
        (carpeta / "definicion.json").write_text(json.dumps(definicion), encoding="utf-8")
        assert cliente.get(f"/api/medida/{f['id']}").json()["bots"] == ["cruce-aaaaaa"]
        r = cliente.delete(f"/api/medida/{f['id']}")
        assert r.status_code == 409
        assert "cruce-aaaaaa" in r.json()["detail"]


class TestProbar:
    def test_prueba_sobre_el_pasado(self, cliente: Api, exchange: ConectorFalso) -> None:
        f = guardar(cliente)
        r = cliente.post(f"/api/medida/{f['id']}/probar", json=PRUEBA)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["exchange"] == "falso"
        assert p["monedas"] == ["BTC"]
        assert p["operaciones"] > 0
        assert p["versiones_probadas"] == 1
        assert p["aviso_sobreajuste"] is None
        assert len(p["curva"]) <= 200
        assert p["lista_operaciones"][0]["nombre"] == "Bitcoin"
        assert any("no hay libro de órdenes" in a for a in p["avisos"])
        ficha = cliente.get(f"/api/medida/{f['id']}").json()
        assert ficha["estado"] == "probada"
        assert ficha["ultima_prueba"] == p
        assert ficha["pruebas"] == [p]
        assert exchange.pedidas

    def test_a_la_tercera_version_avisa_del_sobreajuste(
        self, cliente: Api, exchange: ConectorFalso
    ) -> None:
        f = guardar(cliente)
        avisos: list[str | None] = []
        for corta in (3, 2, 4):
            indicadores = {
                "corta": {"tipo": "sma", "periodo": corta},
                "larga": {"tipo": "sma", "periodo": 5},
            }
            guardar(cliente, con(CRUCE, indicadores=indicadores), id=f["id"])
            avisos.append(
                cliente.post(f"/api/medida/{f['id']}/probar", json=PRUEBA).json()[
                    "aviso_sobreajuste"
                ]
            )
        assert avisos[:2] == [None, None]
        assert avisos[2] is not None and "se parece a hacer trampa" in avisos[2]

    def test_errores_del_exchange_en_llano(self, cliente: Api, exchange: ConectorFalso) -> None:
        f = guardar(cliente, con(CRUCE, monedas=["DOGE"]))
        r = cliente.post(f"/api/medida/{f['id']}/probar", json=PRUEBA)
        assert r.status_code == 422
        assert "no tiene par de contado de DOGE" in r.json()["detail"]

    def test_probar_una_que_no_existe(self, cliente: Api, exchange: ConectorFalso) -> None:
        assert cliente.post("/api/medida/no-existe-000000/probar", json=PRUEBA).status_code == 404


class TestDisenar:
    @pytest.fixture
    def runner(self, monkeypatch: pytest.MonkeyPatch) -> RunnerFalso:
        runner = RunnerFalso(salida_cli("La he guardado.", ["validar", "guardar"]))

        def disenador(b: Biblioteca) -> Disenador:
            runner.efecto = lambda: b.guardar(CRUCE, autor="claude")
            return Disenador(b, runner=runner, reloj=lambda: datetime(2026, 10, 17, tzinfo=UTC))

        monkeypatch.setattr(medida, "nuevo_disenador", disenador)
        return runner

    def test_un_turno_y_la_conversacion_guardada(self, cliente: Api, runner: RunnerFalso) -> None:
        r = cliente.post("/api/medida/disenar", json={"mensaje": "Cruce de medias en BTC"})
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["respuesta"] == "La he guardado."
        assert t["herramientas"] == ["validar", "guardar"]
        assert t["estrategia"] is not None
        assert cliente.get(f"/api/medida/{t['estrategia']}").json()["autor"] == "claude"
        assert [m["autor"] for m in t["historial"]] == ["marcos", "claude"]
        assert cliente.get(f"/api/medida/disenar/{t['sesion']}").json() == t
        sigue = cliente.post("/api/medida/disenar", json={"mensaje": "Otra", "sesion": t["sesion"]})
        assert len(sigue.json()["historial"]) == 4
        assert len(runner.llamadas) == 2

    def test_sesiones_que_no_existen(self, cliente: Api, runner: RunnerFalso) -> None:
        assert cliente.get("/api/medida/disenar/0123456789abcdef").status_code == 404
        r = cliente.post("/api/medida/disenar", json={"mensaje": "x", "sesion": "0123456789abcdef"})
        assert r.status_code == 404
        assert runner.llamadas == []

    def test_sin_claude_es_un_422_en_llano(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def sin_claude(_args: Sequence[str], _entrada: str, _cwd: Path) -> str:
            raise ClaudeNoDisponibleError("No se encuentra el programa «claude» (Claude Code).")

        def disenador(b: Biblioteca) -> Disenador:
            return Disenador(b, runner=sin_claude)

        monkeypatch.setattr(medida, "nuevo_disenador", disenador)
        r = cliente.post("/api/medida/disenar", json={"mensaje": "Hola"})
        assert r.status_code == 422
        assert "«claude»" in r.json()["detail"]
