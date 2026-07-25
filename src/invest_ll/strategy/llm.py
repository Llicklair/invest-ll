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

# Periodos entre decisiones. 21 ≈ un mes de sesiones bursátiles: el valor por defecto de FR-040.
CADA_MES = 21


class LLMStrategy:
    """Rota entre activos según lo que decida un LLM."""

    __slots__ = ("_decisions", "_every", "_last_choice", "_provider", "_since")

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
