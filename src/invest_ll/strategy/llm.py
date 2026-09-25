"""El LLM como una estrategia más.

Implementa el mismo protocolo `RotationStrategy` que `RelativeMomentum`. `run_rotation()` no
distingue una de otra, y por eso los informes son comparables: mismas métricas, misma vara
(Principio V). Si el LLM elige mejor se verá en los números; si no, también.

**Dos decisiones de diseño que sostienen la honestidad del resultado:**

1. **Un fallo del proveedor detiene el backtest.** No se sustituye por "mantener lo que había".
   Esa sustitución convertiría un error en un resultado, y el informe describiría algo que no
   ocurrió — que es exactamente lo que la constitución prohíbe.

2. **Entre puntos de decisión se reutiliza la vigente** (FR-042). No es solo coste: consultar en
   cada vela con una serie diaria son miles de llamadas, y además convierte la estrategia en algo
   que ningún inversor real podría ejecutar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.decision.models import DecisionRequest
from invest_ll.decision.prompt import INSTRUCCIONES_VERSION, render_context, symbol_map

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from invest_ll.decision.models import Decision
    from invest_ll.decision.provider import DecisionProvider
    from invest_ll.engine.universe_view import UniverseView

# Lo que hay que decir siempre que se enseñe un resultado del LLM sobre el pasado. Vive junto a
# la estrategia para que la línea de comandos y el panel lo compartan sin importarse entre sí.
ADVERTENCIA_CONTAMINACION = """\
[!] Sobre el resultado del LLM: el modelo fue entrenado con datos que incluyen lo que paso
    despues del periodo simulado. Eso no se puede eliminar, solo acotar -- aqui se le ocultan
    fechas y nombres, pero un modelo que reconozca un patron sabe en que epoca esta.
    Un buen resultado del LLM sobre el pasado NO es evidencia de que funcione hacia adelante.
    La unica prueba limpia es registrar lo que estima y comparar con lo que pase despues.
"""

# Periodos entre decisiones. 21 ≈ un mes de sesiones bursátiles: el valor por defecto de FR-040.
CADA_MES = 21


class LLMStrategy:
    """Rota entre activos según lo que decida un LLM."""

    __slots__ = ("_decisions", "_every", "_last_choice", "_last_timestamp", "_provider", "_since")

    def __init__(
        self,
        provider: DecisionProvider,
        *,
        every_periods: int = CADA_MES,
    ) -> None:
        if every_periods < 1:
            raise ValueError("hay que decidir al menos cada periodo")
        self._provider = provider
        self._every = every_periods
        self._last_choice: str | None = None
        # Periodos desde la ultima decision. Se cuenta aqui en vez de mirar el cursor del motor:
        # el cursor es interno suyo, y la estrategia no tiene por que conocer sus tripas.
        self._since = 0
        self._decisions: list[Decision] = []
        # Ultima marca vista. Es la unica forma de detectar, sin cooperacion del motor, que esta
        # misma instancia se esta reutilizando en un segundo backtest (ver `choose`).
        self._last_timestamp: datetime | None = None

    @property
    def decisions(self) -> tuple[Decision, ...]:
        """Las decisiones tomadas, con su razonamiento (FR-012).

        Se conservan para poder auditar después por qué el sistema hizo lo que hizo. Un informe
        que dice "el LLM eligió oro" sin poder enseñar el porqué no es auditable.
        """
        return tuple(self._decisions)

    @property
    def decision_count(self) -> int:
        """Cuántas veces se consultó de verdad. Es lo que se paga."""
        return len(self._decisions)

    def choose(self, view: UniverseView) -> str | None:
        """El activo en el que estar tras el cierre de este periodo.

        Solo consulta en los puntos de decisión; el resto del tiempo devuelve lo vigente.
        """
        momento = self._moment(view)
        if self._last_timestamp is not None and momento <= self._last_timestamp:
            # Dentro de un mismo backtest el motor solo avanza en el tiempo (rotation.py recorre
            # `universe.timestamps` en orden). Una marca igual o anterior a la ultima vista solo
            # puede significar que esta instancia se esta reutilizando en un segundo backtest, y
            # entonces `_since`/`_last_choice`/`_decisions` seguirian siendo los del anterior: la
            # primera llamada no consultaria al proveedor y el rastro auditable (FR-012) del nuevo
            # informe describiria una decision que no ocurrio en el. No se puede corregir en
            # silencio (un `reset()` invitaria justo a este reuso); hay que fallar.
            raise RuntimeError(
                f"LLMStrategy ya se uso hasta {self._last_timestamp} y ahora recibe {momento} "
                "(igual o anterior): esta instancia se esta reutilizando en un segundo backtest. "
                "Construye una instancia nueva de LLMStrategy para cada backtest."
            )
        self._last_timestamp = momento

        if self._decisions and self._since < self._every:
            self._since += 1
            return self._last_choice

        decision = self._provider.decide(self._build_request(view))

        self._decisions.append(decision)
        self._last_choice = decision.chosen
        self._since = 1
        return self._last_choice

    def _build_request(self, view: UniverseView) -> DecisionRequest:
        return DecisionRequest(
            timestamp=self._moment(view),
            symbols=tuple(view.symbols),
            market_context=render_context(view),
            instructions_version=INSTRUCCIONES_VERSION,
            model=self._provider.model,
            # Sin esto la decision volveria con las etiquetas anonimas (A, B, C) y el motor
            # buscaria un activo llamado "C" que no existe.
            symbol_map=tuple(symbol_map(view).items()),
        )

    @staticmethod
    def _moment(view: UniverseView) -> datetime:
        return view.current_timestamp

    @staticmethod
    def translate(view: UniverseView) -> dict[str, str]:
        """Qué letra corresponde a cada activo. Expuesto para los informes."""
        return symbol_map(view)
