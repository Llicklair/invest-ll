"""Las claves de Binance que se pegan en el panel, en el almacén de credenciales del sistema.

En Windows es el Administrador de credenciales (la librería `keyring` elige el almacén de cada
sistema). **Nunca en un fichero ni en el repositorio**, y nunca de vuelta por ninguna ruta de la
API: el panel solo sabe si están o no.

Las variables de entorno de docs/operar-de-verdad.md siguen mandando (`modo_panel`); esto es la
alternativa para quien no quiere pegarlas en una terminal cada vez. La línea de comandos no lee
de aquí: sigue leyendo solo del entorno.

`Claves` no se deja imprimir: su `repr` no enseña nada, para que una clave no acabe en un log por
un `print` o una traza de error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

import keyring
import keyring.errors

from invest_ll.errors import InvestLLError

Red = Literal["pruebas", "real"]
REDES: Final[tuple[Red, ...]] = ("pruebas", "real")
SERVICIO: Final = "invest-ll"


class AlmacenDeClavesError(InvestLLError):
    """El almacén de credenciales no está disponible o no deja escribir."""


@dataclass(frozen=True, slots=True)
class Claves:
    clave: str = field(repr=False)
    secreto: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.clave.strip() or not self.secreto.strip():
            raise ValueError("la clave y el secreto no pueden estar vacíos")


def _usuario(red: Red, parte: str) -> str:
    return f"binance-{red}:{parte}"


def leer(red: Red) -> Claves | None:
    """Las claves guardadas de esa red, o `None` si no hay (o el almacén no está disponible)."""
    try:
        clave = keyring.get_password(SERVICIO, _usuario(red, "clave"))
        secreto = keyring.get_password(SERVICIO, _usuario(red, "secreto"))
    except keyring.errors.KeyringError:
        return None
    if not clave or not secreto:
        return None
    return Claves(clave=clave, secreto=secreto)


def guardar(red: Red, claves: Claves) -> None:
    try:
        keyring.set_password(SERVICIO, _usuario(red, "clave"), claves.clave)
        keyring.set_password(SERVICIO, _usuario(red, "secreto"), claves.secreto)
    except keyring.errors.KeyringError as error:
        # El mensaje de keyring no lleva la clave, pero tampoco hace falta: basta con el tipo.
        raise AlmacenDeClavesError(
            "no se pudieron guardar las claves en el almacén de credenciales del sistema "
            f"({type(error).__name__})"
        ) from None


def borrar(red: Red) -> bool:
    """Borra las claves de esa red. `False` si no había ninguna."""
    borrada = False
    for parte in ("clave", "secreto"):
        try:
            keyring.delete_password(SERVICIO, _usuario(red, parte))
            borrada = True
        except keyring.errors.PasswordDeleteError:
            continue
        except keyring.errors.KeyringError as error:
            raise AlmacenDeClavesError(
                f"no se pudieron borrar las claves del almacén ({type(error).__name__})"
            ) from None
    return borrada
