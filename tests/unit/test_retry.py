"""T012 — reintentos con espera creciente (FR-014, FR-015).

La suite no espera de verdad: la espera va inyectada y aquí se sustituye por un registrador.
"""

from __future__ import annotations

import pytest

from invest_ll.fetch.errors import (
    ProviderUnavailableError,
    RateLimitError,
    UnknownSymbolError,
)
from invest_ll.fetch.retry import with_retries


class Reloj:
    """Registra las esperas en lugar de dormir."""

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def test_una_operacion_correcta_no_reintenta() -> None:
    reloj = Reloj()
    assert with_retries(lambda: 42, sleep=reloj) == 42
    assert reloj.esperas == []


def test_reintenta_tras_un_limite_de_tasa() -> None:
    reloj = Reloj()
    intentos = {"n": 0}

    def operacion() -> str:
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise RateLimitError("límite")
        return "ok"

    assert with_retries(operacion, sleep=reloj) == "ok"
    assert intentos["n"] == 2
    assert len(reloj.esperas) == 1


def test_la_espera_crece() -> None:
    """Lo que distingue reintentar de martillear."""
    reloj = Reloj()

    def siempre_falla() -> None:
        raise RateLimitError("límite")

    with pytest.raises(ProviderUnavailableError):
        with_retries(siempre_falla, attempts=4, base_delay=1.0, sleep=reloj)

    assert reloj.esperas == [1.0, 2.0, 4.0]
    assert reloj.esperas == sorted(reloj.esperas)


def test_agotados_los_intentos_se_informa() -> None:
    reloj = Reloj()

    def siempre_falla() -> None:
        raise ProviderUnavailableError("caído")

    with pytest.raises(ProviderUnavailableError, match="3 intentos"):
        with_retries(siempre_falla, sleep=reloj)


def test_el_mensaje_dice_que_lo_local_queda_intacto() -> None:
    """FR-015: el operador debe saber que no ha perdido nada."""
    reloj = Reloj()

    def siempre_falla() -> None:
        raise ProviderUnavailableError("caído")

    with pytest.raises(ProviderUnavailableError, match="intacto"):
        with_retries(siempre_falla, sleep=reloj)


def test_los_errores_no_recuperables_no_se_reintentan() -> None:
    """Reintentar no va a hacer que el activo exista."""
    reloj = Reloj()
    intentos = {"n": 0}

    def activo_inexistente() -> None:
        intentos["n"] += 1
        raise UnknownSymbolError("no existe")

    with pytest.raises(UnknownSymbolError):
        with_retries(activo_inexistente, sleep=reloj)

    assert intentos["n"] == 1
    assert reloj.esperas == []


def test_attempts_invalido_se_rechaza() -> None:
    with pytest.raises(ValueError, match="al menos 1"):
        with_retries(lambda: 1, attempts=0)
