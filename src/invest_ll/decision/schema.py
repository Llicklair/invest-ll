"""Esquema de la decisión y su lectura.

FR-011: una respuesta que no se pueda interpretar es un **fallo**, no una decisión por defecto.
Este módulo nunca inventa nada — si el JSON no encaja, lanza. La alternativa (devolver "mantener"
cuando no se entiende la respuesta) convertiría un error en un resultado, y el informe diría algo
que no ocurrió.

El esquema JSON de la API **no admite límites numéricos** (`minimum`, `maximum`), así que los pesos
se validan aquí y en `models.py`. Delegarlos al esquema habría sido más limpio y no es posible.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from invest_ll.decision.models import Action, AssetDecision, Decision
from invest_ll.errors import InvestLLError

ESQUEMA_DECISION: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Explicacion global de la decision, en una o dos frases.",
        },
        "assets": {
            "type": "array",
            "description": "Una entrada por activo sobre el que se decide algo.",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "La etiqueta del activo tal como aparece en el contexto.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["hold", "enter", "exit"],
                    },
                    "weight": {
                        "type": "number",
                        "description": "Fraccion del capital, entre 0 y 1. La suma no puede pasar de 1.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Por que esta decision para este activo. Obligatorio.",
                    },
                },
                "required": ["symbol", "action", "weight", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "assets"],
    "additionalProperties": False,
}


class DecisionParseError(InvestLLError):
    """La respuesta del modelo no es una decisión interpretable."""


class DecisionUnavailableError(InvestLLError):
    """No se pudo obtener una decisión: sin respuesta, sin caché o sin cuota."""


def parse_decision(
    payload: str,
    *,
    timestamp: datetime,
    model: str,
    symbol_map: dict[str, str] | None = None,
) -> Decision:
    """Convierte la respuesta del modelo en una `Decision`, o lanza.

    `symbol_map` traduce las etiquetas anónimas (A, B...) de vuelta a los símbolos reales. Si un
    activo no está en el mapa, es un fallo: el modelo se inventó un activo que no existe.
    """
    crudo: object
    try:
        crudo = json.loads(payload)
    except json.JSONDecodeError as error:
        raise DecisionParseError(f"la respuesta no es JSON valido: {payload[:120]!r}") from error

    if not isinstance(crudo, dict):
        raise DecisionParseError(f"se esperaba un objeto, llego {type(crudo).__name__}")

    # json.loads devuelve Any; tras comprobar que es un dict, se afirma su forma. El cast es
    # explicito a proposito: dice "aqui dejo de haber garantia del tipo y empieza la mia".
    datos = cast("dict[str, object]", crudo)
    resumen = datos.get("summary")
    activos_crudos = datos.get("assets")

    if not isinstance(resumen, str):
        raise DecisionParseError("falta el resumen de la decision")
    if not isinstance(activos_crudos, list):
        raise DecisionParseError("falta la lista de activos")

    activos = tuple(
        _leer_activo(entrada, indice, symbol_map)
        for indice, entrada in enumerate(cast("list[object]", activos_crudos))
    )

    try:
        return Decision(timestamp=timestamp, assets=activos, summary=resumen, model=model)
    except ValueError as error:
        # Los invariantes de Decision (pesos, duplicados) son parte del contrato: incumplirlos
        # es una respuesta invalida, no un error interno.
        raise DecisionParseError(str(error)) from error


def _leer_activo(entrada: object, indice: int, symbol_map: dict[str, str] | None) -> AssetDecision:
    if not isinstance(entrada, dict):
        raise DecisionParseError(f"el activo {indice} no es un objeto")

    campos = cast("dict[str, object]", entrada)
    etiqueta = campos.get("symbol")
    accion = campos.get("action")
    peso = campos.get("weight")
    razon = campos.get("reasoning")

    if not isinstance(etiqueta, str):
        raise DecisionParseError(f"el activo {indice} no tiene simbolo")
    if not isinstance(accion, str):
        raise DecisionParseError(f"el activo {etiqueta} no tiene accion")
    if not isinstance(razon, str):
        raise DecisionParseError(f"el activo {etiqueta} no tiene razonamiento")

    simbolo = etiqueta
    if symbol_map is not None:
        if etiqueta not in symbol_map:
            raise DecisionParseError(
                f"el modelo eligio {etiqueta!r}, que no esta en el universo {sorted(symbol_map)}"
            )
        simbolo = symbol_map[etiqueta]

    try:
        accion_valida = Action(accion)
    except ValueError as error:
        raise DecisionParseError(f"accion desconocida en {etiqueta}: {accion!r}") from error

    try:
        # str() antes de Decimal: pasar un float directamente arrastra su error de
        # representacion, y estos pesos multiplican cifras de dinero.
        peso_valido = Decimal(str(peso))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise DecisionParseError(f"peso invalido en {etiqueta}: {peso!r}") from error

    try:
        return AssetDecision(
            symbol=simbolo,
            action=accion_valida,
            weight=peso_valido,
            reasoning=razon,
        )
    except ValueError as error:
        raise DecisionParseError(str(error)) from error
