"""Entidades de la capa de decisión (T004, T006).

Una decisión inválida tiene que fallar al construirse, no más tarde. Si un peso de 1.5 llega al
motor, lo que se rompe es una simulación con cifras de dinero — y puede que nadie lo note.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from invest_ll.decision.models import (
    Action,
    AssetDecision,
    Decision,
    DecisionRequest,
)

D = Decimal
CUANDO = datetime(2020, 6, 1, tzinfo=UTC)


def decidir(
    symbol: str = "AAPL", *, peso: str = "0.5", accion: Action = Action.ENTER
) -> AssetDecision:
    return AssetDecision(symbol=symbol, action=accion, weight=D(peso), reasoning="porque si")


class TestAssetDecision:
    def test_una_decision_valida_se_construye(self) -> None:
        d = decidir()
        assert d.symbol == "AAPL"
        assert d.weight == D("0.5")

    @pytest.mark.parametrize("peso", ["-0.1", "1.5"])
    def test_peso_fuera_de_rango_se_rechaza(self, peso: str) -> None:
        with pytest.raises(ValueError, match="entre 0 y 1"):
            decidir(peso=peso)

    def test_entrar_con_peso_cero_no_tiene_sentido(self) -> None:
        with pytest.raises(ValueError, match="peso positivo"):
            decidir(peso="0", accion=Action.ENTER)

    def test_salir_con_peso_cero_si_lo_tiene(self) -> None:
        assert decidir(peso="0", accion=Action.EXIT).weight == 0

    def test_sin_razonamiento_no_se_construye(self) -> None:
        """FR-012: el razonamiento es obligatorio, no decorativo."""
        with pytest.raises(ValueError, match="razonamiento"):
            AssetDecision(symbol="AAPL", action=Action.ENTER, weight=D("0.5"), reasoning="  ")

    def test_sin_simbolo_no_se_construye(self) -> None:
        with pytest.raises(ValueError, match="simbolo"):
            AssetDecision(symbol="", action=Action.EXIT, weight=D(0), reasoning="x")

    def test_es_inmutable(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            decidir().weight = D("0.9")  # type: ignore[misc]


class TestDecision:
    def test_una_decision_completa_se_construye(self) -> None:
        d = Decision(
            timestamp=CUANDO,
            assets=(decidir("AAPL", peso="0.4"), decidir("GLD", peso="0.3")),
            summary="reparto",
            model="claude-opus-5",
        )
        assert len(d.assets) == 2

    def test_simbolos_repetidos_se_rechazan(self) -> None:
        with pytest.raises(ValueError, match="repetid"):
            Decision(
                timestamp=CUANDO,
                assets=(decidir("AAPL", peso="0.3"), decidir("AAPL", peso="0.3")),
                summary="x",
                model="m",
            )

    def test_la_suma_de_pesos_no_puede_pasar_de_uno(self) -> None:
        """Sin apalancamiento en v1. Una respuesta que lo incumpla es un fallo, no algo a recortar."""
        with pytest.raises(ValueError, match="suma de pesos"):
            Decision(
                timestamp=CUANDO,
                assets=(decidir("AAPL", peso="0.7"), decidir("GLD", peso="0.6")),
                summary="x",
                model="m",
            )

    def test_la_suma_exacta_de_uno_se_acepta(self) -> None:
        d = Decision(
            timestamp=CUANDO,
            assets=(decidir("AAPL", peso="0.6"), decidir("GLD", peso="0.4")),
            summary="x",
            model="m",
        )
        assert d.total_weight == D(1)

    def test_una_fecha_sin_zona_horaria_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            Decision(
                timestamp=datetime(2020, 6, 1),
                assets=(),
                summary="x",
                model="m",
            )

    def test_sin_modelo_no_se_construye(self) -> None:
        """FR-045: hay que poder saber quien produjo cada decision."""
        with pytest.raises(ValueError, match="modelo"):
            Decision(timestamp=CUANDO, assets=(), summary="x", model="")

    def test_quedarse_fuera_es_una_decision_valida(self) -> None:
        d = Decision(timestamp=CUANDO, assets=(), summary="todo cae", model="m")
        assert d.total_weight == 0
        assert d.chosen is None

    def test_el_elegido_es_el_de_mayor_peso(self) -> None:
        d = Decision(
            timestamp=CUANDO,
            assets=(decidir("AAPL", peso="0.3"), decidir("GLD", peso="0.6")),
            summary="x",
            model="m",
        )
        assert d.chosen == "GLD"

    def test_solo_cuentan_los_que_entran(self) -> None:
        d = Decision(
            timestamp=CUANDO,
            assets=(
                decidir("AAPL", peso="0.9", accion=Action.EXIT),
                decidir("GLD", peso="0.2", accion=Action.ENTER),
            ),
            summary="x",
            model="m",
        )
        assert d.chosen == "GLD"


class TestDecisionRequest:
    def peticion(self, **kwargs: object) -> DecisionRequest:
        base: dict[str, object] = {
            "timestamp": CUANDO,
            "symbols": ("AAPL", "GLD"),
            "market_context": "precios...",
            "instructions_version": "v1",
            "model": "claude-opus-5",
        }
        base.update(kwargs)
        return DecisionRequest(**base)  # type: ignore[arg-type]

    def test_la_misma_peticion_da_la_misma_clave(self) -> None:
        assert self.peticion().cache_key == self.peticion().cache_key

    def test_el_orden_de_los_simbolos_no_cambia_la_clave(self) -> None:
        """La misma pregunta escrita al reves sigue siendo la misma pregunta."""
        a = self.peticion(symbols=("AAPL", "GLD"))
        b = self.peticion(symbols=("GLD", "AAPL"))
        assert a.cache_key == b.cache_key

    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("model", "claude-sonnet-5"),
            ("instructions_version", "v2"),
            ("timestamp", datetime(2021, 1, 1, tzinfo=UTC)),
            ("market_context", "otros precios"),
            ("symbols", ("AAPL", "GLD", "TLT")),
        ],
    )
    def test_cambiar_lo_que_determina_la_decision_cambia_la_clave(
        self, campo: str, valor: object
    ) -> None:
        """FR-045: cambiar de modelo NO puede reutilizar decisiones del anterior."""
        assert self.peticion().cache_key != self.peticion(**{campo: valor}).cache_key

    def test_la_clave_es_estable_entre_ejecuciones(self) -> None:
        """Un hash que cambia al reiniciar el proceso no sirve de cache."""
        assert self.peticion().cache_key == (
            DecisionRequest(
                timestamp=CUANDO,
                symbols=("AAPL", "GLD"),
                market_context="precios...",
                instructions_version="v1",
                model="claude-opus-5",
            ).cache_key
        )

    def test_la_clave_es_imprimible_y_sirve_de_nombre_de_fichero(self) -> None:
        clave = self.peticion().cache_key
        assert clave.isalnum()
        assert len(clave) >= 16
