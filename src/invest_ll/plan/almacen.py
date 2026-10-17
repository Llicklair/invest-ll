"""El plan guardado: qué estrategias, cuánto al empezar, cuánto cada mes y qué día.

Vive en `plan/plan.json`, fuera de git (como `portfolio/` o `ledger/`): son datos tuyos, no
código. Se reescribe entero de forma atómica (temporal + reemplazo): una interrupción no deja un
plan a medias.

Las reglas que no se negocian, comprobadas al guardar (`validar`):

- Como mucho una estrategia de bolsa y una de cripto: dos de bolsa a la vez repartirían la misma
  aportación con dos criterios distintos, y "qué toca hoy" no sabría a cuál hacer caso.
- Solo estrategias del camino principal: las de Laboratorio (y la retirada) no se ponen en un plan
  con dinero.

Al reemplazar un plan se conserva su fecha de creación: es desde cuándo se cuentan las
aportaciones vencidas. Borrarlo y crear otro empieza la cuenta de cero.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from invest_ll.estrategias.catalogo import Ficha

RAIZ: Final = Path("plan")
FICHERO: Final = "plan.json"
DIA_MAXIMO: Final = 28


class PlanInvalidoError(InvestLLError):
    """El plan pedido rompe alguna de las reglas."""


class PlanIlegibleError(InvestLLError):
    """`plan/plan.json` existe pero no se puede leer. No se ignora: se dice."""


@dataclass(frozen=True, slots=True)
class Parte:
    estrategia: str
    inicial: Decimal
    mensual: Decimal


@dataclass(frozen=True, slots=True)
class Plan:
    partes: tuple[Parte, ...]
    dia_del_mes: int
    creado: datetime
    actualizado: datetime

    def parte_de(self, mercado: str, fichas: Callable[[str], Ficha | None]) -> Parte | None:
        """La parte de ese mercado ('bolsa' o 'cripto'), si el plan la tiene."""
        for parte in self.partes:
            encontrada = fichas(parte.estrategia)
            if encontrada is not None and encontrada.mercado == mercado:
                return parte
        return None


def validar(
    partes: Sequence[Parte], dia_del_mes: int, fichas: Callable[[str], Ficha | None]
) -> None:
    """Las reglas del plan. `PlanInvalidoError` con el motivo en llano si alguna falla."""
    if not partes:
        raise PlanInvalidoError("un plan necesita al menos una estrategia")
    if not 1 <= dia_del_mes <= DIA_MAXIMO:
        raise PlanInvalidoError(
            f"el día de aportación va del 1 al {DIA_MAXIMO}: así existe en todos los meses"
        )
    vistos: dict[str, str] = {}
    for parte in partes:
        encontrada = fichas(parte.estrategia)
        if encontrada is None:
            raise PlanInvalidoError(f"no hay ninguna estrategia {parte.estrategia!r}")
        if encontrada.retirada:
            raise PlanInvalidoError(
                f"{encontrada.nombre} está retirada: no se puede poner en un plan"
            )
        if encontrada.laboratorio:
            raise PlanInvalidoError(
                f"{encontrada.nombre} es de Laboratorio: solo se estudia, no se pone en un plan"
            )
        if encontrada.mercado in vistos:
            raise PlanInvalidoError(
                f"un plan lleva como mucho una estrategia de {encontrada.mercado}: "
                f"{vistos[encontrada.mercado]} y {encontrada.nombre} lo son las dos"
            )
        vistos[encontrada.mercado] = encontrada.nombre
        if parte.inicial < 0 or parte.mensual < 0:
            raise PlanInvalidoError("los importes del plan no pueden ser negativos")
        if parte.inicial == 0 and parte.mensual == 0:
            raise PlanInvalidoError(
                f"{encontrada.nombre} no lleva dinero: pon un inicial o una aportación mensual"
            )


class PlanStore:
    """El plan en disco: leer, guardar (reemplaza) y borrar."""

    __slots__ = ("_raiz",)

    def __init__(self, raiz: Path = RAIZ) -> None:
        self._raiz = raiz

    @property
    def path(self) -> Path:
        return self._raiz / FICHERO

    def leer(self) -> Plan | None:
        if not self.path.exists():
            return None
        try:
            crudo = json.loads(self.path.read_text(encoding="utf-8"))
            return _leer(cast("dict[str, Any]", crudo))
        except (ValueError, KeyError, TypeError, InvalidOperation) as error:
            raise PlanIlegibleError(
                f"{self.path} no se puede leer ({error}). Revísalo o bórralo y vuelve a crear el "
                "plan."
            ) from error

    def guardar(self, plan: Plan) -> None:
        self._raiz.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._raiz, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(json.dumps(_escribir(plan), ensure_ascii=False, indent=2) + "\n")
            temporal = Path(tmp.name)
        os.replace(temporal, self.path)  # noqa: PTH105

    def borrar(self) -> bool:
        """Borra el plan. `False` si no había ninguno."""
        if not self.path.exists():
            return False
        self.path.unlink()
        return True


def _escribir(plan: Plan) -> dict[str, Any]:
    return {
        "partes": [
            {"estrategia": p.estrategia, "inicial": str(p.inicial), "mensual": str(p.mensual)}
            for p in plan.partes
        ],
        "dia_del_mes": plan.dia_del_mes,
        "creado": plan.creado.isoformat(),
        "actualizado": plan.actualizado.isoformat(),
    }


def _leer(c: dict[str, Any]) -> Plan:
    partes = cast("list[dict[str, Any]]", c["partes"])
    creado = datetime.fromisoformat(str(c["creado"]))
    actualizado = datetime.fromisoformat(str(c["actualizado"]))
    if creado.tzinfo is None or actualizado.tzinfo is None:
        raise ValueError("las fechas del plan necesitan zona horaria")
    return Plan(
        partes=tuple(
            Parte(
                estrategia=str(p["estrategia"]),
                inicial=Decimal(str(p["inicial"])),
                mensual=Decimal(str(p["mensual"])),
            )
            for p in partes
        ),
        dia_del_mes=int(c["dia_del_mes"]),
        creado=creado,
        actualizado=actualizado,
    )
