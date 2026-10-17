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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from types import TracebackType

ERRORES_DEL_DOMINIO = (InvestLLError, ValueError, ArithmeticError)


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
