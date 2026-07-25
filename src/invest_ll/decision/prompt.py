"""Traducción de lo que el motor deja ver a un texto que el LLM puede leer.

Función pura: no toca la red, no guarda nada, y solo lee de `UniverseView`. Eso último es lo que
importa — `UniverseView` ya impide estructuralmente ver el futuro, así que el LLM hereda esa
garantía sin código nuevo (Principio II).

**Lo que este módulo NO puede arreglar.** El modelo fue entrenado con datos que incluyen lo que
pasó después del periodo simulado. Aquí se acota lo acotable: no se mencionan fechas ni se dan
pistas de en qué año estamos. Pero un modelo que reconozca "caída del 34% en cinco semanas" sabe
que eso fue marzo de 2020, y contra eso no hay diseño posible. Por eso un buen resultado del LLM
sobre el pasado no demuestra nada (FR-010).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.universe_view import UniverseView

VENTANAS = (5, 20, 60, 120)
DECIMALES = 4

INSTRUCCIONES_VERSION = "v1"

INSTRUCCIONES = """\
Eres un selector de activos dentro de un sistema de inversion. Recibes datos de precios
normalizados y debes decidir en cual estar, o quedarte fuera.

Reglas:
- Solo puedes usar la informacion de este mensaje. No dispones de nada mas.
- Los activos aparecen con nombres genericos (A, B, C...). No intentes adivinar cuales son.
- Los precios estan normalizados: el ultimo cierre de cada activo es 100.
- Quedarte fuera es una decision valida y a veces la correcta.
- La suma de pesos no puede pasar de 1.
- Cada decision necesita su razonamiento.
"""


def render_context(view: UniverseView, *, anonymous: bool = True) -> str:
    """Convierte el estado visible del mercado en texto.

    `anonymous=True` sustituye los símbolos reales por letras y normaliza los precios. Es lo que
    acota la contaminación: sin nombres ni fechas, el modelo tiene menos asideros para reconocer
    el periodo. No la elimina — ver la nota del módulo.
    """
    lineas: list[str] = []
    simbolos = view.symbols

    for indice, symbol in enumerate(simbolos):
        etiqueta = _etiqueta(indice) if anonymous else symbol
        lineas.append(f"Activo {etiqueta}:")

        for periodos in VENTANAS:
            rendimiento = view.return_over(symbol, periodos)
            if rendimiento is None:
                continue
            lineas.append(f"  variacion ultimos {periodos} periodos: {rendimiento:+.2%}")

        cierres = view.closes(symbol, min(VENTANAS[-1], 30))
        if cierres:
            lineas.append(f"  serie reciente (normalizada): {_normalizar(cierres)}")

        lineas.append("")

    return "\n".join(lineas).rstrip()


def symbol_map(view: UniverseView) -> dict[str, str]:
    """Qué letra corresponde a cada activo real.

    El LLM responde con letras; hay que poder traducir de vuelta. Se mantiene fuera del texto
    del prompt a propósito: si el mapa viajara con las instrucciones, anonimizar no serviría.
    """
    return {_etiqueta(i): s for i, s in enumerate(view.symbols)}


def _etiqueta(indice: int) -> str:
    """A, B, ... Z, AA, AB..."""
    letras = ""
    numero = indice
    while True:
        letras = chr(ord("A") + numero % 26) + letras
        numero = numero // 26 - 1
        if numero < 0:
            return letras


def _normalizar(cierres: tuple[float, ...]) -> str:
    """Reescala para que el último valga 100.

    Un precio absoluto es una pista: 45.000 dice "Bitcoin" y 180 dice "una acción grande".
    Normalizar quita esa pista y además hace comparables activos de escalas distintas.
    """
    ultimo = cierres[-1]
    if ultimo == 0:  # pragma: no cover - un cierre a cero no llega hasta aqui
        return "sin datos"
    return " ".join(f"{c / ultimo * 100:.1f}" for c in cierres)
