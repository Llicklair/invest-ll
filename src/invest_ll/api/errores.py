"""Cómo se convierte un error del dominio en una respuesta HTTP. Un sitio, las mismas reglas.

- Lo que el dominio rechaza (`InvestLLError`, `ValueError`, una cifra imposible) sale como 422 con
  su texto, que está escrito para enseñárselo al operador. Es lo que el panel de Streamlit pintaba
  con `st.error`.
- Lo que no existe sale como 404: desarmar un trigger inexistente no es un éxito.
- La pausa de entradas es un 409 y enviar sin un modo que lo permita, un 403.

Los `ValueError` no se capturan con un manejador global a propósito: la validación de Pydantic
también es un `ValueError`, y convertir en 422 un modelo de respuesta mal construido escondería un
fallo del programa detrás de un "dato no válido". Se capturan solo alrededor de las llamadas al
dominio, con `del_dominio`.

**Todos los errores tienen la misma forma**, `{"detail": "texto en llano"}` (`schemas.Error`):
también los de validación de FastAPI, que traen una lista técnica en inglés y aquí se cuentan en
castellano (`explicar_validacion`: qué campo y qué le pasa), y los que FastAPI escribe solo ("Not
Found", "Method Not Allowed"). Los manejadores están en `app.py`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from fastapi import HTTPException

from invest_ll.api.schemas import Error
from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence
    from types import TracebackType

ERRORES_DEL_DOMINIO = (InvestLLError, ValueError, ArithmeticError)

EN_LLANO: Final[dict[str, str]] = {
    "Not Found": "No existe esa dirección en el panel.",
    "Method Not Allowed": "Esa dirección del panel no admite esta operación.",
}
"""Los textos que FastAPI y Starlette escriben solos, en inglés."""

_QUE_LE_PASA: Final[dict[str, str]] = {
    "missing": "falta {donde}",
    "json_invalid": "el cuerpo de la petición no es un JSON válido",
    "json_type": "el cuerpo de la petición no es un JSON válido",
    "decimal_parsing": "{donde} tiene que ser un número",
    "decimal_type": "{donde} tiene que ser un número",
    "float_parsing": "{donde} tiene que ser un número",
    "float_type": "{donde} tiene que ser un número",
    "finite_number": "{donde} tiene que ser un número normal (no infinito)",
    "int_parsing": "{donde} tiene que ser un número entero",
    "int_type": "{donde} tiene que ser un número entero",
    "int_from_float": "{donde} tiene que ser un número entero, sin decimales",
    "bool_parsing": "{donde} tiene que ser sí o no (true o false)",
    "bool_type": "{donde} tiene que ser sí o no (true o false)",
    "date_parsing": "{donde} tiene que ser una fecha (AAAA-MM-DD)",
    "date_type": "{donde} tiene que ser una fecha (AAAA-MM-DD)",
    "date_from_datetime_parsing": "{donde} tiene que ser una fecha (AAAA-MM-DD)",
    "date_from_datetime_inexact": "{donde} tiene que ser una fecha, sin hora",
    "datetime_parsing": "{donde} tiene que ser una fecha con hora",
    "datetime_type": "{donde} tiene que ser una fecha con hora",
    "string_type": "{donde} tiene que ser un texto",
    "string_too_short": "{donde} es demasiado corto: al menos {min_length} caracteres",
    "string_too_long": "{donde} es demasiado largo: como mucho {max_length} caracteres",
    "too_short": "{donde} necesita al menos {min_length} {elementos}",
    "too_long": "{donde} admite como mucho {max_length} {elementos}",
    "greater_than": "{donde} tiene que ser mayor que {gt}",
    "greater_than_equal": "{donde} tiene que ser {ge} o más",
    "less_than": "{donde} tiene que ser menor que {lt}",
    "less_than_equal": "{donde} no puede pasar de {le}",
    "decimal_max_digits": "{donde} tiene demasiadas cifras",
    "decimal_max_places": "{donde} tiene demasiados decimales",
    "literal_error": "{donde} tiene que ser uno de estos: {expected}",
    "enum": "{donde} tiene que ser uno de estos: {expected}",
    "list_type": "{donde} tiene que ser una lista",
    "dict_type": "{donde} tiene que ser un objeto con sus campos",
    "model_type": "{donde} tiene que ser un objeto con sus campos",
    "model_attributes_type": "{donde} tiene que ser un objeto con sus campos",
    "extra_forbidden": "sobra {donde}",
}
"""Qué le pasa a un campo, por el `type` del error de Pydantic. Lo demás: "no es válido"."""

_CUANDO: Final[dict[int, str]] = {
    403: "No se permite en este modo (enviar una orden en simulación)",
    404: "No existe (una estrategia, un plan, unas claves...)",
    409: (
        "Choca con el estado de ahora: el modo lo fija el entorno, la pausa de compras, una "
        "actualización de datos ya en marcha"
    ),
    422: (
        "Datos que no valen o que el dominio rechaza, explicados en llano (también los de "
        "validación: qué campo y qué le pasa)"
    ),
}

RESPUESTAS_DE_ERROR: Final[dict[int | str, dict[str, Any]]] = {
    codigo: {"model": Error, "description": cuando} for codigo, cuando in _CUANDO.items()
}
"""Las respuestas de error de todas las rutas (`rutas.router`), con su única forma.

