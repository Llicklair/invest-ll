"""Proveedores de decisiones y caché (T013, T016).

El test central de este fichero es `test_repetir_no_vuelve_a_preguntar`. Como `temperature` está
eliminada en los modelos actuales, no hay forma de pedir determinismo: el caché **es** la
reproducibilidad. Si ese test cae, comparar dos experimentos deja de significar nada.

Toda la suite corre con los sockets bloqueados, así que un proveedor que intentara salir a la red
fallaría aquí de forma ruidosa.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.models import Action, AssetDecision, Decision, DecisionRequest
from invest_ll.decision.provider import (
    CachedProvider,
    DecisionProvider,
    RecordedProvider,
    ScriptedProvider,
)
from invest_ll.decision.schema import DecisionUnavailableError

D = Decimal
CUANDO = datetime(2020, 6, 1, tzinfo=UTC)


def decision(cuando: datetime = CUANDO, *, symbol: str = "AAPL", model: str = "m") -> Decision:
    return Decision(
        timestamp=cuando,
        assets=(
            AssetDecision(symbol=symbol, action=Action.ENTER, weight=D("0.6"), reasoning="lidera"),
        ),
        summary="resumen",
        model=model,
    )


def peticion(cuando: datetime = CUANDO, *, model: str = "m") -> DecisionRequest:
    return DecisionRequest(
        timestamp=cuando,
        symbols=("AAPL", "GLD"),
        market_context="contexto",
        instructions_version="v1",
        model=model,
    )


class ContadorProvider:
    """Proveedor de mentira que cuenta cuántas veces le preguntan."""

    def __init__(self, *, model: str = "m") -> None:
        self.llamadas = 0
        self.lotes = 0
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def decide(self, request: DecisionRequest) -> Decision:
        self.llamadas += 1
        return decision(request.timestamp, model=self._model)

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        self.lotes += 1
        self.llamadas += len(requests)
        return [decision(r.timestamp, model=self._model) for r in requests]


class TestCumplenElProtocolo:
    def test_los_tres_cumplen_el_protocolo(self, tmp_path: Path) -> None:
        store = DecisionStore(tmp_path)
        assert isinstance(ScriptedProvider([decision()]), DecisionProvider)
        assert isinstance(RecordedProvider(store, model="m"), DecisionProvider)
        assert isinstance(CachedProvider(ContadorProvider(), store), DecisionProvider)


class TestScripted:
    def test_devuelve_la_decision_del_instante(self) -> None:
        p = ScriptedProvider([decision()])
        assert p.decide(peticion()).chosen == "AAPL"

    def test_sin_decision_para_ese_instante_lanza(self) -> None:
        """Nunca improvisa: eso convertiria un hueco en un resultado."""
        p = ScriptedProvider([decision()])
        with pytest.raises(DecisionUnavailableError):
            p.decide(peticion(CUANDO + timedelta(days=1)))

    def test_cuenta_las_llamadas(self) -> None:
        p = ScriptedProvider([decision()])
        p.decide(peticion())
        p.decide(peticion())
        assert p.calls == 2


class TestRecorded:
    def test_lee_lo_guardado(self, tmp_path: Path) -> None:
        store = DecisionStore(tmp_path)
        r = peticion()
        store.put(r.cache_key, decision())
        assert RecordedProvider(store, model="m").decide(r).chosen == "AAPL"

    def test_lo_que_falta_lanza_en_vez_de_improvisar(self, tmp_path: Path) -> None:
        p = RecordedProvider(DecisionStore(tmp_path), model="m")
        with pytest.raises(DecisionUnavailableError, match="no hay decision grabada"):
            p.decide(peticion())


class TestCached:
    def test_la_primera_vez_pregunta(self, tmp_path: Path) -> None:
        interior = ContadorProvider()
        p = CachedProvider(interior, DecisionStore(tmp_path))
        p.decide(peticion())
        assert interior.llamadas == 1

    def test_repetir_no_vuelve_a_preguntar(self, tmp_path: Path) -> None:
        """EL test de este fichero. Sin esto no hay reproducibilidad (FR-044)."""
        interior = ContadorProvider()
        p = CachedProvider(interior, DecisionStore(tmp_path))

        primera = p.decide(peticion())
        segunda = p.decide(peticion())

        assert interior.llamadas == 1
        assert primera == segunda

    def test_el_cache_sobrevive_al_proceso(self, tmp_path: Path) -> None:
        """Un cache que solo vive en memoria no sirve para repetir un experimento manana."""
        interior = ContadorProvider()
        CachedProvider(interior, DecisionStore(tmp_path)).decide(peticion())

        otro = ContadorProvider()
        CachedProvider(otro, DecisionStore(tmp_path)).decide(peticion())

        assert otro.llamadas == 0

    def test_cambiar_de_modelo_si_vuelve_a_preguntar(self, tmp_path: Path) -> None:
        """FR-045: reutilizar la decision de otro modelo seria mentir sobre que se midio."""
        store = DecisionStore(tmp_path)
        CachedProvider(ContadorProvider(model="opus"), store).decide(peticion(model="opus"))

        otro = ContadorProvider(model="sonnet")
        CachedProvider(otro, store).decide(peticion(model="sonnet"))

        assert otro.llamadas == 1

    def test_cuenta_lo_que_hubo_que_pagar(self, tmp_path: Path) -> None:
        p = CachedProvider(ContadorProvider(), DecisionStore(tmp_path))
        p.decide(peticion())
        p.decide(peticion())
        assert p.misses == 1


class TestLotes:
    def test_un_lote_es_una_sola_llamada(self, tmp_path: Path) -> None:
        """El descuento por lotes es la mitad del precio: hay que aprovecharlo."""
        interior = ContadorProvider()
        p = CachedProvider(interior, DecisionStore(tmp_path))

        peticiones = [peticion(CUANDO + timedelta(days=i)) for i in range(10)]
        p.decide_many(peticiones)

        assert interior.lotes == 1
        assert interior.llamadas == 10

    def test_el_lote_solo_pregunta_por_lo_que_falta(self, tmp_path: Path) -> None:
        store = DecisionStore(tmp_path)
        peticiones = [peticion(CUANDO + timedelta(days=i)) for i in range(10)]

        CachedProvider(ContadorProvider(), store).decide_many(peticiones[:6])

        interior = ContadorProvider()
        CachedProvider(interior, store).decide_many(peticiones)

        assert interior.llamadas == 4

    def test_el_orden_del_lote_se_respeta(self, tmp_path: Path) -> None:
        """Devolver las decisiones desordenadas asignaria la de un dia a otro."""
        store = DecisionStore(tmp_path)
        peticiones = [peticion(CUANDO + timedelta(days=i)) for i in range(5)]
        CachedProvider(ContadorProvider(), store).decide_many(peticiones[1:4])

        salida = CachedProvider(ContadorProvider(), store).decide_many(peticiones)

        assert [d.timestamp for d in salida] == [r.timestamp for r in peticiones]

    def test_un_lote_incompleto_lanza(self, tmp_path: Path) -> None:
        class Tacano:
            model = "m"

            def decide(self, request: DecisionRequest) -> Decision:  # pragma: no cover
                return decision(request.timestamp)

            def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
                return [decision(requests[0].timestamp)]

        p = CachedProvider(Tacano(), DecisionStore(tmp_path))
        with pytest.raises(DecisionUnavailableError, match="se pidieron 3"):
            p.decide_many([peticion(CUANDO + timedelta(days=i)) for i in range(3)])


class TestAlmacen:
    def test_guardar_y_leer_conserva_todo(self, tmp_path: Path) -> None:
        store = DecisionStore(tmp_path)
        original = decision()
        store.put("clave", original)

        recuperada = DecisionStore(tmp_path).get("clave")
        assert recuperada == original

    def test_el_peso_no_pierde_precision_al_ir_a_disco(self, tmp_path: Path) -> None:
        """Es una fraccion de capital: pasar por float la degradaria."""
        store = DecisionStore(tmp_path)
        d = Decision(
            timestamp=CUANDO,
            assets=(
                AssetDecision(
                    symbol="A", action=Action.ENTER, weight=D("0.333333333"), reasoning="r"
                ),
            ),
            summary="x",
            model="m",
        )
        store.put("k", d)
        leida = DecisionStore(tmp_path).get("k")
        assert leida is not None
        assert leida.assets[0].weight == D("0.333333333")

    def test_lo_que_no_esta_devuelve_none(self, tmp_path: Path) -> None:
        assert DecisionStore(tmp_path).get("no-existe") is None

    def test_un_fichero_corrupto_se_trata_como_ausencia(self, tmp_path: Path) -> None:
        """Volver a preguntar cuesta dinero; devolver algo a medias cuesta mas."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "roto.json").write_text("{no es json", encoding="utf-8")
        assert DecisionStore(tmp_path).get("roto") is None

    def test_no_deja_ficheros_temporales(self, tmp_path: Path) -> None:
        store = DecisionStore(tmp_path)
        store.put("k", decision())
        assert list(tmp_path.glob("*.tmp")) == []
