"""T012 — carga y validación de series (FR-015, FR-016, FR-021)."""

from __future__ import annotations

from pathlib import Path

import pytest

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.loader import load_series
from invest_ll.errors import InvalidSeriesError

CABECERA = "timestamp,open,high,low,close,volume\n"

FILAS_OK = (
    "2026-01-01T00:00:00+00:00,100,101,99,100.5,1000\n"
    "2026-01-02T00:00:00+00:00,100.5,102,100,101.5,1200\n"
    "2026-01-03T00:00:00+00:00,101.5,103,101,102.5,900\n"
)


def escribir(tmp_path: Path, contenido: str, nombre: str = "serie.csv") -> Path:
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def cargar(ruta: Path):  # type: ignore[no-untyped-def]
    return load_series(ruta, symbol="TEST", interval=Interval.DAY_1, calendar=Continuous24x7())


def test_csv_valido_carga(tmp_path: Path) -> None:
    serie, avisos = cargar(escribir(tmp_path, CABECERA + FILAS_OK))
    assert len(serie) == 3
    assert serie.symbol == "TEST"
    assert avisos == ()


def test_columna_ausente_se_rechaza(tmp_path: Path) -> None:
    sin_volumen = "timestamp,open,high,low,close\n2026-01-01T00:00:00+00:00,100,101,99,100.5\n"
    with pytest.raises(InvalidSeriesError, match=r"columna|volume"):
        cargar(escribir(tmp_path, sin_volumen))


def test_precio_negativo_se_rechaza(tmp_path: Path) -> None:
    malo = CABECERA + "2026-01-01T00:00:00+00:00,-100,101,99,100.5,1000\n"
    with pytest.raises(InvalidSeriesError):
        cargar(escribir(tmp_path, malo))


def test_fichero_vacio_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(InvalidSeriesError):
        cargar(escribir(tmp_path, CABECERA))


def test_fichero_inexistente_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises((FileNotFoundError, InvalidSeriesError)):
        cargar(tmp_path / "no_existe.csv")


def test_formato_no_soportado_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(InvalidSeriesError, match=r"formato|extensión"):
        cargar(escribir(tmp_path, CABECERA + FILAS_OK, nombre="serie.txt"))


def test_hueco_en_mercado_continuo_genera_aviso(tmp_path: Path) -> None:
    """FR-016: el hueco se reporta, nunca se rellena en silencio."""
    con_hueco = (
        CABECERA
        + "2026-01-01T00:00:00+00:00,100,101,99,100.5,1000\n"
        + "2026-01-04T00:00:00+00:00,101.5,103,101,102.5,900\n"
    )
    serie, avisos = cargar(escribir(tmp_path, con_hueco))
    assert len(serie) == 2, "el hueco no se rellena: siguen siendo dos velas"
    assert len(avisos) >= 1
    assert any("hueco" in aviso.message.lower() for aviso in avisos)


def test_los_avisos_se_devuelven_no_se_registran(tmp_path: Path) -> None:
    """Devolverlos obliga a quien llama a recibirlos; un log se ignora."""
    _, avisos = cargar(escribir(tmp_path, CABECERA + FILAS_OK))
    assert isinstance(avisos, tuple)
