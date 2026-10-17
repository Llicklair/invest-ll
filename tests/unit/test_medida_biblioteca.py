"""La biblioteca de estrategias a medida (`medida/`): versiones con su huella, autor, estado,
pruebas guardadas y escritura atómica."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.estrategias_custom import biblioteca as modulo
from invest_ll.estrategias_custom.biblioteca import (
    MAX_PRUEBAS,
    Biblioteca,
    EstrategiaNoEncontradaError,
    bots_que_usan,
    marcar_estado,
)
from invest_ll.estrategias_custom.formato import EstrategiaInvalidaError, validar
from invest_ll.estrategias_custom.prueba import simular

from .medida_apoyo import CRUCE, INICIO, con, onda, serie

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.estrategias_custom.prueba import Resultado

OTRA = con(CRUCE, riesgo={"stop_perdida": 0.1})


def resultado(definicion: object = CRUCE) -> Resultado:
    velas = {"BTC": serie("BTC", onda(120, periodo=30))}
    return simular(
        validar(definicion),
        velas,
        exchange="falso",
        capital=Decimal(1000),
        desde=INICIO + timedelta(days=10),
        hasta=INICIO + timedelta(days=120),
    )


class TestGuardar:
    def test_nueva_es_un_borrador_con_su_version_y_su_autor(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude", nota="primera")
        assert f.id.startswith("cruce-de-medias-")
        assert f.estado == "borrador"
        assert f.autor == "claude"
        assert [(v.version, v.nota) for v in f.versiones] == [(1, "primera")]
        assert b.ficha(f.id) == f
        assert b.ids() == [f.id]

    def test_guarda_la_definicion_completa_y_validada(self, tmp_path: Path) -> None:
        f = Biblioteca(tmp_path).guardar(con(CRUCE, monedas=["btc"]), autor="marcos")
        assert f.ultima.definicion["monedas"] == ["BTC"]
        assert f.ultima.definicion["tamano"] == {
            "fraccion": 1.0,
            "reparto": "igual",
            "maximo_por_moneda": 1.0,
            "periodo_volatilidad": 20,
        }

    def test_la_misma_otra_vez_no_crea_version(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        assert b.guardar(CRUCE, autor="claude", estrategia_id=f.id) == f

    def test_una_version_nueva_vuelve_a_borrador(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.registrar_prueba(f.id, resultado())
        assert b.ficha(f.id).estado == "probada"
        f2 = b.guardar(OTRA, autor="marcos", nota="con stop", estrategia_id=f.id)
        assert [v.version for v in f2.versiones] == [1, 2]
        assert f2.estado == "borrador"
        assert f2.autor == "marcos"
        assert f2.ultima.huella != f2.versiones[0].huella

    def test_cambiar_solo_el_nombre_no_cambia_el_estado(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.registrar_prueba(f.id, resultado())
        f2 = b.guardar(con(CRUCE, nombre="Mejor nombre"), autor="claude", estrategia_id=f.id)
        assert f2.estado == "probada"
        assert f2.ultima.version == 2
        assert f2.ultima.huella == f2.versiones[0].huella

    def test_volver_a_una_version_ya_probada(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.registrar_prueba(f.id, resultado())
        b.guardar(OTRA, autor="claude", estrategia_id=f.id)
        vuelta = b.guardar(
            con(CRUCE, nombre="Otra vez la primera"), autor="claude", estrategia_id=f.id
        )
        assert vuelta.estado == "probada"

    def test_una_invalida_no_se_guarda(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        with pytest.raises(EstrategiaInvalidaError):
            b.guardar(con(CRUCE, intervalo="1m"), autor="claude")
        assert b.ids() == []

    def test_version_de_una_que_no_existe(self, tmp_path: Path) -> None:
        with pytest.raises(EstrategiaNoEncontradaError):
            Biblioteca(tmp_path).guardar(CRUCE, autor="claude", estrategia_id="no-existe-123456")

    def test_ids_que_saldrian_de_la_carpeta(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        for malo in ("../fuera", "..", "C:\\Windows", "a/b", ""):
            with pytest.raises(EstrategiaNoEncontradaError):
                b.ficha(malo)
            assert not b.existe(malo)

    def test_escritura_atomica_sin_restos(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.registrar_prueba(f.id, resultado())
        restos = [p for p in tmp_path.rglob("*") if p.name.endswith(".tmp")]
        assert restos == []
        json.loads((b.carpeta(f.id) / "ficha.json").read_text(encoding="utf-8"))

    def test_una_ficha_rota_no_impide_ver_las_demas(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        buena = b.guardar(CRUCE, autor="claude")
        rota = b.guardar(OTRA, autor="claude")
        (b.carpeta(rota.id) / "ficha.json").write_text("{ roto", encoding="utf-8")
        assert [f.id for f in b.fichas()] == [buena.id]


class TestPruebasYEstado:
    def test_guarda_las_pruebas_la_mas_reciente_primero(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        primera = b.registrar_prueba(f.id, resultado())
        b.guardar(OTRA, autor="claude", estrategia_id=f.id)
        segunda = b.registrar_prueba(f.id, resultado(OTRA))
        assert b.pruebas(f.id) == [segunda, primera]
        assert b.ultima_prueba(f.id) == segunda

    def test_guarda_como_mucho_las_ultimas(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        r = resultado()
        for _ in range(MAX_PRUEBAS + 3):
            b.registrar_prueba(f.id, r)
        assert len(b.pruebas(f.id)) == MAX_PRUEBAS

    def test_probar_una_version_vieja_no_marca_probada_la_nueva(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.guardar(OTRA, autor="claude", estrategia_id=f.id)
        r = b.registrar_prueba(f.id, resultado(CRUCE))
        assert r.version == 1
        assert b.ficha(f.id).estado == "borrador"

    def test_los_bots_marcan_ficticio_y_real_y_solo_sube(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        marcar_estado(f.id, "ficticio", tmp_path)
        assert b.ficha(f.id).estado == "ficticio"
        marcar_estado(f.id, "real", tmp_path)
        assert b.ficha(f.id).estado == "real"
        marcar_estado(f.id, "ficticio", tmp_path)
        assert b.ficha(f.id).estado == "real"

    def test_la_definicion_para_el_motor(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.guardar(OTRA, autor="claude", estrategia_id=f.id)
        assert modulo.definicion(f.id, raiz=tmp_path)["riesgo"]["stop_perdida"] == 0.1
        assert modulo.definicion(f.id, 1, raiz=tmp_path)["riesgo"]["stop_perdida"] is None
        with pytest.raises(EstrategiaNoEncontradaError):
            modulo.definicion(f.id, 7, raiz=tmp_path)

    def test_borrar(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        f = b.guardar(CRUCE, autor="claude")
        b.registrar_prueba(f.id, resultado())
        b.borrar(f.id)
        assert not b.existe(f.id)
        with pytest.raises(EstrategiaNoEncontradaError):
            b.borrar(f.id)


def test_los_bots_que_la_usan(tmp_path: Path) -> None:
    bots = tmp_path / "bots"
    definiciones: dict[str, dict[str, Any]] = {
        "uno-aaaaaa": {"id": "uno-aaaaaa", "plantilla": "medida", "estrategia": "mia-123456"},
        "dos-bbbbbb": {
            "id": "dos-bbbbbb",
            "plantilla": "medida",
            "parametros": {"estrategia": "mia-123456"},
        },
        "tres-cccccc": {"id": "tres-cccccc", "plantilla": "tendencia", "parametros": {}},
    }
    for bot_id, datos in definiciones.items():
        (bots / bot_id).mkdir(parents=True)
        (bots / bot_id / "definicion.json").write_text(json.dumps(datos), encoding="utf-8")
    (bots / "roto").mkdir()
    (bots / "roto" / "definicion.json").write_text("{", encoding="utf-8")
    assert bots_que_usan("mia-123456", bots) == ["dos-bbbbbb", "uno-aaaaaa"]
    assert bots_que_usan("otra-000000", bots) == []
    assert bots_que_usan("mia-123456", tmp_path / "no-hay") == []
