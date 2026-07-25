"""`invest-ll-triggers` de extremo a extremo, incluida la pausa sobre `invest-ll-propose`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from invest_ll.cli.alerts import SALIDA_HAY_QUE_REVISAR
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK
from invest_ll.cli.portfolio import main as portfolio_main
from invest_ll.cli.propose import main as propose_main
from invest_ll.cli.triggers import main as triggers_main


def sobre_de(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(capsys.readouterr().out))


def datos_de(sobre: dict[str, object]) -> dict[str, object]:
    datos = sobre["data"]
    assert isinstance(datos, dict)
    return cast("dict[str, object]", datos)


@pytest.fixture
def con_posicion(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """Un store con una compra de AAA a 100."""
    portfolio_main(
        [
            "--store",
            str(tmp_path),
            "add",
            "buy",
            "--symbol",
            "AAA",
            "--quantity",
            "10",
            "--price",
            "100",
            "--date",
            "2026-01-02",
        ]
    )
    capsys.readouterr()
    return tmp_path


def precios(base: Path, simbolo: str, cierres: list[float]) -> None:
    """Escribe data/market/test/<simbolo>/DAY_1.csv relativo a `base` (cwd del test)."""
    destino = base / "data" / "market" / "test" / simbolo / "DAY_1.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    filas = ["timestamp,open,high,low,close,volume"]
    filas += [
        f"2026-07-{i + 1:02d}T00:00:00+00:00,{c},{c},{c},{c},1000" for i, c in enumerate(cierres)
    ]
    destino.write_text("\n".join(filas) + "\n", encoding="utf-8")


class TestArmarYComprobar:
    def test_el_ciclo_completo(
        self,
        con_posicion: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Armar, caer el precio, y ver la orden PROPUESTA con codigo de revisar."""
        monkeypatch.chdir(tmp_path)
        precios(tmp_path, "AAA", [100.0, 95.0, 80.0])  # -20% desde la entrada a 100

        assert (
            triggers_main(
                [
                    "--store",
                    str(con_posicion),
                    "arm",
                    "--symbol",
                    "AAA",
                    "--rule",
                    "loss-from-entry",
                    "--threshold",
                    "0.15",
                ]
            )
            == SALIDA_OK
        )
        capsys.readouterr()

        codigo = triggers_main(["--store", str(con_posicion), "check", "--json"])
        sobre = sobre_de(capsys)
        disparados = cast("list[dict[str, object]]", datos_de(sobre)["fired"])

        assert codigo == SALIDA_HAY_QUE_REVISAR
        assert sobre["ok"] is True, "que salte un trigger no es que el comando falle"
        assert len(disparados) == 1
        assert disparados[0]["proposed_quantity"] == "10"

    def test_sin_caida_no_salta(
        self,
        con_posicion: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        precios(tmp_path, "AAA", [100.0, 101.0])
        triggers_main(
            [
                "--store",
                str(con_posicion),
                "arm",
                "--symbol",
                "AAA",
                "--rule",
                "loss-from-entry",
                "--threshold",
                "0.15",
            ]
        )
        capsys.readouterr()

        assert triggers_main(["--store", str(con_posicion), "check"]) == SALIDA_OK
        texto = capsys.readouterr().out
        assert "ninguna de TUS reglas" in texto, "no saltar no es 'todo va bien'"

    def test_sin_datos_del_activo_se_dice_no_se_calla(
        self,
        con_posicion: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)  # sin data/market: no hay precios de AAA
        triggers_main(
            [
                "--store",
                str(con_posicion),
                "arm",
                "--symbol",
                "AAA",
                "--rule",
                "loss-from-entry",
                "--threshold",
                "0.15",
            ]
        )
        capsys.readouterr()

        triggers_main(["--store", str(con_posicion), "check", "--json"])
        sobre = sobre_de(capsys)
        avisos = cast("list[dict[str, str]]", sobre["warnings"])
        assert any(a["code"] == "trigger_not_evaluated" for a in avisos)


class TestElKillSwitch:
    def test_la_pausa_frena_a_propose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Nivel 1: con la pausa activa, invest-ll-propose se niega y dice por que."""
        monkeypatch.chdir(tmp_path)
        assert (
            triggers_main(["halt", "--reason", "mercado revuelto, freno voluntario"]) == SALIDA_OK
        )
        capsys.readouterr()

        codigo = propose_main(["cualquier.csv", "--amount", "500", "--json"])
        sobre = sobre_de(capsys)
        assert codigo == SALIDA_ERROR
        assert "en pausa" in str(sobre["error"])
        assert "revuelto" in str(sobre["error"]), "la pausa recuerda SU motivo"

        triggers_main(["resume"])
        capsys.readouterr()

    def test_la_pausa_sin_motivo_no_existe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert triggers_main(["halt", "--reason", "  "]) == SALIDA_ERROR
        capsys.readouterr()

    def test_liquidar_propone_todo_sin_enviar_nada(
        self, con_posicion: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Nivel 2: una orden por posicion, listas para confirmar una a una."""
        codigo = triggers_main(["--store", str(con_posicion), "liquidate", "--json"])
        sobre = sobre_de(capsys)
        comandos = cast("list[str]", datos_de(sobre)["commands"])

        assert codigo == SALIDA_OK
        assert len(comandos) == 1
        assert "--symbol AAA --side sell --quantity 10" in comandos[0]
        assert comandos[0].startswith("uv run invest-ll-execute")

    def test_liquidar_sin_posiciones(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert triggers_main(["--store", str(tmp_path), "liquidate"]) == SALIDA_OK
        assert "No hay posiciones" in capsys.readouterr().out


class TestListarYDesarmar:
    def test_listar_ensena_la_pausa_y_los_armados(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        triggers_main(
            [
                "--store",
                str(tmp_path),
                "arm",
                "--symbol",
                "GLD",
                "--rule",
                "drop-from-peak",
                "--threshold",
                "0.2",
            ]
        )
        capsys.readouterr()
        triggers_main(["--store", str(tmp_path), "list", "--json"])
        datos = datos_de(sobre_de(capsys))
        armados = cast("list[dict[str, object]]", datos["triggers"])

        assert len(armados) == 1
        assert armados[0]["rule"] == "drop-from-peak"
        assert datos["halted"] is None

    def test_desarmar_lo_inexistente_falla(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert triggers_main(["--store", str(tmp_path), "disarm", "--id", "trg-9"]) == SALIDA_ERROR
        capsys.readouterr()
