"""T020 — contrato de Strategy y Signal (FR-017, FR-018).

Cualquier objeto con `decide` sirve. Es lo que permite medir con la misma vara una regla fija y
un modelo de IA.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from invest_ll.strategy.protocol import Signal, SignalKind, Strategy

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.view import MarketView


class EstrategiaSinHerencia:
    """No hereda de nada. Debe valer igual (tipado estructural)."""

    def decide(self, view: MarketView) -> Signal | None:
        return Signal(kind=SignalKind.ENTER_LONG)


class EnvoltorioDeModelo:
    """Simula el envoltorio de un modelo de IA: mismo contrato, mecanismo opaco."""

    def __init__(self, respuestas: list[Signal | None]) -> None:
        self._respuestas = respuestas
        self._i = 0

    def decide(self, view: MarketView) -> Signal | None:
        respuesta = self._respuestas[self._i % len(self._respuestas)]
        self._i += 1
        return respuesta


class NoEsEstrategia:
    pass


def test_objeto_con_decide_cumple_el_protocolo() -> None:
    assert isinstance(EstrategiaSinHerencia(), Strategy)


def test_envoltorio_de_modelo_cumple_el_protocolo() -> None:
    assert isinstance(EnvoltorioDeModelo([None]), Strategy)


def test_objeto_sin_decide_no_cumple() -> None:
    assert not isinstance(NoEsEstrategia(), Strategy)


class TestSignal:
    def test_senal_minima_solo_necesita_tipo(self) -> None:
        assert Signal(kind=SignalKind.ENTER_LONG).stop_loss is None

    def test_senal_es_inmutable(self) -> None:
        signal = Signal(kind=SignalKind.EXIT)
        with pytest.raises((AttributeError, TypeError)):
            signal.kind = SignalKind.ENTER_LONG  # type: ignore[misc]

    def test_no_lleva_cantidad_ni_precio(self) -> None:
        """El dimensionado es del motor (FR-027): si la señal lo llevara, dos estrategias
        dejarían de ser comparables."""
        campos = set(Signal.__dataclass_fields__)
        assert not campos & {"quantity", "size", "price", "amount"}

    def test_admite_niveles_de_proteccion(self) -> None:
        signal = Signal(kind=SignalKind.ENTER_LONG, stop_loss=90.0, take_profit=120.0)
        assert signal.stop_loss == 90.0

    @pytest.mark.parametrize("nivel", ["stop_loss", "take_profit"])
    def test_nivel_no_positivo_se_rechaza(self, nivel: str) -> None:
        with pytest.raises(ValueError, match="positivo"):
            Signal(kind=SignalKind.ENTER_LONG, **{nivel: -1.0})
