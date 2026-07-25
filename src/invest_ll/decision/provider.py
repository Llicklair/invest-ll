"""La frontera con el LLM.

Todo lo que sale a la red vive detrás de este protocolo, para que el resto del sistema no lo
conozca y para que los tests puedan sustituirlo. Es el mismo patrón que aisló a los proveedores de
datos en la feature 002.

**`decide_many` está en el protocolo desde el primer día** y no es un detalle. Las decisiones de un
backtest son independientes entre sí —cada una solo mira su propia ventana—, así que se pueden
enviar en lote a mitad de precio. Añadirlo después obligaría a cambiar todos los implementadores.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.models import Decision, DecisionRequest
from invest_ll.decision.schema import DecisionUnavailableError


@runtime_checkable
class DecisionProvider(Protocol):
    """De dónde salen las decisiones."""

    @property
    def model(self) -> str:
        """Qué modelo las produce. Entra en la clave del caché."""
        ...

    def decide(self, request: DecisionRequest) -> Decision:
        """Una decisión. Lanza si no se puede obtener — nunca inventa."""
        ...

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        """Varias de golpe. El orden de la respuesta coincide con el de la petición."""
        ...


class ScriptedProvider:
    """Decisiones fijas escritas a mano. Para probar casos límite.

    No toca la red ni disco: es lo que permite probar `LLMStrategy` sin depender de nada.
    """

    __slots__ = ("_by_timestamp", "_calls", "_model")

    def __init__(self, decisions: Sequence[Decision], *, model: str = "scripted") -> None:
        self._by_timestamp = {d.timestamp: d for d in decisions}
        self._model = model
        self._calls = 0

    @property
    def model(self) -> str:
        return self._model

    @property
    def calls(self) -> int:
        """Cuántas veces se ha consultado. Lo usan los tests de reutilización (FR-042)."""
        return self._calls

    def decide(self, request: DecisionRequest) -> Decision:
        self._calls += 1
        decision = self._by_timestamp.get(request.timestamp)
        if decision is None:
            raise DecisionUnavailableError(
                f"no hay decision escrita para {request.timestamp.isoformat()}"
            )
        return decision

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        return [self.decide(r) for r in requests]


class RecordedProvider:
    """Lee decisiones ya guardadas y no consulta a nadie.

    Es lo que hace reproducible un experimento: repetirlo devuelve exactamente lo mismo y no gasta
    ni una llamada. Si falta una decisión, **lanza** en vez de improvisar — un experimento al que
    le faltan piezas no es el mismo experimento.
    """

    __slots__ = ("_model", "_store")

    def __init__(self, store: DecisionStore, *, model: str) -> None:
        self._store = store
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def decide(self, request: DecisionRequest) -> Decision:
        decision = self._store.get(request.cache_key)
        if decision is None:
            raise DecisionUnavailableError(
                f"no hay decision grabada para {request.timestamp.isoformat()} "
                f"(clave {request.cache_key}). Genera el experimento antes de repetirlo."
            )
        return decision

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        return [self.decide(r) for r in requests]


class CachedProvider:
    """Envuelve a otro proveedor y guarda lo que devuelve.

    Es donde vive la reproducibilidad del sistema. Como `temperature` ya no existe en los modelos
    actuales, no hay forma de pedirle al modelo que sea determinista: la única manera de que dos
    ejecuciones del mismo experimento den lo mismo es no volver a preguntar (FR-044).
    """

    __slots__ = ("_inner", "_misses", "_store")

    def __init__(self, inner: DecisionProvider, store: DecisionStore) -> None:
        self._inner = inner
        self._store = store
        self._misses = 0

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def misses(self) -> int:
        """Cuántas hubo que preguntar de verdad. Es lo que se paga."""
        return self._misses

    def decide(self, request: DecisionRequest) -> Decision:
        guardada = self._store.get(request.cache_key)
        if guardada is not None:
            return guardada

        self._misses += 1
        decision = self._inner.decide(request)
        self._store.put(request.cache_key, decision)
        return decision

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        """Pregunta en un solo lote solo por lo que falta.

        Separar lo cacheado de lo pendiente antes de llamar es lo que hace que repetir un
        experimento con un activo nuevo cueste una fracción en vez de todo otra vez.
        """
        pendientes: list[DecisionRequest] = []
        resultado: list[Decision | None] = []

        for request in requests:
            guardada = self._store.get(request.cache_key)
            resultado.append(guardada)
            if guardada is None:
                pendientes.append(request)

        if pendientes:
            self._misses += len(pendientes)
            nuevas = self._inner.decide_many(pendientes)
            if len(nuevas) != len(pendientes):
                raise DecisionUnavailableError(
                    f"se pidieron {len(pendientes)} decisiones y llegaron {len(nuevas)}"
                )
            for request, decision in zip(pendientes, nuevas, strict=True):
                self._store.put(request.cache_key, decision)

            iterador = iter(nuevas)
            resultado = [d if d is not None else next(iterador) for d in resultado]

        return [d for d in resultado if d is not None]
