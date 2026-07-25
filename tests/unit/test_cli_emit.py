"""El sobre JSON de la CLI.

El test que da sentido al módulo es `test_un_aviso_siempre_viaja_en_los_dos_modos`. Un modo JSON
que entregue los números sin las advertencias sería peor que no tenerlo: un agente leería
"el LLM ganó" sin leer "el modelo conoce lo que pasó después". Todo lo demás de este fichero es
para que ese invariante no se pueda romper por accidente.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from invest_ll.cli.emit import (
    AVISO_CONTAMINACION,
    VERSION_FORMATO,
    Salida,
    add_json_flag,
    como_dict,
    salida_de,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

D = Decimal


def leer(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """El JSON que quedó en stdout, exigiendo que stdout sea SOLO eso."""
    salida = capsys.readouterr().out
    return cast("dict[str, object]", json.loads(salida))


def datos_de(sobre: dict[str, object]) -> dict[str, object]:
    cuerpo = sobre["data"]
    assert isinstance(cuerpo, dict)
    return cast("dict[str, object]", cuerpo)


def avisos_de(sobre: dict[str, object]) -> list[dict[str, str]]:
    avisos = sobre["warnings"]
    assert isinstance(avisos, list)
    return cast("list[dict[str, str]]", avisos)


class TestElSobre:
    def test_lleva_version_comando_y_codigo(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="compare", json_mode=True)
        assert s.cerrar(0) == 0

        sobre = leer(capsys)
        assert sobre["format_version"] == VERSION_FORMATO
        assert sobre["command"] == "compare"
        assert sobre["exit_code"] == 0
        assert sobre["ok"] is True

    def test_un_codigo_distinto_de_cero_no_es_ok(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Un agente decide por `ok`; si mintiera, seguiria adelante tras un fallo."""
        s = Salida(command="compare", json_mode=True)
        assert s.cerrar(3) == 3
        assert leer(capsys)["ok"] is False

    def test_cerrar_devuelve_el_codigo_que_le_dan(self) -> None:
        """El modo JSON no puede cambiar el codigo de salida del proceso."""
        for codigo in (0, 1, 2, 3, 5):
            assert Salida(command="x", json_mode=False).cerrar(codigo) == codigo

    def test_en_modo_texto_no_sale_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="compare", json_mode=False)
        s.dato(resultado=100)
        s.cerrar(0)
        assert capsys.readouterr().out == ""

    def test_el_error_va_dentro_del_sobre(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quien parsea stdout tiene que poder leer el fallo sin mirar stderr."""
        s = Salida(command="compare", json_mode=True)
        assert s.error("no existe el fichero", 2) == 2

        sobre = leer(capsys)
        assert sobre["ok"] is False
        assert sobre["exit_code"] == 2
        assert sobre["error"] == "no existe el fichero"

    def test_en_texto_el_error_va_a_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="compare", json_mode=False)
        s.error("no existe el fichero", 2)

        capturado = capsys.readouterr()
        assert "no existe el fichero" in capturado.err
        assert capturado.out == ""


class TestLosAvisosNoSePierden:
    """La razon de ser del modulo."""

    def test_un_aviso_siempre_viaja_en_los_dos_modos(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """EL test de este fichero.

        El mismo `aviso()` produce texto para una persona Y una entrada en el JSON. No existe
        forma de emitir uno sin el otro porque es una sola llamada.
        """
        texto_del_aviso = "el modelo fue entrenado con datos posteriores al periodo simulado"

        en_texto = Salida(command="compare", json_mode=False)
        en_texto.aviso(AVISO_CONTAMINACION, texto_del_aviso)
        en_texto.cerrar(0)
        assert texto_del_aviso in capsys.readouterr().out

        en_json = Salida(command="compare", json_mode=True)
        en_json.aviso(AVISO_CONTAMINACION, texto_del_aviso)
        en_json.cerrar(0)

        assert avisos_de(leer(capsys)) == [
            {"code": AVISO_CONTAMINACION, "message": texto_del_aviso}
        ]

    def test_mostrar_false_lo_calla_en_texto_pero_no_en_json(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Para avisos ya impresos con formato propio: se registran igual, no se repiten."""
        s = Salida(command="compare", json_mode=False)
        s.aviso(AVISO_CONTAMINACION, "un aviso largo", mostrar=False)
        s.cerrar(0)
        assert capsys.readouterr().out == ""
        assert len(s.avisos) == 1

    def test_el_orden_se_conserva(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="compare", json_mode=True)
        for i in range(3):
            s.aviso(f"c{i}", f"m{i}")
        s.cerrar(0)

        assert [a["code"] for a in avisos_de(leer(capsys))] == ["c0", "c1", "c2"]

    def test_sin_avisos_la_lista_existe_vacia(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Que el campo falte obligaria a quien consuma a distinguir dos casos por nada."""
        Salida(command="compare", json_mode=True).cerrar(0)
        assert leer(capsys)["warnings"] == []


class TestElDineroNoPierdeExactitud:
    def test_los_decimales_salen_como_cadena(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Serializarlos como float perderia centimos justo en la frontera."""
        s = Salida(command="compare", json_mode=True)
        s.dato(resultado=D("19246.37"))
        s.cerrar(0)

        assert datos_de(leer(capsys))["resultado"] == "19246.37"

    def test_un_decimal_largo_sobrevive_entero(self, capsys: pytest.CaptureFixture[str]) -> None:
        exacto = "0.1234567890123456789012345678"
        s = Salida(command="compare", json_mode=True)
        s.dato(fraccion=D(exacto))
        s.cerrar(0)

        datos = datos_de(leer(capsys))
        assert datos["fraccion"] == exacto
        assert D(str(datos["fraccion"])) == D(exacto)

    def test_como_float_se_habria_roto(self) -> None:
        """Comprobacion del propio test: que el caso de arriba no pasa por casualidad."""
        exacto = "0.1234567890123456789012345678"
        assert str(float(D(exacto))) != exacto


class TestTiposQueAparecenDeVerdad:
    def test_fechas_en_iso(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="track", json_mode=True)
        s.dato(emitida=datetime(2026, 7, 25, 12, 30, tzinfo=UTC))
        s.cerrar(0)

        assert datos_de(leer(capsys))["emitida"] == "2026-07-25T12:30:00+00:00"

    def test_rutas_como_texto(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="generate", json_mode=True)
        s.dato(destino=Path("decisions") / "run")
        s.cerrar(0)

        assert "run" in str(datos_de(leer(capsys))["destino"])

    def test_estructuras_anidadas(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="compare", json_mode=True)
        s.dato(estrategias=[{"nombre": "llm", "resultado": D("19246")}])
        s.cerrar(0)

        assert datos_de(leer(capsys))["estrategias"] == [{"nombre": "llm", "resultado": "19246"}]

    def test_los_datos_se_acumulan(self, capsys: pytest.CaptureFixture[str]) -> None:
        s = Salida(command="compare", json_mode=True)
        s.dato(a=1)
        s.dato(b=2)
        s.cerrar(0)

        assert datos_de(leer(capsys)) == {"a": 1, "b": 2}


class TestLaBanderaEsIgualEnTodos:
    def test_add_json_flag_deja_json_en_false_por_defecto(self) -> None:
        """El default tiene que ser el modo de una persona: nadie hereda JSON sin pedirlo."""
        parser = argparse.ArgumentParser()
        add_json_flag(parser)
        assert parser.parse_args([]).json is False
        assert parser.parse_args(["--json"]).json is True

    def test_salida_de_lee_la_bandera(self) -> None:
        parser = argparse.ArgumentParser()
        add_json_flag(parser)
        assert salida_de(parser.parse_args(["--json"]), "compare").json_mode is True
        assert salida_de(parser.parse_args([]), "compare").json_mode is False

    def test_sin_bandera_no_revienta(self) -> None:
        """Un comando sin `--json` sigue funcionando en modo texto."""
        assert salida_de(argparse.Namespace(), "x").json_mode is False


class TestPreguntarNoEsOpcional:
    """`--json` es un formato de salida, nunca un permiso para actuar sin preguntar."""

    def test_en_modo_json_sigue_preguntando(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        preguntado: list[str] = []

        def falso_input(prompt: str = "") -> str:
            preguntado.append(prompt)
            return "0.5"

        monkeypatch.setattr("builtins.input", falso_input)

        s = Salida(command="execute", json_mode=True)
        assert s.pregunta("Escribe la cantidad: ") == "0.5"
        assert preguntado, "en modo JSON la pregunta NO se puede saltar"

    def test_la_pregunta_no_ensucia_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Si el prompt saliera por stdout, el JSON dejaria de ser parseable."""

        def responder(prompt: str = "") -> str:
            return "0.5"

        monkeypatch.setattr("builtins.input", responder)

        s = Salida(command="execute", json_mode=True)
        s.pregunta("Escribe la cantidad: ")
        s.cerrar(0)

        capturado = capsys.readouterr()
        assert "Escribe la cantidad" in capturado.err
        json.loads(capturado.out)

    def test_en_modo_texto_el_prompt_va_por_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recibido: list[str] = []

        def falso_input(prompt: str = "") -> str:
            recibido.append(prompt)
            return "s"

        monkeypatch.setattr("builtins.input", falso_input)
        Salida(command="execute", json_mode=False).pregunta("Continuar? ")
        assert recibido == ["Continuar? "]


class TestComoDict:
    def test_extrae_y_renombra(self) -> None:
        class Falso:
            net_result = D("100")
            trade_count = 5

        assert como_dict(Falso(), {"resultado": "net_result", "ops": "trade_count"}) == {
            "resultado": "100",
            "ops": 5,
        }

    def test_un_atributo_ausente_sale_nulo(self) -> None:
        """Mejor un `null` explicito que un KeyError a mitad de emitir."""
        assert como_dict(object(), {"x": "no_existe"}) == {"x": None}


def _acentos(s: Salida) -> None:
    s.dato(texto="acentos: ñ á é")


def _nulo(s: Salida) -> None:
    s.dato(vacio=None)


def _lista_vacia(s: Salida) -> None:
    s.dato(lista=[])


def _comillas(s: Salida) -> None:
    s.aviso("c", 'mensaje con "comillas" y \\barras')


def _anidado(s: Salida) -> None:
    s.dato(anidado={"a": {"b": [D("1.5")]}})


CARGAS: list[Callable[[Salida], None]] = [
    _acentos,
    _nulo,
    _lista_vacia,
    _comillas,
    _anidado,
]


class TestElJsonEsValidoDeVerdad:
    @pytest.mark.parametrize("carga", CARGAS)
    def test_siempre_parsea(
        self, carga: Callable[[Salida], None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        s = Salida(command="x", json_mode=True)
        carga(s)
        s.cerrar(0)
        json.loads(capsys.readouterr().out)
