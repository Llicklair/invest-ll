"""Tests de la CLI (T055)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from invest_ll.cli import main

CABECERA = "timestamp,open,high,low,close,volume\n"


def escribir_serie(tmp_path: Path, n: int = 120) -> Path:
    """Serie ondulada determinista, con cruces de medias suficientes."""
    filas: list[str] = []
    for i in range(n):
        precio = 100.0 + 20.0 * math.sin(i / 8.0)
        filas.append(
            f"{_fecha(i)},{precio:.2f},{precio + 1:.2f},{precio - 1:.2f},{precio:.2f},1000\n"
        )
    ruta = tmp_path / "serie.csv"
    ruta.write_text(CABECERA + "".join(filas), encoding="utf-8")
    return ruta


def _fecha(i: int) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat()


def test_la_cli_ejecuta_un_backtest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruta = escribir_serie(tmp_path)
    codigo = main(
        [str(ruta), "--commission", "0.001", "--slippage", "0.0005", "--short", "3", "--long", "10"]
    )
    salida = capsys.readouterr().out
    assert "Resultado neto" in salida
    assert codigo in (0, 3)


def test_los_costes_son_obligatorios(tmp_path: Path) -> None:
    """El Principio IV también se aplica en la línea de comandos."""
    ruta = escribir_serie(tmp_path)
    with pytest.raises(SystemExit):
        main([str(ruta)])


def test_fichero_inexistente_devuelve_codigo_2(tmp_path: Path) -> None:
    codigo = main([str(tmp_path / "no_existe.csv"), "--commission", "0", "--slippage", "0"])
    assert codigo == 2


def test_resultado_no_concluyente_devuelve_codigo_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Encadenable en un script sin dar por bueno lo que no concluye."""
    ruta = escribir_serie(tmp_path, n=40)
    codigo = main([str(ruta), "--commission", "0.001", "--slippage", "0", "--min-trades", "1000"])
    capsys.readouterr()
    assert codigo == 3


def test_configuracion_invalida_devuelve_codigo_1(tmp_path: Path) -> None:
    ruta = escribir_serie(tmp_path)
    codigo = main([str(ruta), "--commission", "0.001", "--slippage", "0", "--fraction", "5"])
    assert codigo == 1


def test_la_salida_es_imprimible_en_consola_windows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruta = escribir_serie(tmp_path)
    main([str(ruta), "--commission", "0.001", "--slippage", "0"])
    capsys.readouterr().out.encode("cp1252")
