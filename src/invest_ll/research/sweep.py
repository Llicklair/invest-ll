"""Barrido sistemático de estrategias, con corrección por número de pruebas.

Probar muchas estrategias y quedarse con las que funcionaron es el método más fiable que existe
para encontrar cosas que no funcionan. Este módulo permite hacerlo igualmente — pero contando
cuántas se probaron, que es lo que convierte la búsqueda en algo interpretable.

**La aritmética que nadie quiere hacer.** Si una estrategia no tiene ninguna ventaja real, su
exceso sobre no hacer nada es esencialmente una moneda al aire: la mitad de las veces sale
positivo. Así que al probar 20 configuraciones sin ventaja, lo *esperable* es que unas 10 salgan
positivas en validación. Encontrar "algunas que funcionan" está garantizado de antemano.

Lo que sí significa algo es que salgan **muchas más** de la mitad. `probabilidad_por_azar` calcula
exactamente eso: qué probabilidad había de obtener este resultado o mejor si ninguna estrategia
tuviera ventaja. Si esa probabilidad es alta, el barrido no ha encontrado nada por mucho que
algunas cifras sean bonitas.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import comb
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.report.report import BacktestReport

# Por debajo de esta probabilidad, el resultado del barrido es difícil de explicar solo por azar.
# No es una frontera mágica: es el convenio habitual, y sigue sin demostrar que la estrategia
# vaya a funcionar en el futuro.
UMBRAL_SIGNIFICANCIA = 0.05


@dataclass(frozen=True, slots=True)
class SweepEntry:
    """Una configuración probada, con su resultado dentro y fuera de muestra."""

    label: str
    train_excess: Decimal
    train_trades: int
    validation_excess: Decimal
    validation_trades: int

    @property
    def survives(self) -> bool:
        """Positiva en el periodo que no se uso para elegirla."""
        return self.validation_excess > 0

    @property
    def looked_good(self) -> bool:
        return self.train_excess > 0

    @property
    def promise_kept(self) -> bool:
        """Prometía en entrenamiento y cumplió en validación.

        Es lo único que se parece a evidencia. Una configuración que va mal en entrenamiento y
        bien en validación no la habrías elegido nunca: su acierto no cuenta.
        """
        return self.looked_good and self.survives


@dataclass(frozen=True, slots=True)
class SweepSummary:
    """Resultado del barrido completo, con la corrección por número de pruebas."""

    entries: tuple[SweepEntry, ...]

    @property
    def tested(self) -> int:
        return len(self.entries)

    @property
    def survivors(self) -> tuple[SweepEntry, ...]:
        return tuple(e for e in self.entries if e.survives)

    @property
    def promises_kept(self) -> tuple[SweepEntry, ...]:
        return tuple(e for e in self.entries if e.promise_kept)

    @property
    def expected_by_chance(self) -> float:
        """Cuántas esperarías que sobrevivieran si ninguna tuviera ventaja."""
        return self.tested / 2

    @property
    def chance_probability(self) -> float:
        """Probabilidad de obtener estos supervivientes o más solo por azar."""
        return probabilidad_por_azar(len(self.survivors), self.tested)

    @property
    def beats_chance(self) -> bool:
        return self.tested > 0 and self.chance_probability < UMBRAL_SIGNIFICANCIA

    @property
    def worse_than_chance_probability(self) -> float:
        """Probabilidad de obtener TAN POCOS supervivientes o menos solo por azar."""
        return probabilidad_cola_inferior(len(self.survivors), self.tested)

    @property
    def systematically_worse(self) -> bool:
        """Muchos menos supervivientes de los que explicaria el azar.

        Es un hallazgo distinto de "no hay ventaja", y mas fuerte. Si de 40 pruebas ninguna
        sobrevive cuando esperarias 20, estas estrategias no son neutras: pierden de forma
        consistente. La explicacion habitual es la friccion -- cada operacion paga comisiones y
        ninguna aporta lo suficiente para cubrirlas.

        La primera version de este modulo solo miraba el extremo bueno y se habria callado ante
        el resultado mas informativo del barrido.
        """
        return self.tested > 0 and self.worse_than_chance_probability < UMBRAL_SIGNIFICANCIA

    @property
    def best_by_training(self) -> SweepEntry | None:
        """La que habrías elegido mirando solo el entrenamiento.

        Es la única elección honesta: en la vida real no puedes ver la validación antes de
        decidir. Su resultado en validación es la prueba de verdad.
        """
        return max(self.entries, key=lambda e: e.train_excess) if self.entries else None

    def render(self) -> str:
        if not self.entries:
            return "Barrido sin configuraciones que probar."

        lineas = [
            "Barrido de estrategias",
            "=" * 72,
            f"{'configuracion':<28}{'ENTREN.':>14}{'ops':>5}{'VALIDACION':>16}{'ops':>5}",
            "-" * 72,
        ]
        for e in sorted(self.entries, key=lambda x: x.train_excess, reverse=True):
            marca = " *" if e.promise_kept else "  "
            lineas.append(
                f"{e.label:<28}{e.train_excess:>14,.0f}{e.train_trades:>5}"
                f"{e.validation_excess:>16,.0f}{e.validation_trades:>5}{marca}"
            )

        lineas += [
            "-" * 72,
            f"  Probadas                  {self.tested}",
            f"  Positivas en validacion   {len(self.survivors)}",
            f"  Esperables por azar       {self.expected_by_chance:.1f}",
            f"  Probabilidad de que sea casualidad  {self.chance_probability:.1%}",
        ]

        if self.beats_chance:
            lineas += [
                "",
                "  Mas supervivientes de los que explica el azar. Sigue sin ser garantia de",
                "  nada de cara al futuro, pero merece mirarse con atencion.",
            ]
        elif self.systematically_worse:
            lineas += [
                "",
                f"  [!] Solo {len(self.survivors)} de {self.tested} positivas cuando el azar daria",
                f"      {self.expected_by_chance:.1f}. Eso no es ausencia de ventaja: es DESVENTAJA",
                "      sistematica. Estas estrategias no empatan con comprar y mantener, pierden",
                "      contra ella de forma consistente, y la explicacion habitual es la friccion:",
                "      cada operacion paga y ninguna aporta lo suficiente para cubrirlo.",
            ]
        else:
            lineas += [
                "",
                f"  [!] {len(self.survivors)} de {self.tested} positivas es lo que saldria tirando",
                f"      monedas al aire ({self.expected_by_chance:.1f} esperables). Este barrido NO",
                "      ha encontrado ninguna ventaja: encontrar 'algunas que funcionan' estaba",
                "      garantizado antes de empezar.",
            ]

        mejor = self.best_by_training
        if mejor is not None:
            veredicto = "cumplio" if mejor.survives else "NO cumplio"
            lineas += [
                "",
                f"  La que habrias elegido: {mejor.label}",
                f"    prometia {mejor.train_excess:,.0f} en entrenamiento y {veredicto}:",
                f"    {mejor.validation_excess:,.0f} en validacion.",
            ]

        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()


def probabilidad_por_azar(exitos: int, pruebas: int) -> float:
    """Probabilidad de obtener `exitos` o más de `pruebas`, si cada una fuera una moneda al aire.

    Es la corrección por comparaciones múltiples en su forma más simple. Sin ella, "he probado
    cincuenta estrategias y veinticinco funcionan" suena a hallazgo cuando es exactamente lo que
    predice el azar.
    """
    if pruebas <= 0:
        return 1.0
    if exitos <= 0:
        return 1.0

    total = 2**pruebas
    acumulado = sum(comb(pruebas, k) for k in range(exitos, pruebas + 1))
    return acumulado / total


def probabilidad_cola_inferior(exitos: int, pruebas: int) -> float:
    """Probabilidad de obtener `exitos` o MENOS de `pruebas`, si fueran monedas al aire.

    La cola opuesta a `probabilidad_por_azar`. Existe porque un barrido puede fallar de dos
    formas y solo una es "no encontre nada": obtener muchisimos menos aciertos de los esperados
    significa que las estrategias probadas son peores que no hacer nada, y eso es informacion.
    """
    if pruebas <= 0:
        return 1.0
    if exitos >= pruebas:
        return 1.0

    total = 2**pruebas
    acumulado = sum(comb(pruebas, k) for k in range(exitos + 1))
    return acumulado / total


def run_sweep(
    configuraciones: Sequence[
        tuple[str, Callable[[], BacktestReport], Callable[[], BacktestReport]]
    ],
) -> SweepSummary:
    """Ejecuta cada configuración en entrenamiento y validación.

    Recibe pares de funciones ya preparadas en lugar de construir los backtests aquí: así el
    barrido sirve igual para estrategias de un activo, para rotación entre varios o para lo que
    venga después, sin conocer ninguna de las tres.
    """
    entradas: list[SweepEntry] = []
    for etiqueta, entrenar, validar in configuraciones:
        train = entrenar()
        val = validar()
        entradas.append(
            SweepEntry(
                label=etiqueta,
                train_excess=train.excess_return,
                train_trades=train.trade_count,
                validation_excess=val.excess_return,
                validation_trades=val.trade_count,
            )
        )
    return SweepSummary(entries=tuple(entradas))
