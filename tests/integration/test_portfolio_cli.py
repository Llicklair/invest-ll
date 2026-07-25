"""`invest-ll-portfolio` de extremo a extremo: registrar, importar, y ver la cartera."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_NO_ENCONTRADO, SALIDA_OK
from invest_ll.cli.portfolio import main


def sobre_de(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(capsys.readouterr().out))


def datos_de(sobre: dict[str, object]) -> dict[str, object]:
    datos = sobre["data"]
    assert isinstance(datos, dict)
    return cast("dict[str, object]", datos)


def anadir(store: Path, *extra: str) -> int:
    return main(["--store", str(store), *extra])


class TestElCicloCompleto:
    def test_comprar_ver_vender_y_ver_lo_retirado(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """La historia entera: entra, aparece en abiertas; sale, aparece en retiradas."""
        assert anadir(tmp_path, "cash", "deposit", "--amount", "5000", "--date", "2026-01-01") == 0
        capsys.readouterr()
        assert (
            anadir(
                tmp_path,
                "add",
                "buy",
                "--symbol",
                "AAA",
                "--quantity",
                "10",
                "--price",
                "100",
                "--fee",
                "5",
                "--date",
                "2026-01-02",
            )
            == 0
        )
        capsys.readouterr()

        assert anadir(tmp_path, "show", "--json") == SALIDA_OK
        datos = datos_de(sobre_de(capsys))
        abiertas = cast("list[dict[str, object]]", datos["open_positions"])
        assert len(abiertas) == 1
        assert abiertas[0]["symbol"] == "AAA"
        assert abiertas[0]["avg_cost"] == "100.5"

        assert (
            anadir(
                tmp_path,
                "add",
                "sell",
                "--symbol",
                "AAA",
                "--quantity",
                "10",
                "--price",
                "120",
                "--fee",
                "5",
                "--date",
                "2026-03-02",
            )
            == 0
        )
        capsys.readouterr()

        assert anadir(tmp_path, "show", "--json") == SALIDA_OK
        datos = datos_de(sobre_de(capsys))
        assert datos["open_positions"] == []
        retiradas = cast("list[dict[str, object]]", datos["closed_trades"])
        assert len(retiradas) == 1
        assert retiradas[0]["realized_pnl"] == "190"
        assert retiradas[0]["holding_days"] == 59

    def test_en_texto_las_dos_secciones_se_distinguen(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Abiertas = valoracion; retiradas = hecho. El texto lo dice, no lo da por sabido."""
        anadir(tmp_path, "add", "buy", "--symbol", "AAA", "--quantity", "5", "--price", "100")
        anadir(tmp_path, "add", "buy", "--symbol", "BBB", "--quantity", "5", "--price", "50")
        anadir(tmp_path, "add", "sell", "--symbol", "BBB", "--quantity", "5", "--price", "60")
        capsys.readouterr()

        anadir(tmp_path, "show")
        texto = capsys.readouterr().out
        assert "valoracion, no un hecho" in texto
        assert "ya no cambia" in texto


class TestLaCarteraVacia:
    def test_dice_como_empezar(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert anadir(tmp_path, "show") == SALIDA_OK
        texto = capsys.readouterr().out
        assert "vacia" in texto
        assert "invest-ll-portfolio add" in texto


class TestErroresHonestos:
    def test_vender_lo_que_no_hay_falla_al_mirar(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        anadir(tmp_path, "add", "sell", "--symbol", "AAA", "--quantity", "10", "--price", "100")
        capsys.readouterr()
        codigo = anadir(tmp_path, "show", "--json")
        sobre = sobre_de(capsys)

        assert codigo == SALIDA_ERROR
        assert sobre["ok"] is False
        assert "Falta alguna compra" in str(sobre["error"])

    def test_un_duplicado_exacto_se_rechaza(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argumentos = [
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
        assert anadir(tmp_path, *argumentos) == SALIDA_OK
        capsys.readouterr()
        assert anadir(tmp_path, *argumentos) == SALIDA_ERROR
        assert "dos veces" in capsys.readouterr().err

    def test_un_csv_inexistente(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        codigo = anadir(tmp_path, "import", str(tmp_path / "no-existe.csv"))
        capsys.readouterr()
        assert codigo == SALIDA_NO_ENCONTRADO


class TestImportarDosVecesNoDuplica:
    def test_reimportar_es_idempotente(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Reimportar el mismo CSV del broker no puede duplicar la cartera."""
        csv_path = tmp_path / "movs.csv"
        csv_path.write_text(
            "Date,Symbol,Type,Quantity,Unit Price,Fee\n2026-01-15,AAA,buy,10,180,1\n",
            encoding="utf-8",
        )
        store = tmp_path / "store"

        assert main(["--store", str(store), "import", str(csv_path), "--json"]) == SALIDA_OK
        assert datos_de(sobre_de(capsys))["imported"] == 1

        assert main(["--store", str(store), "import", str(csv_path), "--json"]) == SALIDA_OK
        datos = datos_de(sobre_de(capsys))
        assert datos["imported"] == 0
        assert datos["already_present"] == 1

    def test_lo_saltado_viaja_como_aviso_en_el_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "movs.csv"
        csv_path.write_text(
            "Date,Symbol,Type,Quantity,Unit Price\n"
            "2026-01-15,AAA,buy,10,180\n"
            "2026-02-01,AAA,dividend,1,2\n",
            encoding="utf-8",
        )
        main(["--store", str(tmp_path / "store"), "import", str(csv_path), "--json"])
        sobre = sobre_de(capsys)
        avisos = cast("list[dict[str, str]]", sobre["warnings"])
        assert any(a["code"] == "import_partial" for a in avisos)


class TestElJsonConservaElDinero:
    def test_los_importes_salen_como_cadena(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        anadir(tmp_path, "add", "buy", "--symbol", "AAA", "--quantity", "3", "--price", "33.33")
        capsys.readouterr()
        anadir(tmp_path, "show", "--json")
        abiertas = cast("list[dict[str, object]]", datos_de(sobre_de(capsys))["open_positions"])
        assert isinstance(abiertas[0]["invested"], str)
