"""Si unos datos están al día: la bolsa no cotiza en fin de semana ni en sus festivos."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from invest_ll.fetch import al_dia

from ..fixtures.paneles_v2 import BOLSA, CRIPTO, HASTA, escribir_paneles

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path


@pytest.mark.parametrize(
    ("hoy", "ultima"),
    [
        (date(2026, 10, 19), date(2026, 10, 16)),  # lunes: la del viernes
        (date(2026, 10, 17), date(2026, 10, 16)),  # sábado: la del viernes
        (date(2026, 10, 16), date(2026, 10, 15)),  # viernes: la de hoy aún no se descarga
        (date(2026, 11, 27), date(2026, 11, 25)),  # tras Acción de Gracias (jueves 26)
    ],
)
def test_la_ultima_sesion_de_bolsa(hoy: date, ultima: date) -> None:
    assert al_dia.ultima_sesion_de_bolsa(hoy) == ultima


def test_sin_calendario_de_lunes_a_viernes(monkeypatch: pytest.MonkeyPatch) -> None:
    def sin_calendario(anio: int) -> object:
        raise RuntimeError(f"sin calendario para {anio}")

    monkeypatch.setattr(al_dia, "_calendario", sin_calendario)
    assert al_dia.ultima_sesion_de_bolsa(date(2026, 10, 19)) == date(2026, 10, 16)
    assert al_dia.ultima_sesion_de_bolsa(date(2026, 11, 27)) == date(2026, 11, 26), (
        "sin festivos: el error del lado prudente (pide un dato que no existe)"
    )


def test_cripto_cotiza_todos_los_dias() -> None:
    lunes = date(2026, 10, 19)
    assert al_dia.esta_al_dia(date(2026, 10, 18), lunes, cripto=True)
    assert not al_dia.esta_al_dia(date(2026, 10, 16), lunes, cripto=True)
    assert al_dia.esta_al_dia(date(2026, 10, 16), lunes, cripto=False), "el viernes vale"
    assert not al_dia.esta_al_dia(None, lunes, cripto=False)


def test_el_ultimo_dia_de_un_panel(tmp_path: Path) -> None:
    assert al_dia.ultimo_dia_del_panel(tmp_path / CRIPTO) is None
    escribir_paneles(tmp_path)
    assert al_dia.ultimo_dia_del_panel(tmp_path / CRIPTO) == HASTA
    assert al_dia.ultimo_dia_del_panel(tmp_path / BOLSA) == HASTA
