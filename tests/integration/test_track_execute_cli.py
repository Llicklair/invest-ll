"""Los dos comandos que cierran la feature 003 (T056, T075).

`invest-ll-execute` es el único comando del proyecto que puede mover dinero, así que la mayoría de
sus tests comprueban **lo que no debe pasar**.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from invest_ll.cli.execute import (
    SALIDA_CANCELADO,
    SALIDA_ERROR,
    SALIDA_OK,
)
from invest_ll.cli.execute import main as ejecutar
from invest_ll.cli.track import main as seguir


class TestSeguimiento:
    """T056. La única evidencia limpia que este proyecto puede producir sobre el LLM."""

    def test_sin_estimaciones_explica_como_empezar(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert seguir(["--store", str(tmp_path), "list"]) == SALIDA_OK
        salida = capsys.readouterr().out
        assert "No hay ninguna estimacion" in salida
        assert "invest-ll-track issue" in salida, "debe decir como emitir la primera"

    def test_emitir_registra_y_dice_cuando_vence(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        codigo = seguir(
            [
                "--store",
                str(tmp_path),
                "issue",
                "--expected",
                "320000",
                "--horizon",
                "90",
                "--basis",
                "aportaciones periodicas sobre 4 activos",
                "--holding",
                "GLD:10",
            ]
        )
        salida = capsys.readouterr().out
        assert codigo == SALIDA_OK
        assert "Vence" in salida
        assert "Ya no se puede modificar" in salida

    def test_dos_emisiones_seguidas_son_estimaciones_distintas(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """El identificador incluye el instante de emision, asi que dos previsiones del mismo
        valor en momentos distintos NO son la misma: registrar ambas es correcto.

        Lo que FR-021 impide es reescribir una ya registrada, y eso lo cubre el almacen
        (`test_forecast.py::test_reescribir_una_estimacion_falla`), no el comando.
        """
        args = [
            "--store",
            str(tmp_path),
            "issue",
            "--expected",
            "320000",
            "--horizon",
            "90",
            "--basis",
            "x",
        ]
        assert seguir(args) == SALIDA_OK
        assert seguir(args) == SALIDA_OK

        capsys.readouterr()
        seguir(["--store", str(tmp_path), "list"])
        filas = [linea for linea in capsys.readouterr().out.splitlines() if "esperando" in linea]
        assert len(filas) == 2, "ambas deben quedar registradas y visibles"

    def test_sin_base_no_se_puede_emitir(self, tmp_path: Path) -> None:
        """Una estimacion sin explicar en que se basa no se puede evaluar despues."""
        with pytest.raises(SystemExit):
            seguir(["--store", str(tmp_path), "issue", "--expected", "1000"])

    def test_una_cartera_mal_escrita_se_rechaza(self, tmp_path: Path) -> None:
        codigo = seguir(
            [
                "--store",
                str(tmp_path),
                "issue",
                "--expected",
                "1000",
                "--basis",
                "x",
                "--holding",
                "GLD-10",
            ]
        )
        assert codigo == SALIDA_ERROR

    def test_registrar_un_resultado_muestra_el_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seguir(["--store", str(tmp_path), "issue", "--expected", "1000", "--basis", "x"])
        identificador = capsys.readouterr().out.split("Estimacion registrada: ")[1].split("\n")[0]

        assert (
            seguir(["--store", str(tmp_path), "record", "--id", identificador, "--actual", "1200"])
            == SALIDA_OK
        )
        salida = capsys.readouterr().out
        assert "Estimado" in salida
        assert "Real" in salida
        assert "por encima" in salida

    def test_registrar_un_id_inexistente_falla(self, tmp_path: Path) -> None:
        codigo = seguir(["--store", str(tmp_path), "record", "--id", "noexiste", "--actual", "100"])
        assert codigo == SALIDA_ERROR

    def test_el_historial_conserva_los_fallos(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """FR-023: un historial que solo guarda los aciertos no mide nada."""
        for esperado, real in (("1000", "500"), ("2000", "2100")):
            seguir(["--store", str(tmp_path), "issue", "--expected", esperado, "--basis", "x"])
            ident = capsys.readouterr().out.split("Estimacion registrada: ")[1].split("\n")[0]
            seguir(["--store", str(tmp_path), "record", "--id", ident, "--actual", real])
            capsys.readouterr()

        seguir(["--store", str(tmp_path), "evaluate"])
        salida = capsys.readouterr().out
        assert "Evaluadas               2" in salida
        assert "solo guarda los" in salida


def _responder(texto: str) -> Callable[[str], str]:
    """Sustituto de `input` para los tests: responde siempre lo mismo, con tipo explicito."""

    def responder(_prompt: str) -> str:
        return texto

    return responder


class TestEjecucionNoSaleNadaPorDefecto:
    """T075. Lo que NO debe poder pasar."""

    def test_sin_configurar_nada_no_se_envia(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("INVEST_LL_MODE", "INVEST_LL_LIVE_KEY", "INVEST_LL_TESTNET_KEY"):
            monkeypatch.delenv(var, raising=False)

        codigo = ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--ledger",
                str(tmp_path),
            ]
        )
        salida = capsys.readouterr().out

        assert codigo == SALIDA_OK
        assert "MODO SIMULACION" in salida
        assert "no se ha enviado nada" in salida.lower()

    def test_explica_las_cuatro_condiciones(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Decir 'no puedes' sin decir 'que hace falta' deja al operador igual de perdido."""
        monkeypatch.delenv("INVEST_LL_MODE", raising=False)
        ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--ledger",
                str(tmp_path),
            ]
        )
        salida = capsys.readouterr().out
        assert "CUATRO cosas" in salida
        assert "INVEST_LL_TESTNET_VERIFIED" in salida
        assert "Empieza por testnet" in salida

    def test_en_simulacion_no_se_escribe_en_el_registro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si no ha salido nada, no hay nada que registrar."""
        monkeypatch.delenv("INVEST_LL_MODE", raising=False)
        ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--ledger",
                str(tmp_path),
            ]
        )
        assert not (tmp_path / "orders.jsonl").exists()

    def test_una_cantidad_no_positiva_se_rechaza(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("INVEST_LL_MODE", raising=False)
        codigo = ejecutar(
            ["--symbol", "BTC/USDT", "--side", "buy", "--quantity", "0", "--ledger", str(tmp_path)]
        )
        assert codigo == SALIDA_ERROR

    def test_el_modo_real_sin_testnet_previa_se_rechaza(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-047: los fallos de ejecucion se descubren en pruebas, no pagandolos."""
        monkeypatch.setenv("INVEST_LL_MODE", "real")
        monkeypatch.setenv("INVEST_LL_LIVE_KEY", "k")
        monkeypatch.setenv("INVEST_LL_LIVE_SECRET", "s")
        monkeypatch.delenv("INVEST_LL_TESTNET_VERIFIED", raising=False)

        codigo = ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--ledger",
                str(tmp_path),
            ]
        )
        assert codigo == SALIDA_ERROR
        assert "red de pruebas" in capsys.readouterr().err

    def test_la_confirmacion_exige_escribir_la_cantidad(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un 's' distraido no deberia mover 0.5 BTC."""
        monkeypatch.setenv("INVEST_LL_MODE", "testnet")
        monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "k")
        monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "s")
        monkeypatch.setattr("builtins.input", _responder("s"))

        codigo = ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--ledger",
                str(tmp_path),
            ]
        )
        assert codigo == SALIDA_CANCELADO
        assert "no coincide" in capsys.readouterr().out

    def test_cancelar_no_deja_rastro_en_el_registro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INVEST_LL_MODE", "testnet")
        monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "k")
        monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "s")
        monkeypatch.setattr("builtins.input", _responder(""))

        ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--ledger",
                str(tmp_path),
            ]
        )
        assert not (tmp_path / "orders.jsonl").exists()

    def test_dry_run_no_pide_confirmacion_ni_envia(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INVEST_LL_MODE", "testnet")
        monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "k")
        monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "s")

        def no_preguntar(_: str) -> str:  # pragma: no cover - no debe llamarse
            raise AssertionError("--dry-run no debe pedir confirmacion")

        monkeypatch.setattr("builtins.input", no_preguntar)

        codigo = ejecutar(
            [
                "--symbol",
                "BTC/USDT",
                "--side",
                "buy",
                "--quantity",
                "0.001",
                "--dry-run",
                "--ledger",
                str(tmp_path),
            ]
        )
        assert codigo == SALIDA_OK
        assert "no se ha enviado nada" in capsys.readouterr().out
        assert not (tmp_path / "orders.jsonl").exists()
