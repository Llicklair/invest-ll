"""El proveedor real. **El único módulo del proyecto que sale a la red por su cuenta.**

Notas que no son obvias y que costaría descubrir:

- **No se envía `temperature`.** Está eliminada en los modelos actuales y enviarla devuelve un
  error 400. Tampoco `top_p` ni `top_k`. El determinismo se consigue no volviendo a preguntar
  (`CachedProvider`), no configurando el muestreo.
- **`stop_reason` se comprueba antes que el contenido.** Un rechazo por seguridad devuelve un 200
  con contenido vacío o parcial; leer `content[0]` sin mirar antes revienta.
- **El contexto estable va primero y lo volátil al final**, para que el caché de prompt de la API
  sirva de algo: cualquier byte que cambie al principio invalida todo lo que viene detrás.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from invest_ll.decision.models import Decision, DecisionRequest
from invest_ll.decision.prompt import INSTRUCCIONES
from invest_ll.decision.schema import (
    ESQUEMA_DECISION,
    DecisionUnavailableError,
    parse_decision,
)

if TYPE_CHECKING:  # pragma: no cover
    from anthropic import Anthropic

MODELO_POR_DEFECTO = "claude-opus-5"
MAX_TOKENS = 2000

# Precios por millón de tokens del modelo por defecto. Solo se usan para estimar antes de
# lanzar (FR-041); no se factura nada aquí.
PRECIO_ENTRADA = 5.0
PRECIO_SALIDA = 25.0


class AnthropicProvider:
    """Pide decisiones a Claude.

    El cliente se recibe ya construido en lugar de crearse aquí: así un test puede pasar un doble
    sin monkeypatching, y este módulo no decide de dónde salen las credenciales.
    """

    __slots__ = ("_client", "_model")

    def __init__(self, client: Anthropic, *, model: str = MODELO_POR_DEFECTO) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def decide(self, request: DecisionRequest) -> Decision:
        respuesta = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": INSTRUCCIONES,
                    # Lo estable va primero y marcado: las lecturas de cache cuestan ~0,1x.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA_DECISION}},
            # El contexto de mercado va al final porque cambia en cada peticion.
            messages=[{"role": "user", "content": request.market_context}],
        )

        return self._leer(respuesta, request)

    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]:
        """Una por una, en el mismo orden.

        Aquí es donde encajaría la Batches API (mitad de precio): las peticiones son
        independientes entre sí, así que agruparlas es correcto. Se deja para cuando haya
        volumen real que lo justifique — la interfaz ya lo permite sin cambiarla.
        """
        return [self.decide(r) for r in requests]

    def _leer(self, respuesta: Any, request: DecisionRequest) -> Decision:
        # Primero el motivo de parada: un rechazo trae contenido vacio o parcial, y leerlo
        # directamente reventaria con un IndexError que no explica nada.
        motivo = getattr(respuesta, "stop_reason", None)
        if motivo == "refusal":
            detalle = getattr(respuesta, "stop_details", None)
            categoria = getattr(detalle, "category", None) or "sin categoria"
            raise DecisionUnavailableError(
                f"el modelo rechazo la peticion ({categoria}) para {request.timestamp.isoformat()}"
            )
        if motivo == "max_tokens":
            raise DecisionUnavailableError(
                "la respuesta se corto por longitud: sube max_tokens o reduce el contexto"
            )

        texto = next(
            (b.text for b in respuesta.content if getattr(b, "type", None) == "text"), None
        )
        if texto is None:
            raise DecisionUnavailableError(f"la respuesta no trae texto (stop_reason={motivo})")

        return parse_decision(
            texto,
            timestamp=request.timestamp,
            model=self._model,
            symbol_map=request.labels or None,
        )
