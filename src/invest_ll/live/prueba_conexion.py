"""Probar unas claves de Binance: leer el saldo y, si falla, decir en llano qué revisar.

**No envía ninguna orden.** Leer el saldo es la llamada más barata que exige claves válidas: si
el exchange las acepta aquí, las aceptará al enviar. Es lo mismo que hace `scripts/testnet.ps1`,
pero desde el panel y para las dos redes.

`leer_saldo` es la única función que habla con el exchange y está aislada a propósito: los tests
la sustituyen (la suite corre sin red) y `explicar_fallo`, que traduce cada error a lo que hay que
mirar, se prueba sola con errores construidos a mano.

Los fallos típicos, en el orden en que suelen pasar:

- La clave no es HMAC-SHA256 (Binance deja elegir Ed25519 o RSA, y con ellas solo hay un "secret"
  que en realidad es una clave privada): el exchange rechaza la firma.
- La clave es de la otra red: las de testnet.binance.vision no valen en Binance, ni al revés.
- No hay conexión, o la hora del ordenador está desajustada.

Ningún mensaje lleva la clave ni el secreto: se usan `mensaje_seguro` y el nombre del tipo de error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, cast

from invest_ll.live.ccxt_broker import build_exchange, mensaje_seguro
from invest_ll.live.mode import Real, Testnet

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from invest_ll.live.credenciales import Claves, Red

MONEDAS_DE_REFERENCIA: Final = ("USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "EUR")
"""La red de pruebas reparte saldo en cientos de monedas: estas van primero."""

NOMBRE_RED: Final[dict[Red, str]] = {
    "pruebas": "la red de pruebas (testnet.binance.vision)",
    "real": "Binance (dinero real)",
}
OTRA_RED: Final[dict[Red, str]] = {
    "pruebas": "son de tu cuenta real de Binance, no de testnet.binance.vision",
    "real": "son de la red de pruebas (testnet.binance.vision), no de tu cuenta real",
}


class RedEquivocadaError(Exception):
    """El exchange construido no apunta a la red pedida. Nunca debería pasar; si pasa, se para."""


@dataclass(frozen=True, slots=True)
class Prueba:
    ok: bool
    detalle: str
    saldo: tuple[tuple[str, Decimal], ...] = ()


def leer_saldo(red: Red, claves: Claves) -> dict[str, Decimal]:
    """El saldo libre de esa red con esas claves. Habla con el exchange: los tests la sustituyen."""
    modo = (
        Testnet(key=claves.clave, secret=claves.secreto)
        if red == "pruebas"
        else Real(key=claves.clave, secret=claves.secreto)
    )
    exchange = build_exchange(modo)
    if red == "pruebas":
        destino = str(getattr(exchange, "urls", {}).get("api", "")).lower()
        if "testnet" not in destino and "vision" not in destino:
            raise RedEquivocadaError(destino[:80])
    crudo = exchange.fetch_balance()
    libres: object = crudo.get("free") or {}
    if not isinstance(libres, dict):  # pragma: no cover - respuesta inesperada
        return {}
    # Frontera con ccxt, que no publica tipos: como en CcxtBroker.balance, todo pasa por str
    # antes de Decimal porque son cantidades de dinero.
    entradas = cast("dict[str, Any]", libres)
    return {
        str(moneda): Decimal(str(cantidad)) for moneda, cantidad in entradas.items() if cantidad
    }


def ordenar_saldo(saldo: dict[str, Decimal]) -> tuple[tuple[str, Decimal], ...]:
    """Las monedas con saldo: primero las de referencia, después el resto por orden alfabético."""
    con_saldo = {m: c for m, c in saldo.items() if c > 0}
    primero = [(m, con_saldo[m]) for m in MONEDAS_DE_REFERENCIA if m in con_saldo]
    resto = sorted((m, c) for m, c in con_saldo.items() if m not in MONEDAS_DE_REFERENCIA)
    return tuple(primero + resto)


def _codigo_binance(texto: str) -> int | None:
    """El código de error de Binance (`"code":-2015`) si viene en el mensaje."""
    encontrado = re.search(r'"code"\s*:\s*(-?\d+)', texto)
    return int(encontrado.group(1)) if encontrado else None


def explicar_fallo(error: Exception, red: Red) -> str:
    """Qué revisar, en llano, según el tipo de error de ccxt (por nombre, sin importar ccxt)."""
    tipos = {t.__name__ for t in type(error).__mro__}
    texto = str(error)
    codigo = _codigo_binance(texto)
    donde = NOMBRE_RED[red]

    if "RedEquivocadaError" in tipos:
        return (
            "La conexión no apunta a la red de pruebas, así que no se ha probado nada. Es un fallo "
            "del programa, no de tus claves: avisa antes de seguir."
        )
    if "InvalidNonce" in tipos or codigo == -1021:
        return (
            "Binance rechaza la petición porque la hora de tu ordenador no coincide con la suya. "
            "Sincroniza el reloj de Windows (Configuración, Hora e idioma, Sincronizar ahora) y "
            "vuelve a probar."
        )
    if "AuthenticationError" in tipos or "PermissionDenied" in tipos or codigo in (-2014, -2015):
        if codigo == -2014:
            causa = (
                "El formato de la clave no es válido: revisa que la copiaste entera, sin espacios, "
                "y que es de tipo HMAC-SHA256 (las Ed25519 o RSA no sirven aquí)."
            )
        else:
            causa = (
                "Las causas más frecuentes, por orden: 1) las claves "
                f"{OTRA_RED[red]}; 2) no son de tipo HMAC-SHA256 (las Ed25519 o RSA no sirven "
                "aquí: solo hay sitio para una clave y un secreto); 3) la clave tiene "
                "restringida la IP y esta no es la tuya, o le falta el permiso de lectura."
            )
        return f"{donde.capitalize()} rechaza las claves. {causa}"
    if tipos & {"NetworkError", "RequestTimeout", "ExchangeNotAvailable", "DDoSProtection"}:
        return (
            f"No hay conexión con {donde}: revisa tu conexión a internet y vuelve a probar. Si "
            "es la red de pruebas, a veces está caída o se está reiniciando (pasa una vez al mes)."
        )
    return f"No se pudo leer el saldo de {donde}: {type(error).__name__}: {mensaje_seguro(error)}"


def probar(
    red: Red,
    claves: Claves | None,
    lector: Callable[[Red, Claves], dict[str, Decimal]] = leer_saldo,
) -> Prueba:
    """Lee el saldo y lo cuenta en llano. No envía nada."""
    if claves is None:
        return Prueba(
            ok=False,
            detalle=f"No hay claves de {'la red de pruebas' if red == 'pruebas' else 'dinero real'}"
            " guardadas: pégalas primero.",
        )
    try:
        saldo = ordenar_saldo(lector(red, claves))
    except Exception as error:
        return Prueba(ok=False, detalle=explicar_fallo(error, red))
    if not saldo:
        vacio = (
            "Las claves funcionan, pero la cuenta de pruebas no tiene saldo: la red de pruebas "
            "se borra más o menos una vez al mes y reparte saldo nuevo al volver a entrar."
            if red == "pruebas"
            else "Las claves funcionan, pero tu cuenta no tiene saldo."
        )
        return Prueba(ok=True, detalle=vacio)
    ficticio = " (dinero ficticio)" if red == "pruebas" else ""
    return Prueba(
        ok=True,
        detalle=f"Conexión correcta con {NOMBRE_RED[red]}: {len(saldo)} monedas con saldo{ficticio}.",
        saldo=saldo,
    )
