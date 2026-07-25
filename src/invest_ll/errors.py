"""Errores del dominio (T013).

Cada uno marca una frontera distinta: datos corruptos, intento de mirar al futuro, o una orden
que no cabe en la caja.
"""

from __future__ import annotations


class InvestLLError(Exception):
    """Raíz de los errores del proyecto."""


class LookAheadError(InvestLLError):
    """Una estrategia intentó acceder a datos posteriores al instante simulado.

    Principio II de la constitución. **Nunca se captura dentro del motor para continuar**: un
    backtest contaminado no produce un resultado degradado, no produce resultado. Un número
    obtenido mirando el futuro es peor que ningún número, porque parece válido.
    """


class InvalidSeriesError(InvestLLError):
    """La serie histórica no supera la validación (FR-015, FR-034)."""


class InsufficientCapitalError(InvestLLError):
    """La orden excede el capital disponible (FR-010).

    A diferencia de los anteriores, es recuperable: el motor lo registra como orden rechazada y
    la simulación continúa, igual que ocurriría en un mercado real.
    """
