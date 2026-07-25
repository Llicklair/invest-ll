"""Recortar una serie a un subperiodo.

Es la base de la validación fuera de muestra: medir la estrategia en un tramo y comprobarla en
otro que no se usó para decidir nada. Sin esto no se puede distinguir una estrategia de un
periodo afortunado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from invest_ll.data.bar import Interval
from invest_ll.errors import InvalidSeriesError

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

PASO = Interval.DAY_1.duration


def test_recorta_por_el_principio() -> None:
    serie = series_from_closes(ramp(10))
    recortada = serie.slice(start=ORIGIN + PASO * 5)
    assert len(recortada) == 5
    assert recortada.bars[0].timestamp == ORIGIN + PASO * 5


def test_recorta_por_el_final() -> None:
    serie = series_from_closes(ramp(10))
    recortada = serie.slice(end=ORIGIN + PASO * 5)
    assert len(recortada) == 5


def test_recorta_por_ambos_lados() -> None:
    serie = series_from_closes(ramp(10))
    recortada = serie.slice(start=ORIGIN + PASO * 2, end=ORIGIN + PASO * 7)
    assert len(recortada) == 5


def test_sin_limites_devuelve_todo() -> None:
    serie = series_from_closes(ramp(10))
    assert len(serie.slice()) == 10


def test_el_final_es_exclusivo() -> None:
    """Mismo criterio que en la descarga: [inicio, fin)."""
    serie = series_from_closes(ramp(10))
    recortada = serie.slice(start=ORIGIN, end=ORIGIN + PASO * 3)
    assert [b.close for b in recortada.bars] == [100.0, 101.0, 102.0]


def test_conserva_activo_intervalo_y_calendario() -> None:
    serie = series_from_closes(ramp(10))
    recortada = serie.slice(start=ORIGIN + PASO * 2)
    assert recortada.symbol == serie.symbol
    assert recortada.interval is serie.interval
    assert type(recortada.calendar) is type(serie.calendar)


def test_un_recorte_vacio_se_rechaza() -> None:
    """Devolver una serie vacía dejaría el error para más adelante y más lejos."""
    serie = series_from_closes(ramp(10))
    with pytest.raises(InvalidSeriesError, match=r"vac|ninguna vela"):
        serie.slice(start=ORIGIN + PASO * 100)


def test_no_modifica_la_serie_original() -> None:
    serie = series_from_closes(ramp(10))
    serie.slice(start=ORIGIN + PASO * 5)
    assert len(serie) == 10


def test_dos_mitades_reconstruyen_el_total() -> None:
    """La propiedad que hace fiable la validacion fuera de muestra."""
    serie = series_from_closes(ramp(10))
    corte = ORIGIN + PASO * 6
    primera = serie.slice(end=corte)
    segunda = serie.slice(start=corte)
    assert len(primera) + len(segunda) == len(serie)


class TestEnLaCLI:
    def test_la_cli_acepta_un_subperiodo(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from invest_ll.cli import main

        filas = "".join(
            f"{(datetime(2025, 1, 1, tzinfo=UTC).replace(day=1) + PASO * i).isoformat()},"
            f"{100 + i},{101 + i},{99 + i},{100 + i},1000\n"
            for i in range(60)
        )
        ruta = tmp_path / "serie.csv"
        ruta.write_text("timestamp,open,high,low,close,volume\n" + filas, encoding="utf-8")

        codigo = main(
            [
                str(ruta),
                "--commission",
                "0",
                "--slippage",
                "0",
                "--from",
                "2025-01-10",
                "--to",
                "2025-02-10",
            ]
        )
        salida = capsys.readouterr().out
        assert codigo in (0, 3)
        assert "Resultado neto" in salida

    def test_un_subperiodo_sin_datos_falla_con_claridad(self, tmp_path: Path) -> None:
        from invest_ll.cli import main

        filas = "".join(
            f"{(datetime(2025, 1, 1, tzinfo=UTC) + PASO * i).isoformat()},"
            f"{100 + i},{101 + i},{99 + i},{100 + i},1000\n"
            for i in range(30)
        )
        ruta = tmp_path / "serie.csv"
        ruta.write_text("timestamp,open,high,low,close,volume\n" + filas, encoding="utf-8")

        codigo = main([str(ruta), "--commission", "0", "--slippage", "0", "--from", "2030-01-01"])
        assert codigo == 1