Sin esto, el OpenAPI declaraba el 422 de validación de FastAPI (una lista técnica que la API ya
no devuelve) y no declaraba los demás."""

RESPUESTAS_DE_ERROR_EN_JSON: Final[dict[int | str, dict[str, Any]]] = {
    codigo: {
        "description": cuando,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }
    for codigo, cuando in _CUANDO.items()
}
"""Lo mismo para una ruta que no responde JSON cuando va bien (el estudio en HTML): FastAPI
declararía sus errores con el tipo de la ruta, y salen en JSON como todos."""


class _Traductor:
    """El `with` de `del_dominio`. Su `__exit__` devuelve `None`: nunca se traga un error."""

    __slots__ = ("_prefijo",)

    def __init__(self, prefijo: str) -> None:
        self._prefijo = prefijo

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        if isinstance(error, ERRORES_DEL_DOMINIO):
            raise HTTPException(status_code=422, detail=f"{self._prefijo}{error}") from error


def del_dominio(prefijo: str = "") -> _Traductor:
    """Lo que el dominio rechace dentro del bloque sale como 422, con `prefijo` delante."""
    return _Traductor(prefijo)


# Devuelven la excepcion en vez de lanzarla para que se lea `raise no_encontrado(...)`: quien lee
# la ruta ve que ahi acaba, y los linters tambien.


def invalido(detalle: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detalle)


def no_encontrado(detalle: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detalle)


def en_pausa(detalle: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detalle)


def prohibido(detalle: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detalle)


def conflicto(detalle: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detalle)


# -- Los errores de validación de FastAPI, en llano ----------------------------------------------


def explicar_validacion(errores: Sequence[Mapping[str, Any]]) -> str:
    """'Revisa los datos: falta «fecha»; «cantidad» tiene que ser un número.'

    Uno por campo y en el orden en que llegan; los repetidos (un mismo campo que falla dos
    comprobaciones de una unión de tipos) se dicen una vez.
    """
    frases = list(dict.fromkeys(_frase(e) for e in errores)) or ["la petición no es válida"]
    return "Revisa los datos: " + "; ".join(frases) + "."


def _frase(error: Mapping[str, Any]) -> str:
    tipo = str(error.get("type", ""))
    contexto: Mapping[str, Any] = error.get("ctx") or {}
    donde = _donde(tuple(error.get("loc") or ()))
    if tipo == "value_error":
        # Un validador propio: su mensaje ya está escrito para el operador.
        mensaje = str(error.get("msg", "")).removeprefix("Value error, ")
        return f"{donde}: {mensaje}"
    plantilla = _QUE_LE_PASA.get(tipo)
    if plantilla is None:
        return f"{donde} no es válido"
    valores = {clave: _cifra_o_texto(clave, valor) for clave, valor in contexto.items()}
    cuantos = contexto.get("min_length", contexto.get("max_length"))
    valores["elementos"] = "elemento" if cuantos == 1 else "elementos"
    try:
        return plantilla.format(donde=donde, **valores)
    except (KeyError, IndexError):  # pragma: no cover - un contexto distinto del esperado
        return f"{donde} no es válido"


def _donde(loc: tuple[object, ...]) -> str:
    """'«cantidad»', '«porcentaje» del elemento 2 de «reparto»', 'el parámetro «tramo»'."""
    origen = str(loc[0]) if loc else "body"
    partes = loc[1:] if origen in ("body", "query", "path", "header", "cookie") else loc
    if not partes:
        return "el cuerpo de la petición"
    texto = ""
    for parte in partes:
        if isinstance(parte, int):
            texto = f"el elemento {parte + 1}" + (f" de {texto}" if texto else "")
        elif not texto:
            texto = f"«{parte}»"
        elif texto.startswith("el elemento"):
            texto = f"«{parte}» del {texto.removeprefix('el ')}"
        else:
            texto = f"«{parte}» de {texto}"
    if origen == "query":
        return f"el parámetro {texto}"
    if origen == "path":
        return f"{texto} en la dirección"
    return texto


def _cifra_o_texto(clave: str, valor: object) -> str:
    if clave == "expected":
        return str(valor).replace(" or ", " o ")
    if clave in ("min_length", "max_length") and isinstance(valor, int):
        return str(valor)
    try:
        cifra = Decimal(str(valor))
    except InvalidOperation:
        return str(valor)
    if not cifra.is_finite():
        return str(valor)
    texto = format(cifra.normalize(), "f")
    return texto.replace(".", ",")
