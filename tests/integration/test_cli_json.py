"""Los comandos con `--json`, de extremo a extremo.

`test_cli_emit.py` prueba el sobre; esto prueba que los comandos lo usan bien. La distinción
importa: el módulo puede estar perfecto y un comando seguir escribiendo por su cuenta, que es
exactamente el fallo que ya ocurrió dos veces en este proyecto — código correcto, nunca conectado.

Lo que más se comprueba aquí no son los números, sino que **los avisos llegan al JSON**. Un
agente que lea `net_result` sin leer `no_advantage_over_holding` tiene la mitad de la historia,
y es la mitad equivocada.
"""

from __future__ import annotations

import ast
import csv
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from invest_ll.cli import main as backtest_main
from invest_ll.cli.compare import SALIDA_NO_ENCONTRADO, SALIDA_OK
from invest_ll.cli.compare import main as compare_main
from invest_ll.cli.emit import (
    AVISO_SIN_VENTAJA,
    AVISO_SOLO_SIMULACION,
    AVISO_WIN_RATE,
    VERSION_FORMATO,
)
from invest_ll.cli.execute import main as execute_main
from invest_ll.cli.propose import main as propose_main
from invest_ll.cli.track import main as track_main

from ..fixtures.builders import ORIGIN, ramp

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal


