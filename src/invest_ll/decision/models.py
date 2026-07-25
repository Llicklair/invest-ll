"""Entidades de la capa de decisión.

Una decisión inválida falla al construirse. No más tarde, y no en silencio: lo que hay al otro
lado es una simulación con cifras de dinero, y un peso de 1.5 que se cuela produce un resultado
que parece bueno y no existe.

**Nota sobre el no-determinismo.** `temperature` está eliminada en los modelos actuales — enviarla
devuelve un error, y cuando existía tampoco garantizaba salidas idénticas. Por eso `cache_key`
lleva todo lo que determina una decisión: es el único mecanismo de reproducibilidad que queda
(FR-044), no una optimización de coste.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256

PESO_MINIMO = Decimal(0)
PESO_MAXIMO = Decimal(1)
LONGITUD_CLAVE = 32


class Action(Enum):
    """Qué hacer con un activo."""

    HOLD = "hold"
    ENTER = "enter"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class AssetDecision:
    """Qué hacer con un activo concreto, y por qué."""

    symbol: str
    action: Action
    weight: Decimal
    reasoning: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("una decision necesita un simbolo")
        if not PESO_MINIMO <= self.weight <= PESO_MAXIMO:
            raise ValueError(f"el peso debe estar entre 0 y 1, recibido {self.weight}")
        if self.action is Action.ENTER and self.weight <= 0:
            raise ValueError(f"entrar en {self.symbol} exige un peso positivo")
        if not self.reasoning.strip():
            raise ValueError(f"falta el razonamiento de {self.symbol} (FR-012)")


@dataclass(frozen=True, slots=True)
class Decision:
    """La respuesta completa para un instante."""

    timestamp: datetime
    assets: tuple[AssetDecision, ...]
    summary: str
    model: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("la marca de tiempo necesita zona horaria")
        if not self.model.strip():
            raise ValueError("hay que saber que modelo produjo la decision (FR-045)")

        simbolos = [a.symbol for a in self.assets]
        if len(simbolos) != len(set(simbolos)):
            raise ValueError(f"simbolos repetidos en la decision: {simbolos}")

        if self.total_weight > PESO_MAXIMO:
            raise ValueError(
                f"la suma de pesos es {self.total_weight}, mayor que 1. "
                "No hay apalancamiento en v1: esto es un fallo, no algo que recortar."
            )

    @property
    def total_weight(self) -> Decimal:
        """Cuánto del capital compromete. Solo cuenta lo que entra o se mantiene."""
        return sum(
            (a.weight for a in self.assets if a.action is not Action.EXIT),
            start=Decimal(0),
        )

    @property
    def chosen(self) -> str | None:
        """El activo de mayor peso, o `None` si la decisión es quedarse fuera.

        El motor de rotación espera un activo o nada, así que aquí se traduce. Cuando el LLM
        reparte entre varios, se toma el de mayor peso: la rotación no admite carteras mixtas.
        """
        candidatos = [a for a in self.assets if a.action is not Action.EXIT and a.weight > 0]
        if not candidatos:
            return None
        return max(candidatos, key=lambda a: a.weight).symbol


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """Todo lo que determina una decisión. Es la clave del caché.

    Si un dato no cambia la decisión, no debe entrar aquí: metería ruido en la clave y haría
    fallar el caché sin motivo.
    """

    timestamp: datetime
    symbols: tuple[str, ...]
    market_context: str
    instructions_version: str
    model: str
    # Que etiqueta anonima corresponde a cada activo real. NO entra en `cache_key`: se deriva de
    # `symbols`, que si esta, asi que anadirlo no cambiaria la identidad de la pregunta.
    symbol_map: tuple[tuple[str, str], ...] = ()

    @property
    def labels(self) -> dict[str, str]:
        """El mapa como diccionario, listo para traducir la respuesta."""
        return dict(self.symbol_map)

    @property
    def cache_key(self) -> str:
        """Hash estable del contenido más el modelo.

        Los símbolos se ordenan: preguntar por [AAPL, GLD] o por [GLD, AAPL] es la misma pregunta,
        y tratarlas como distintas duplicaría el gasto sin motivo.

        Se usa sha256 y no `hash()` porque el hash de Python cambia entre ejecuciones — un caché
        que se invalida al reiniciar no es un caché.
        """
        material = "\n".join(
            (
                self.model,
                self.instructions_version,
                self.timestamp.isoformat(),
                ",".join(sorted(self.symbols)),
                self.market_context,
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()[:LONGITUD_CLAVE]
