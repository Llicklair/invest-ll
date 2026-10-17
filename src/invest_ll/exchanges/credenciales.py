"""Las claves de cada exchange y red, en el almacén de credenciales del sistema.

Generaliza `live/credenciales.py` (solo Binance) a cualquier exchange con ficha: en Windows, el
Administrador de credenciales (la librería `keyring`). **Nunca en un fichero ni en el
repositorio**, y nunca de vuelta por ninguna ruta de la API: el panel solo sabe si están.

Cada campo se guarda aparte, con el nombre `<exchange>-<red>:<campo>` en el servicio `invest-ll`.
La clave y el secreto se llaman como en v2 (`clave`, `secreto`), así que **Binance lee las que ya
se guardaron desde Ajustes → Conexión** (y v2 las de aquí): es el mismo sitio.

`ClavesExchange` no se deja imprimir (su `repr` no enseña nada): una clave no puede acabar en un
log por un `print` o una traza de error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import keyring
import keyring.errors

from invest_ll.live.credenciales import SERVICIO, AlmacenDeClavesError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping

    from invest_ll.exchanges.conector import Red
    from invest_ll.exchanges.fichas import Ficha

ALIAS: Final[dict[str, str]] = {"apiKey": "clave", "secret": "secreto"}
"""Los nombres de v2 en el almacén: así Binance sigue leyendo las claves que ya existían."""

QUE_DISTINGUEN: Final = ("apiKey", "secret", "privateKey")
"""Si coincide alguno de estos, son las mismas claves. La dirección de la cartera de Hyperliquid
es la misma en las dos redes (es tu cartera) y la passphrase de OKX se puede repetir: no cuentan."""

DIRECCION: Final = re.compile(r"0x[0-9a-fA-F]{40}")
CLAVE_PRIVADA: Final = re.compile(r"(0x)?[0-9a-fA-F]{64}")


@dataclass(frozen=True, slots=True)
class ClavesExchange:
    """Los valores de las claves, por `Campo.clave` ('apiKey', 'secret'...)."""

    valores: Mapping[str, str] = field(repr=False)

    def __getitem__(self, campo: str) -> str:
        return self.valores[campo]

    def mismas_que(self, otras: ClavesExchange) -> bool:
        """Si son las mismas claves (coincide la clave de la API, el secreto o la privada)."""
        return any(
            self.valores.get(c) and self.valores.get(c) == otras.valores.get(c)
            for c in QUE_DISTINGUEN
        )


def _usuario(exchange: str, red: Red, campo: str) -> str:
    return f"{exchange}-{red}:{ALIAS.get(campo, campo)}"


def normalizar(ficha: Ficha, valores: Mapping[str, str]) -> ClavesExchange:
    """Las claves tal como se guardan, comprobadas. `ValueError` en llano si algo no vale."""
    conocidos = {c.clave for c in ficha.campos}
    sobran = sorted(set(valores) - conocidos)
    if sobran:
        raise ValueError(f"{ficha.nombre} no usa {', '.join(sobran)}.")
    limpios: dict[str, str] = {}
    for campo in ficha.campos:
        valor = (valores.get(campo.clave) or "").strip()
        if not valor:
            raise ValueError(f"Falta «{campo.nombre}».")
        if "-----BEGIN" in valor:
            # Una clave en PEM (Coinbase) pegada en una línea trae los saltos escritos como \n.
            valor = valor.replace("\\n", "\n") + ("\n" if not valor.endswith("\n") else "")
        elif any(c.isspace() for c in valor):
            raise ValueError(f"«{campo.nombre}» lleva espacios: cópiala otra vez, entera.")
        limpios[campo.clave] = valor
    _comprobar_formato(ficha, limpios)
    return ClavesExchange(valores=limpios)


def _comprobar_formato(ficha: Ficha, valores: Mapping[str, str]) -> None:
    if ficha.id == "hyperliquid":
        if not DIRECCION.fullmatch(valores["walletAddress"]):
            raise ValueError(
                "La dirección de la cartera tiene que ser 0x seguido de 40 caracteres "
                "hexadecimales (la de tu cartera, la principal)."
            )
        if not CLAVE_PRIVADA.fullmatch(valores["privateKey"]):
            raise ValueError(
                "La clave privada de la API wallet tiene que ser 64 caracteres hexadecimales "
                "(con o sin 0x delante)."
            )
    if ficha.id == "coinbase" and not valores["secret"].startswith("-----BEGIN"):
        raise ValueError(
            "La clave privada de Coinbase empieza por -----BEGIN EC PRIVATE KEY-----. Si la "
            "tuya no, es de tipo Ed25519, que Advanced Trade no admite: crea otra con ECDSA."
        )


def leer(ficha: Ficha, red: Red) -> ClavesExchange | None:
    """Las claves guardadas de ese exchange y red, o `None` si falta alguna (o el almacén no está
    disponible)."""
    valores: dict[str, str] = {}
    try:
        for campo in ficha.campos:
            valor = keyring.get_password(SERVICIO, _usuario(ficha.id, red, campo.clave))
            if not valor:
                return None
            valores[campo.clave] = valor
    except keyring.errors.KeyringError:
        return None
    return ClavesExchange(valores=valores)


def guardar(ficha: Ficha, red: Red, claves: ClavesExchange) -> None:
    try:
        for campo in ficha.campos:
            keyring.set_password(
                SERVICIO, _usuario(ficha.id, red, campo.clave), claves[campo.clave]
            )
    except keyring.errors.KeyringError as error:
        raise AlmacenDeClavesError(
            "no se pudieron guardar las claves en el almacén de credenciales del sistema "
            f"({type(error).__name__})"
        ) from None


def borrar(ficha: Ficha, red: Red) -> bool:
    """Borra las claves de ese exchange y red. `False` si no había ninguna."""
    borrada = False
    for campo in ficha.campos:
        try:
            keyring.delete_password(SERVICIO, _usuario(ficha.id, red, campo.clave))
            borrada = True
        except keyring.errors.PasswordDeleteError:
            continue
        except keyring.errors.KeyringError as error:
            raise AlmacenDeClavesError(
                f"no se pudieron borrar las claves del almacén ({type(error).__name__})"
            ) from None
    return borrada