def escribir_csv(destino: Path, cierres: list[float]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i, cierre in enumerate(cierres):
            marca = ORIGIN + timedelta(days=i)
            w.writerow([marca.isoformat(), cierre, cierre * 1.01, cierre * 0.99, cierre, 1000])


@pytest.fixture
def mercado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    # Comparar apunta cuántas pruebas llevas en `attempts/`, relativo al directorio de trabajo:
    # sin esto, la suite lo dejaba en la raíz del repositorio con AAA y BBB.
    monkeypatch.chdir(tmp_path)
    a = tmp_path / "yfinance" / "AAA" / "DAY_1.csv"
    b = tmp_path / "yfinance" / "BBB" / "DAY_1.csv"
    escribir_csv(a, list(ramp(200)))
    escribir_csv(b, list(ramp(200, start=50.0)))
    return a, b


def sobre_de(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """El JSON de stdout. Que esto no reviente ya es media prueba.

    Si el comando imprimiera una sola linea suelta ademas del sobre, `json.loads` fallaria — que
    es justo lo que debe pasar, porque quien consuma la salida tampoco podria leerla.
    """
    crudo = capsys.readouterr().out
    return cast("dict[str, object]", json.loads(crudo))


def codigos_de_aviso(sobre: dict[str, object]) -> list[str]:
    avisos = sobre["warnings"]
    assert isinstance(avisos, list)
    return [str(cast("dict[str, object]", a)["code"]) for a in cast("list[object]", avisos)]


def cuerpo_de(sobre: dict[str, object]) -> dict[str, object]:
    datos = sobre["data"]
    assert isinstance(datos, dict)
    return cast("dict[str, object]", datos)


class TestStdoutEsSoloElSobre:
    """En modo JSON nada mas puede salir por stdout."""

    def test_compare(self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
        a, b = mercado
        codigo = compare_main(
            [
                str(a),
                str(b),
                "--strategies",
                "momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--json",
            ]
        )
        sobre = sobre_de(capsys)
        assert sobre["command"] == "compare"
        assert sobre["format_version"] == VERSION_FORMATO
        assert sobre["exit_code"] == codigo, "el sobre y el proceso tienen que coincidir"

    def test_backtest(self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
        a, _ = mercado
        backtest_main(
            [str(a), "--symbol", "AAA", "--commission", "0.001", "--slippage", "0.0005", "--json"]
        )
        assert sobre_de(capsys)["command"] == "backtest"

    def test_propose(self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
        a, b = mercado
        propose_main([str(a), str(b), "--amount", "500", "--json"])
        assert sobre_de(capsys)["command"] == "propose"

    def test_track_list(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        track_main(["--store", str(tmp_path), "list", "--json"])
        assert sobre_de(capsys)["command"] == "track list"


class TestLosAvisosLleganAlJson:
    """La razon de ser del modo JSON, comprobada sobre los comandos reales."""

    def test_compare_avisa_de_que_no_hay_ventaja(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sin este aviso, un agente leeria el resultado como si fuera bueno."""
        a, b = mercado
        compare_main(
            [
                str(a),
                str(b),
                "--strategies",
                "momentum",
                "--commission",
                "0.05",  # comision alta: se asegura de que no bata a no hacer nada
                "--slippage",
                "0.01",
                "--json",
            ]
        )
        codigos = codigos_de_aviso(sobre_de(capsys))
        assert AVISO_SIN_VENTAJA in codigos
        assert AVISO_WIN_RATE in codigos

    def test_el_backtest_lleva_la_coletilla_del_win_rate(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        a, _ = mercado
        backtest_main(
            [str(a), "--symbol", "AAA", "--commission", "0.001", "--slippage", "0.0005", "--json"]
        )
        assert AVISO_WIN_RATE in codigos_de_aviso(sobre_de(capsys))

    def test_los_avisos_llevan_texto_y_no_solo_codigo(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Un codigo sin explicacion obligaria a quien consuma a saberselos de memoria."""
        a, b = mercado
        compare_main(
            [
                str(a),
                str(b),
                "--strategies",
                "momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--json",
            ]
        )
        avisos = sobre_de(capsys)["warnings"]
        assert isinstance(avisos, list)
        for crudo in cast("list[object]", avisos):
            aviso = cast("dict[str, object]", crudo)
            assert str(aviso["message"]).strip(), f"aviso {aviso['code']} sin texto"


class TestLosNumerosSonLosMismos:
    """El modo JSON no puede cambiar el resultado, solo su forma."""

    def test_el_codigo_de_salida_no_depende_del_formato(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        a, b = mercado
        argumentos = [
            str(a),
            str(b),
            "--strategies",
            "momentum",
            "--commission",
            "0.001",
            "--slippage",
            "0.0005",
        ]
        en_texto = compare_main(argumentos)
        capsys.readouterr()
        en_json = compare_main([*argumentos, "--json"])
        capsys.readouterr()
        assert en_texto == en_json

    def test_el_resultado_sale_como_cadena_exacta(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dinero como texto: convertirlo a float en la frontera perderia centimos."""
        a, b = mercado
        compare_main(
            [
                str(a),
                str(b),
                "--strategies",
                "momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--json",
            ]
        )
        estrategias = cuerpo_de(sobre_de(capsys))["strategies"]
        assert isinstance(estrategias, list)
        primera = cast("dict[str, object]", cast("list[object]", estrategias)[0])
        assert isinstance(primera["net_result"], str)
        D(primera["net_result"])  # tiene que reconstruirse sin perder nada


class TestElErrorTambienEsJson:
    def test_un_fichero_que_no_existe(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quien parsea stdout necesita poder leer el fallo sin mirar stderr."""
        codigo = compare_main(
            [
                "no/existe.csv",
                "--strategies",
                "momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--json",
            ]
        )
        sobre = sobre_de(capsys)
        assert codigo == SALIDA_NO_ENCONTRADO
        assert sobre["ok"] is False
        assert sobre["exit_code"] == SALIDA_NO_ENCONTRADO
        assert "existe" in str(sobre["error"])


class TestEjecutarSigueSiendoDificil:
    """`--json` es un formato de salida, NUNCA un permiso.

    El Principio I dice que el modo simulacion es el estado por defecto y que ninguna orden real
    sale sin confirmacion humana. Anhadir una bandera de formato no puede erosionar eso, y estos
    tests existen para que no lo haga en silencio.
    """

    def test_en_simulacion_no_sale_nada_y_se_dice(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for variable in ("INVEST_LL_MODE", "INVEST_LL_LIVE_KEY", "INVEST_LL_TESTNET_KEY"):
            monkeypatch.delenv(variable, raising=False)

        codigo = execute_main(
            ["--symbol", "BTC/USDT", "--side", "buy", "--quantity", "0.01", "--json"]
        )
        sobre = sobre_de(capsys)

        assert codigo == SALIDA_OK
        assert cuerpo_de(sobre)["submitted"] is False, "en simulacion no se envia nada"
        assert AVISO_SOLO_SIMULACION in codigos_de_aviso(sobre)

    def test_el_modo_viaja_siempre_en_el_json(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Quien lea esta salida tiene que saber en que mundo ocurrio antes que ningun numero."""
        monkeypatch.delenv("INVEST_LL_MODE", raising=False)
        execute_main(["--symbol", "BTC/USDT", "--side", "buy", "--quantity", "0.01", "--json"])
        assert cuerpo_de(sobre_de(capsys))["mode"] == "simulacion"

    def test_json_no_es_una_forma_de_saltarse_la_confirmacion(self) -> None:
        """Comprobacion estructural: la confirmacion no mira la bandera de formato.

        Se mira el AST y **se descarta el docstring** a proposito: la primera version de este
        test leia el texto plano y se puso rojo por una frase de la documentacion que explicaba
        justo esta regla. Un guardian que confunde hablar de algo con hacerlo obliga a no
        documentar, que es peor que no tenerlo.

        Se inspecciona el codigo en vez de simular una orden real porque montar un modo real en
        un test seria justo la clase de atajo que este test existe para impedir.
        """
        arbol = ast.parse(Path("src/invest_ll/cli/execute.py").read_text(encoding="utf-8"))
        funcion = next(
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.FunctionDef) and n.name == "_pedir_confirmacion"
        )

        cuerpo = funcion.body[1:] if ast.get_docstring(funcion) else funcion.body
        nombres = {
            nodo.attr
            for rama in cuerpo
            for nodo in ast.walk(rama)
            if isinstance(nodo, ast.Attribute)
        }

        assert "json_mode" not in nombres, (
            "la confirmacion NO puede ramificar por el formato de salida: seria una via "
            "para que un agente enviara una orden sin que nadie la confirme"
        )
        assert "pregunta" in nombres, "tiene que seguir preguntando"

    def test_el_guardian_de_arriba_detecta_de_verdad(self) -> None:
        """Contra codigo que SI deberia marcar: si no lo ve, el test de arriba pasa por vacio."""
        sospechoso = ast.parse("def f(salida):\n    if salida.json_mode:\n        return True\n")
        nombres = {n.attr for n in ast.walk(sospechoso) if isinstance(n, ast.Attribute)}
        assert "json_mode" in nombres


class TestSinLaBanderaNadaCambia:
    """Un proyecto que no use `--json` no puede notar que existe."""

    def test_el_texto_sigue_saliendo_igual(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        a, b = mercado
        compare_main(
            [
                str(a),
                str(b),
                "--strategies",
                "momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
            ]
        )
        texto = capsys.readouterr().out

        assert "RESULTADO" in texto and "DRAWDOWN" in texto
        assert "win rate" in texto
        with pytest.raises(json.JSONDecodeError):
            json.loads(texto)

    @pytest.mark.parametrize(
        "argumentos",
        [
            ["--strategies", "momentum", "--commission", "0.001", "--slippage", "0.0005"],
            ["--strategies", "momentum", "--commission", "0.05", "--slippage", "0.01"],
        ],
    )
    def test_el_codigo_de_salida_es_el_de_siempre(
        self,
        mercado: tuple[Path, Path],
        argumentos: Sequence[str],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a, b = mercado
        codigo = compare_main([str(a), str(b), *argumentos])
        capsys.readouterr()
        assert codigo in (SALIDA_OK, 3), "solo OK o no concluyente"
