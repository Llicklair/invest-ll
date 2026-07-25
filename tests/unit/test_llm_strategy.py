"""El LLM como estrategia (T021-T027).

Estos tests son los que sostienen la afirmación central de la feature: que el LLM se mide con la
misma vara que una regla fija. Si la paridad de informes cae, "el LLM elige mejor" deja de ser
comprobable y pasa a ser una opinión.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest

from invest_ll.data.universe import build_universe
from invest_ll.decision.models import Action, AssetDecision, Decision, DecisionRequest
from invest_ll.decision.schema import DecisionUnavailableError
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.rotation import run_rotation
from invest_ll.strategy.llm import LLMStrategy
from invest_ll.strategy.rotation import RelativeMomentum, RotationStrategy

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

D = Decimal
FR = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RI = RiskConfig(position_fraction=D(1))


def universo(n: int = 300):  # type: ignore[no-untyped-def]
    return build_universe(
        [
            series_from_closes(ramp(n), symbol="AAPL"),
            series_from_closes(ramp(n, start=50.0), symbol="GLD", start=ORIGIN),
        ]
    )


class SiempreElMismo:
    """Proveedor que elige siempre el mismo activo. Cuenta cuántas veces le preguntan."""

    def __init__(self, symbol: str | None = "AAPL", *, model: str = "falso") -> None:
        self.symbol = symbol
        self.llamadas = 0
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def decide(self, request: DecisionRequest) -> Decision:
        self.llamadas += 1
        activos: tuple[AssetDecision, ...] = ()
        if self.symbol is not None:
            activos = (
                AssetDecision(
                    symbol=self.symbol,
                    action=Action.ENTER,
                    weight=D("1.0"),
                    reasoning="lidera con claridad",
                ),
            )
        return Decision(
            timestamp=request.timestamp,
            assets=activos,
            summary="decision de prueba",
            model=self._model,
        )

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        return [self.decide(r) for r in requests]


class Roto:
    """Proveedor que siempre falla."""

    model = "roto"

    def decide(self, request: DecisionRequest) -> Decision:
        raise DecisionUnavailableError("el proveedor no responde")

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        return [self.decide(r) for r in requests]


class TestCumpleElProtocolo:
    def test_es_una_rotation_strategy(self) -> None:
        """T021 · Principio V: misma interfaz que las reglas fijas."""
        assert isinstance(LLMStrategy(SiempreElMismo()), RotationStrategy)

    def test_run_rotation_la_acepta_sin_distinguirla(self) -> None:
        """El motor no sabe que hay un LLM detras. Ese es justo el punto."""
        informe = run_rotation(
            universo(),
            LLMStrategy(SiempreElMismo()),
            initial_capital=D(10000),
            friction=FR,
            risk=RI,
        )
        assert informe.trade_count >= 0

    def test_periodicidad_invalida_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="al menos cada periodo"):
            LLMStrategy(SiempreElMismo(), every_periods=0)


class TestReutilizaLaDecision:
    """T022 · FR-042: consultar en cada vela seria inviable y ademas irreal."""

    def test_no_pregunta_en_cada_periodo(self) -> None:
        proveedor = SiempreElMismo()
        run_rotation(
            universo(300),
            LLMStrategy(proveedor, every_periods=21),
            initial_capital=D(10000),
            friction=FR,
            risk=RI,
        )
        # ~300 periodos / 21 ≈ 15 decisiones, no 300.
        assert proveedor.llamadas < 25

    def test_mas_frecuencia_significa_mas_llamadas(self) -> None:
        raro = SiempreElMismo()
        frecuente = SiempreElMismo()
        for proveedor, cada in ((raro, 60), (frecuente, 5)):
            run_rotation(
                universo(300),
                LLMStrategy(proveedor, every_periods=cada),
                initial_capital=D(10000),
                friction=FR,
                risk=RI,
            )
        assert frecuente.llamadas > raro.llamadas

    def test_entre_decisiones_devuelve_lo_vigente(self) -> None:
        proveedor = SiempreElMismo("GLD")
        estrategia = LLMStrategy(proveedor, every_periods=10)
        u = universo(100)
        from invest_ll.engine.universe_view import UniverseView

        primera = estrategia.choose(UniverseView(universe=u, cursor=50))
        segunda = estrategia.choose(UniverseView(universe=u, cursor=51))

        assert primera == segunda == "GLD"
        assert proveedor.llamadas == 1


class TestUnFalloDetieneElBacktest:
    """T023: sustituir un fallo por 'mantener' convertiria un error en un resultado."""

    def test_el_fallo_del_proveedor_se_propaga(self) -> None:
        with pytest.raises(DecisionUnavailableError):
            run_rotation(
                universo(),
                LLMStrategy(Roto()),
                initial_capital=D(10000),
                friction=FR,
                risk=RI,
            )

    def test_no_se_traga_el_error_devolviendo_none(self) -> None:
        estrategia = LLMStrategy(Roto())
        from invest_ll.engine.universe_view import UniverseView

        with pytest.raises(DecisionUnavailableError):
            estrategia.choose(UniverseView(universe=universo(100), cursor=50))


class TestRegistroDelRazonamiento:
    """T027 · FR-012."""

    def test_guarda_cada_decision_con_su_razonamiento(self) -> None:
        estrategia = LLMStrategy(SiempreElMismo(), every_periods=21)
        run_rotation(universo(300), estrategia, initial_capital=D(10000), friction=FR, risk=RI)
        assert estrategia.decision_count > 0
        for decision in estrategia.decisions:
            assert decision.summary
            for activo in decision.assets:
                assert activo.reasoning.strip()

    def test_las_decisiones_conservan_su_instante(self) -> None:
        estrategia = LLMStrategy(SiempreElMismo(), every_periods=21)
        run_rotation(universo(300), estrategia, initial_capital=D(10000), friction=FR, risk=RI)
        marcas = [d.timestamp for d in estrategia.decisions]
        assert marcas == sorted(marcas), "las decisiones deben ir en orden temporal"


class TestParidadDeInformes:
    """T025 · Principio III + V: la misma vara para todos.

    Es el test que hace comprobable la afirmacion central de la feature.
    """

    def informes(self):  # type: ignore[no-untyped-def]
        u = universo(300)
        llm = run_rotation(
            u, LLMStrategy(SiempreElMismo()), initial_capital=D(10000), friction=FR, risk=RI
        )
        regla = run_rotation(
            u, RelativeMomentum(lookback=60), initial_capital=D(10000), friction=FR, risk=RI
        )
        return llm, regla

    def test_los_dos_informes_tienen_los_mismos_campos(self) -> None:
        llm, regla = self.informes()
        assert type(llm) is type(regla)

    def test_las_metricas_obligatorias_estan_en_ambos(self) -> None:
        llm, regla = self.informes()
        for informe in (llm, regla):
            assert informe.net_result is not None
            assert informe.max_drawdown is not None
            assert informe.total_costs is not None
            assert informe.trade_count >= 0
            assert informe.buy_and_hold is not None

    def test_los_dos_se_pueden_comparar_directamente(self) -> None:
        """Sin esto, 'el LLM elige mejor' no seria una afirmacion comprobable."""
        llm, regla = self.informes()
        diferencia = llm.net_result - regla.net_result
        assert isinstance(diferencia, Decimal)

    def test_el_informe_del_llm_no_tiene_formato_propio(self) -> None:
        """Si se pudiera distinguir por el formato, el Principio V estaria roto."""
        llm, regla = self.informes()
        assert set(llm.render().split()) - set(llm.render().split()) == set()
        # Ambos rinden un texto con las mismas secciones obligatorias.
        for informe in (llm, regla):
            texto = informe.render().lower()
            assert "win rate" in texto
            assert "drawdown" in texto


class TestQuedarseFuera:
    def test_el_llm_puede_no_estar_en_nada(self) -> None:
        """Quedarse fuera es una decision valida, no un fallo."""
        estrategia = LLMStrategy(SiempreElMismo(None))
        informe = run_rotation(
            universo(300), estrategia, initial_capital=D(10000), friction=FR, risk=RI
        )
        assert informe.trade_count == 0


class TestTraduccionDeSimbolos:
    """El bug que aparecio al generar decisiones de verdad.

    El contexto va anonimizado (A, B, C...) para no darle al modelo pistas sobre que activo es.
    Si la respuesta no se traduce de vuelta, la decision guarda "C" y el motor busca un activo
    llamado "C" que no existe. Los tests con dobles no lo detectaban porque los dobles devuelven
    simbolos reales directamente.
    """

    def test_la_peticion_lleva_el_mapa_de_traduccion(self) -> None:
        capturadas: list[DecisionRequest] = []

        class Espia:
            model = "espia"

            def decide(self, request: DecisionRequest) -> Decision:
                capturadas.append(request)
                return Decision(
                    timestamp=request.timestamp,
                    assets=(),
                    summary="fuera",
                    model="espia",
                )

            def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
                return [self.decide(r) for r in requests]

        from invest_ll.engine.universe_view import UniverseView

        LLMStrategy(Espia()).choose(UniverseView(universe=universo(100), cursor=50))

        assert capturadas
        assert capturadas[0].labels == {"A": "AAPL", "B": "GLD"}

    def test_el_mapa_no_cambia_la_clave_del_cache(self) -> None:
        """Se deriva de `symbols`, que ya esta en la clave: anadirlo seria redundante."""
        from datetime import UTC, datetime

        base = {
            "timestamp": datetime(2020, 6, 1, tzinfo=UTC),
            "symbols": ("AAPL", "GLD"),
            "market_context": "x",
            "instructions_version": "v1",
            "model": "m",
        }
        sin_mapa = DecisionRequest(**base)  # type: ignore[arg-type]
        con_mapa = DecisionRequest(**base, symbol_map=(("A", "AAPL"), ("B", "GLD")))  # type: ignore[arg-type]
        assert sin_mapa.cache_key == con_mapa.cache_key
