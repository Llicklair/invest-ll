"""Reintentos con espera creciente (T018).

La espera se **inyecta**. Dos razones: los tests no deben tardar de verdad, y la constitución exige
determinismo — una lógica que llama al reloj del sistema por su cuenta deja de ser comprobable.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from invest_ll.fetch.errors import ProviderUnavailableError, RateLimitError

INTENTOS_POR_DEFECTO = 3
ESPERA_BASE_SEGUNDOS = 1.0


def with_retries[T](
    operacion: Callable[[], T],
    *,
    attempts: int = INTENTOS_POR_DEFECTO,
    base_delay: float = ESPERA_BASE_SEGUNDOS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Ejecuta `operacion`, reintentando ante fallos recuperables.

    La espera crece (1s, 2s, 4s...): es lo que distingue reintentar de martillear. Repetir de
    inmediato ante un límite de tasa solo empeora la situación, porque el proveedor cuenta también
    las peticiones rechazadas.

    Los errores **no** recuperables —activo desconocido, intervalo no soportado— se propagan al
    instante: reintentar no va a hacer que el activo exista.
    """
    if attempts < 1:
        raise ValueError("attempts debe ser al menos 1")

    ultimo: Exception | None = None

    for intento in range(attempts):
        try:
            return operacion()
        except (RateLimitError, ProviderUnavailableError) as error:
            ultimo = error
            if intento < attempts - 1:
                sleep(base_delay * (2**intento))

    raise ProviderUnavailableError(
        f"el proveedor no respondió tras {attempts} intentos. El histórico local queda intacto. "
        f"Último fallo: {ultimo}"
    ) from ultimo
