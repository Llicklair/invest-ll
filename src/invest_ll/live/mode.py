"""El modo de operación. **Tipos distintos, no un booleano.**

Esta es la pieza donde el Principio I deja de ser una promesa y pasa a ser algo que el
comprobador de tipos impone. Un flag `real: bool` sería una comprobación en tiempo de ejecución
que alguien puede olvidar escribir; tres tipos distintos hacen que una función que acepta `Real`
**no pueda** recibir `Simulation`, y que el error salte antes de ejecutar nada.

`Simulation` es lo que se obtiene sin configurar nada. No por convención: es el valor por defecto
de la función que resuelve el modo, y hay un test que lo comprueba desde un entorno vacío.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from invest_ll.errors import InvestLLError

# Variables de entorno. Las de pruebas y las reales son DISTINTAS a proposito: asi usar unas
# donde tocan las otras no es un descuido silencioso, es un fallo (FR-048).
VAR_MODO: Final = "INVEST_LL_MODE"
VAR_CLAVE_PRUEBAS: Final = "INVEST_LL_TESTNET_KEY"
VAR_SECRETO_PRUEBAS: Final = "INVEST_LL_TESTNET_SECRET"
VAR_CLAVE_REAL: Final = "INVEST_LL_LIVE_KEY"
VAR_SECRETO_REAL: Final = "INVEST_LL_LIVE_SECRET"

# Marca en disco de que ya se ha operado en la red de pruebas de un mercado (FR-047).
VAR_TESTNET_HECHA: Final = "INVEST_LL_TESTNET_VERIFIED"


class ModeError(InvestLLError):
    """El modo pedido no se puede activar."""


class CredentialError(InvestLLError):
    """Faltan credenciales, o son las del otro modo."""


@dataclass(frozen=True, slots=True)
class Simulation:
    """Nada sale al exterior. El estado por defecto."""

    @property
    def name(self) -> str:
        return "simulacion"

    @property
    def sends_real_orders(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Testnet:
    """Órdenes reales contra dinero ficticio."""

    # pytest intenta recolectar cualquier clase que empiece por Test; esto le dice que no.
    __test__ = False

    key: str
    secret: str

    @property
    def name(self) -> str:
        return "pruebas"

    @property
    def sends_real_orders(self) -> bool:
        """Salen de verdad al exchange, aunque el dinero no lo sea."""
        return True


@dataclass(frozen=True, slots=True)
class Real:
    """Dinero de verdad."""

    key: str
    secret: str

    @property
    def name(self) -> str:
        return "REAL"

    @property
    def sends_real_orders(self) -> bool:
        return True


OperatingMode = Simulation | Testnet | Real


def resolve_mode(env: dict[str, str] | None = None) -> OperatingMode:
    """Determina el modo a partir del entorno.

    **Sin nada configurado devuelve `Simulation`.** Ese es el requisito FR-025 y el motivo de que
    esta función tenga un valor por defecto en vez de exigir un argumento: lo seguro tiene que ser
    lo que pasa cuando nadie hace nada.
    """
    entorno = dict(os.environ) if env is None else env
    pedido = entorno.get(VAR_MODO, "").strip().lower()

    if pedido in ("", "simulation", "simulacion"):
        return Simulation()

    if pedido == "testnet":
        return Testnet(
            key=_exigir(entorno, VAR_CLAVE_PRUEBAS, "pruebas"),
            secret=_exigir(entorno, VAR_SECRETO_PRUEBAS, "pruebas"),
        )

    if pedido == "real":
        _exigir_testnet_previa(entorno)
        clave = _exigir(entorno, VAR_CLAVE_REAL, "reales")
        secreto = _exigir(entorno, VAR_SECRETO_REAL, "reales")
        _rechazar_credenciales_cruzadas(entorno, clave)
        return Real(key=clave, secret=secreto)

    raise ModeError(
        f"modo desconocido {pedido!r}. Opciones: simulation (por defecto), testnet, real."
    )


def _exigir(entorno: dict[str, str], variable: str, cual: str) -> str:
    valor = entorno.get(variable, "").strip()
    if not valor:
        raise CredentialError(
            f"falta {variable}: el modo pedido necesita las credenciales {cual}. "
            "Se leen del entorno y nunca se guardan en el repositorio."
        )
    return valor


def _exigir_testnet_previa(entorno: dict[str, str]) -> None:
    """FR-047: antes de dinero real hay que haber operado en pruebas.

    Es donde se descubren los fallos de ejecución sin pagarlos.
    """
    if entorno.get(VAR_TESTNET_HECHA, "").strip().lower() not in ("1", "true", "si", "yes"):
        raise ModeError(
            "no se puede operar con dinero real sin haber operado antes en la red de pruebas. "
            f"Hazlo con {VAR_MODO}=testnet y despues marca {VAR_TESTNET_HECHA}=1."
        )


def _rechazar_credenciales_cruzadas(entorno: dict[str, str], clave_real: str) -> None:
    """Usar la clave de pruebas donde toca la real falla de forma visible (FR-048)."""
    clave_pruebas = entorno.get(VAR_CLAVE_PRUEBAS, "").strip()
    if clave_pruebas and clave_pruebas == clave_real:
        raise CredentialError(
            "la credencial de dinero real coincide con la de pruebas. "
            "Tienen que ser distintas: si son la misma, no hay separacion real entre modos."
        )
