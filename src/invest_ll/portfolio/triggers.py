"""Triggers de retirada: reglas armadas sobre tu cartera real que PROPONEN la venta. Nunca la envían.

La diferencia con los bots reales (Freqtrade, 3Commas), dicha de frente: allí el bot, una vez
armado, opera solo; aquí, cuando una regla se cruza, produce **la orden de venta exacta** —símbolo,
cantidad y el comando `invest-ll-execute` completo— para que la confirmes tú. Un paso del humano,
no cero (Principio I).

Este módulo **no puede importar nada de `live/`** (broker, ccxt, modo real): la distancia entre
"propone" y "dispara" es exactamente un import, y un test lo vigila por AST.

El kill switch copia la distinción universal de los bots —dejar de entrar no es liquidarlo todo— y
les quita lo peligroso: la pausa solo frena las propuestas de entrada, y liquidar produce una orden
por posición para confirmar una a una.

Lo que no promete: el stop-loss automático, medido sobre 21 años y 84 decisiones reales, no mejoró
nada (docs/experimento-stop-loss.md). Estos triggers son límites visibles que decidiste tú, no una
estrategia de salida superior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from invest_ll.errors import InvestLLError
from invest_ll.fetch.available import RAIZ_DATOS
from invest_ll.llano import fecha_corta
from invest_ll.portfolio.models import CERO, UNO, como_texto
from invest_ll.portfolio.quotes import maximo_y_ultimo, ultimo_cierre
from invest_ll.portfolio.store import RAIZ, CorruptLedgerError, anadir_linea, leer_jsonl

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from invest_ll.portfolio.models import OpenPosition

FICHERO = "triggers.jsonl"
PREFIJO_ID = "trg-"


class TriggerError(InvestLLError):
    """Una operación sobre los triggers o la pausa que no se acepta."""


class TriggerRule(Enum):
    """Pocas reglas y legibles, antes que muchas y opacas."""

    LOSS_FROM_ENTRY = "loss-from-entry"
    """Perder más del umbral desde TU entrada (coste medio con comisiones)."""
    DROP_FROM_PEAK = "drop-from-peak"
    """Caer más del umbral desde el cierre máximo del histórico descargado."""


@dataclass(frozen=True, slots=True)
class Trigger:
    """Una regla armada sobre un activo. El umbral es una fracción: 0.15 = 15%."""

    trigger_id: str
    symbol: str
    rule: TriggerRule
    threshold: Decimal
    armed_at: datetime

    def __post_init__(self) -> None:
        if not self.trigger_id.strip():
            raise ValueError("un trigger necesita identificador")
        if not self.symbol.strip():
            raise ValueError("un trigger necesita simbolo")
        if not self.threshold.is_finite() or not CERO < self.threshold < UNO:
            raise ValueError(
                f"el umbral es una fraccion entre 0 y 1 (0.15 = 15%); recibido {self.threshold}"
            )
        if self.armed_at.tzinfo is None:
            raise ValueError("la fecha de armado necesita zona horaria")

    def describe(self) -> str:
        porcentaje = como_texto(self.threshold * 100)
        if self.rule is TriggerRule.LOSS_FROM_ENTRY:
            condicion = (
                f"pierde mas del {porcentaje}% desde tu entrada (coste medio con comisiones)"
            )
        else:
            condicion = f"cae mas del {porcentaje}% desde el cierre maximo de los datos descargados"
        return f"{self.symbol}: proponer la venta si {condicion}"


@dataclass(frozen=True, slots=True)
class FiredTrigger:
    """Un trigger que ha saltado: la venta PROPUESTA, en texto para leer. No se ha enviado nada."""

    trigger: Trigger
    measured: Decimal
    """La variación medida, como fracción (negativa al saltar: -0.2 = -20%)."""
    reference: Decimal
    """Contra qué se midió: el coste medio de entrada o el cierre máximo."""
    last_price: Decimal
    quantity: Decimal
    """Toda la posición: el trigger propone salir de ella entera."""

    @property
    def command(self) -> str:
        return comando_de_venta(self.trigger.symbol, self.quantity)

    def render(self) -> str:
        referencia = (
            "tu coste medio" if self.trigger.rule is TriggerRule.LOSS_FROM_ENTRY else "el maximo"
        )
        variacion = f"{self.measured * 100:+.1f}%"
        umbral = como_texto(self.trigger.threshold * 100)
        return "\n".join(
            (
                f"[{self.trigger.trigger_id}] {self.trigger.symbol}: {variacion} desde "
                f"{referencia} ({como_texto(self.reference)} -> {como_texto(self.last_price)}), "
                f"umbral -{umbral}%.",
                f"  Propuesta: vender TODA la posicion, {como_texto(self.quantity)} "
                f"{self.trigger.symbol}. Nada se ha enviado.",
                "  Si decides salir, ejecutalo tu (te pedira confirmar la cantidad):",
                f"    {self.command}",
            )
        )


def evaluate_trigger(
    trigger: Trigger,
    position: OpenPosition | None,
    *,
    last_price: Decimal | None,
    peak: Decimal | None,
) -> FiredTrigger | None:
    """Evalúa una regla. `None` si no salta — o si no hay con qué medir.

    Sin posición, sin precio o (para la caída desde máximo) sin pico, no se inventa nada: no
    salta. Distinguir "no saltó" de "no se pudo evaluar" es cosa de quien llama, que sabe cuál
    de los datos faltaba.
    """
    if position is None or last_price is None:
        return None
    if position.symbol != trigger.symbol:
        raise ValueError(
            f"el trigger {trigger.trigger_id} es de {trigger.symbol}, no de {position.symbol}"
        )

    if trigger.rule is TriggerRule.LOSS_FROM_ENTRY:
        if position.cost <= 0:
            return None
        referencia = position.avg_cost
        medido = (position.value_at(last_price) - position.cost) / position.cost
    else:
        if peak is None or peak <= 0:
            return None
        referencia = peak
        medido = last_price / peak - 1

    if medido > -trigger.threshold:
        return None
    return FiredTrigger(
        trigger=trigger,
        measured=medido,
        reference=referencia,
        last_price=last_price,
        quantity=position.quantity,
    )


def comando_de_venta(symbol: str, quantity: Decimal) -> str:
    """La venta, como comando de `invest-ll-execute`: la única puerta al dinero."""
    return (
        f"uv run invest-ll-execute --symbol {symbol} --side sell --quantity {como_texto(quantity)}"
    )


def liquidation_commands(positions: Iterable[OpenPosition]) -> list[str]:
    """Nivel 2 del kill switch: una orden de venta por posición, con su cantidad exacta.

    Son comandos para leer y confirmar UNO A UNO. Liquidarlo todo con un solo enter sería la clase
    de acción irreversible que el Principio I prohíbe.
    """
    return [comando_de_venta(p.symbol, p.quantity) for p in positions]


@dataclass(frozen=True, slots=True)
class TriggerCheck:
    """Todas las reglas armadas, evaluadas contra la cartera real. Nada se ha enviado."""

    fired: tuple[tuple[FiredTrigger, datetime], ...]
    """Cada disparo con la fecha del precio usado: con historicos parados, sin ella pareceria
    de hoy."""
    not_evaluated: tuple[str, ...]
    """Las que no se pudieron mirar, con el porque. No poder mirar NO es 'todo en orden'."""
    armed: int


def check_triggers(
    triggers: Sequence[Trigger],
    positions: Iterable[OpenPosition],
    *,
    data_root: Path = RAIZ_DATOS,
) -> TriggerCheck:
    """Evalúa cada regla armada con el último cierre descargado de su activo.

    Vive aquí y no en la línea de comandos para que el terminal y el panel cuenten lo mismo: una
    regla sin posición abierta o sin datos se declara sin evaluar, nunca se da por no saltada.
    """
    abiertas = {p.symbol: p for p in positions}
    disparados: list[tuple[FiredTrigger, datetime]] = []
    sin_evaluar: list[str] = []

    for trigger in triggers:
        posicion = abiertas.get(trigger.symbol)
        if posicion is None:
            sin_evaluar.append(
                f"{trigger.trigger_id}: no hay posicion abierta de {trigger.symbol} en el ledger"
            )
            continue
        cierre = ultimo_cierre(trigger.symbol, data_root)
        if cierre is None:
            sin_evaluar.append(f"{trigger.trigger_id}: sin datos descargados de {trigger.symbol}")
            continue
        precio, fecha = cierre
        pico = maximo_y_ultimo(trigger.symbol, data_root)
        resultado = evaluate_trigger(
            trigger, posicion, last_price=precio, peak=pico[0] if pico else None
        )
        if resultado is not None:
            disparados.append((resultado, fecha))

    return TriggerCheck(
        fired=tuple(disparados), not_evaluated=tuple(sin_evaluar), armed=len(triggers)
    )


@dataclass(frozen=True, slots=True)
class _Estado:
    """Lo que resulta de reproducir el registro de eventos."""

    armados: tuple[Trigger, ...]
    ids_usados: frozenset[str]
    pausa: str | None


class TriggerStore:
    """Triggers armados y la pausa, en un registro de eventos que solo añade.

    Armar, desarmar, pausar y reanudar son eventos; el estado actual se reproduce leyéndolos. Así
    queda constancia de cuándo se desarmó una regla o se retiró una pausa, y un id ya usado no se
    reutiliza nunca. Comparte carpeta con el ledger de cartera (`portfolio/`).
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path = RAIZ) -> None:
        self._root = root

    @property
    def path(self) -> Path:
        return self._root / FICHERO

    def arm(self, trigger: Trigger) -> None:
        if trigger.trigger_id in self._estado().ids_usados:
            raise TriggerError(
                f"el id {trigger.trigger_id} ya se uso: los ids no se reutilizan. "
                "Pide uno nuevo con next_id()."
            )
        anadir_linea(
            self.path,
            {
                "event": "arm",
                "trigger_id": trigger.trigger_id,
                "symbol": trigger.symbol,
                "rule": trigger.rule.value,
                "threshold": str(trigger.threshold),
                "armed_at": trigger.armed_at.isoformat(),
            },
        )

    def disarm(self, trigger_id: str) -> bool:
        """Desarma. `False` si no había ninguno armado con ese id: eso no es un éxito."""
        if all(t.trigger_id != trigger_id for t in self._estado().armados):
            return False
        anadir_linea(
            self.path,
            {"event": "disarm", "trigger_id": trigger_id, "at": datetime.now(UTC).isoformat()},
        )
        return True

    def triggers(self) -> list[Trigger]:
        """Los armados ahora, en el orden en que se armaron."""
        return list(self._estado().armados)

    def next_id(self) -> str:
        """Un id que no se ha usado nunca, ni siquiera por un trigger ya desarmado."""
        usados = self._estado().ids_usados
        numeros = [
            int(i.removeprefix(PREFIJO_ID))
            for i in usados
            if i.startswith(PREFIJO_ID) and i.removeprefix(PREFIJO_ID).isdigit()
        ]
        return f"{PREFIJO_ID}{max([len(usados), *numeros]) + 1}"

    def halt(self, *, reason: str, at: datetime) -> None:
        """Nivel 1 del kill switch: dejar de proponer entradas nuevas. El motivo es obligatorio.

        Las posiciones abiertas no se tocan. Una pausa sin motivo no se acepta: dentro de un mes
        nadie sabría por qué está ahí, ni si ya se puede retirar.
        """
        motivo = reason.strip()
        if not motivo:
            raise TriggerError("una pausa necesita motivo: escribe por que dejas de entrar")
        if at.tzinfo is None:
            raise TriggerError("la fecha de la pausa necesita zona horaria")
        anadir_linea(self.path, {"event": "halt", "reason": motivo, "at": at.isoformat()})

    def resume(self) -> bool:
        """Retira la pausa. `False` si no había ninguna: reanudar sin pausa no es un éxito."""
        if self._estado().pausa is None:
            return False
        anadir_linea(self.path, {"event": "resume", "at": datetime.now(UTC).isoformat()})
        return True

    def halted(self) -> str | None:
        """El motivo de la pausa activa, con su fecha. `None` si no hay pausa."""
        return self._estado().pausa

    def _estado(self) -> _Estado:
        armados: dict[str, Trigger] = {}
        usados: set[str] = set()
        pausa: str | None = None
        for numero, evento in leer_jsonl(self.path):
            try:
                tipo = evento["event"]
                if tipo == "arm":
                    trigger = _leer_trigger(evento)
                    armados[trigger.trigger_id] = trigger
                    usados.add(trigger.trigger_id)
                elif tipo == "disarm":
                    armados.pop(str(evento["trigger_id"]), None)
                elif tipo == "halt":
                    desde = datetime.fromisoformat(evento["at"]).date()
                    pausa = f"{evento['reason']} (desde el {fecha_corta(desde)})"
                elif tipo == "resume":
                    pausa = None
                else:
                    raise ValueError(f"evento desconocido {tipo!r}")
            except (KeyError, ValueError, TypeError, ArithmeticError) as error:
                # Saltarse una linea podria desarmar una regla o levantar una pausa en silencio.
                raise CorruptLedgerError(
                    f"{self.path}, linea {numero}: evento ilegible ({error}). Revisalo a mano."
                ) from error
        return _Estado(armados=tuple(armados.values()), ids_usados=frozenset(usados), pausa=pausa)


def _leer_trigger(c: dict[str, Any]) -> Trigger:
    return Trigger(
        trigger_id=str(c["trigger_id"]),
        symbol=str(c["symbol"]),
        rule=TriggerRule(c["rule"]),
        threshold=Decimal(c["threshold"]),
        armed_at=datetime.fromisoformat(c["armed_at"]),
    )
