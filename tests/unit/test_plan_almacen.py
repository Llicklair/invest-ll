"""El plan guardado: sus reglas y su fichero."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.estrategias.catalogo import ficha
from invest_ll.plan.almacen import (
    Parte,
    Plan,
    PlanIlegibleError,
    PlanInvalidoError,
    PlanStore,
    validar,
)

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

D = Decimal


def _parte(clave: str, inicial: str = "100", mensual: str = "10") -> Parte:
    return Parte(estrategia=clave, inicial=D(inicial), mensual=D(mensual))


def test_una_de_bolsa_y_una_de_cripto_vale() -> None:
    validar([_parte("bolsa-equilibrada"), _parte("btc-freno")], 1, ficha)


@pytest.mark.parametrize(
    ("partes", "motivo"),
    [
        (["bolsa-equilibrada", "bolsa-eeuu"], "como mucho una estrategia de bolsa"),
        (["btc-freno", "btc-mantener"], "como mucho una estrategia de cripto"),
        (["no-existe"], "no hay ninguna estrategia"),
        (["cripto-prerregistrada"], "es de Laboratorio"),
        (["bolsa-igual"], "es de Laboratorio"),
        (["cripto-rotacion"], "retirada"),
    ],
)
def test_lo_que_no_se_puede_poner_en_un_plan(partes: list[str], motivo: str) -> None:
    with pytest.raises(PlanInvalidoError, match=motivo):
        validar([_parte(p) for p in partes], 1, ficha)


def test_una_parte_sin_dinero_no_vale() -> None:
    with pytest.raises(PlanInvalidoError, match="no lleva dinero"):
        validar([_parte("btc-freno", "0", "0")], 1, ficha)


def test_el_dia_va_del_1_al_28() -> None:
    with pytest.raises(PlanInvalidoError, match="del 1 al 28"):
        validar([_parte("btc-freno")], 29, ficha)


def test_guardar_leer_y_borrar(tmp_path: Path) -> None:
    almacen = PlanStore(tmp_path / "plan")
    assert almacen.leer() is None
    momento = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    plan = Plan(
        partes=(_parte("bolsa-equilibrada", "5400.50", "180"), _parte("btc-freno", "600", "20")),
        dia_del_mes=5,
        creado=momento,
        actualizado=momento,
    )

    almacen.guardar(plan)

    assert almacen.leer() == plan
    assert almacen.borrar() is True
    assert almacen.borrar() is False
    assert almacen.leer() is None


def test_un_fichero_ilegible_se_dice(tmp_path: Path) -> None:
    almacen = PlanStore(tmp_path)
    almacen.path.write_text("{no es json", encoding="utf-8")
    with pytest.raises(PlanIlegibleError, match="no se puede leer"):
        almacen.leer()
