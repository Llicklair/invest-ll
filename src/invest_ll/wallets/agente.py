"""La wallet agente de Hyperliquid: operar con tu wallet sin que el panel pueda retirar tus fondos
(docs/panel-v5.md §5).

Hyperliquid deja que una wallet autorice a otra ("agente", o API wallet) a operar en su nombre: el
agente firma órdenes, pero NO puede retirar ni mover fondos. El camino:

1. `preparar`: se crea la clave del agente (aquí, en memoria; nunca sale) y los datos tipados
   EIP-712 de la acción `approveAgent`, como los firma el SDK oficial de Hyperliquid
   (hyperliquid-python-sdk 0.24.0, `utils/signing.py`: `sign_agent` y `user_signed_payload`). La
   cadena con que se firma (`signatureChainId`) es la que tenga la wallet: el SDK dice que puede ser
   cualquiera, y MetaMask exige que coincida con la activa.
2. La wallet del navegador firma esos datos (`eth_signTypedData_v4`).
3. `confirmar`: se comprueba que la firma es de esa dirección (antes de mandar nada), se envía a
   `/exchange` de Hyperliquid y, si la acepta, se devuelve la clave del agente para guardarla en el
   almacén de claves (como las de cualquier exchange). Lo preparado caduca a los 10 minutos.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, cast

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils.address import to_checksum_address

from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from invest_ll.wallets.red import RedHl

NOMBRE_AGENTE: Final = "invest-ll"
PRIMARIO: Final = "HyperliquidTransaction:ApproveAgent"
TIPOS_APPROVE_AGENT: Final = [
    {"name": "hyperliquidChain", "type": "string"},
    {"name": "agentAddress", "type": "address"},
    {"name": "agentName", "type": "string"},
    {"name": "nonce", "type": "uint64"},
]
TIPOS_DOMINIO: Final = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
CADUCA: Final = timedelta(minutes=10)


class AgenteError(InvestLLError):
    """Algo del camino de la wallet agente no vale. El texto, en llano."""


@dataclass(frozen=True, slots=True)
class Preparado:
    direccion: str
    red: RedHl
    chain_id: int
    nonce: int
    agente: str
    """La dirección del agente (pública)."""
    clave_agente: str
    """Su clave privada: solo en memoria hasta confirmar, y luego al almacén de claves."""
    creado: datetime


_cerrojo = threading.Lock()
_preparados: dict[tuple[str, str, int], Preparado] = {}


def cadena_hyperliquid(red: RedHl) -> str:
    return "Mainnet" if red == "real" else "Testnet"


def datos_tipados(red: RedHl, chain_id: int, agente: str, nonce: int) -> dict[str, Any]:
    """Lo que firma la wallet, en el formato de `eth_signTypedData_v4` (el de `user_signed_payload`
    del SDK, con solo los campos que firma)."""
    return {
        "domain": {
            "name": "HyperliquidSignTransaction",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        },
        "types": {PRIMARIO: TIPOS_APPROVE_AGENT, "EIP712Domain": TIPOS_DOMINIO},
        "primaryType": PRIMARIO,
        "message": {
            "hyperliquidChain": cadena_hyperliquid(red),
            "agentAddress": agente,
            "agentName": NOMBRE_AGENTE,
            "nonce": nonce,
        },
    }


def direccion_valida(direccion: str) -> str:
    """La dirección con su checksum (EIP-55). `AgenteError` en llano si no es una."""
    try:
        return to_checksum_address(direccion.strip())
    except ValueError as error:
        raise AgenteError(
            f"«{direccion.strip()[:60]}» no es una dirección de wallet (0x y 40 caracteres)."
        ) from error


def preparar(
    direccion: str, red: RedHl, chain_id: int, *, ahora: datetime | None = None
) -> Preparado:
    """Crea el agente y deja preparada su autorización para esa wallet."""
    if chain_id <= 0:
        raise AgenteError("La wallet no dijo en qué cadena está.")
    momento = ahora or datetime.now(UTC)
    cuenta = Account.from_key("0x" + secrets.token_hex(32))
    p = Preparado(
        direccion=direccion_valida(direccion),
        red=red,
        chain_id=chain_id,
        nonce=int(momento.timestamp() * 1000),
        agente=cuenta.address,
        clave_agente=cuenta.key.hex()
        if cuenta.key.hex().startswith("0x")
        else "0x" + cuenta.key.hex(),
        creado=momento,
    )
    with _cerrojo:
        for k, v in list(_preparados.items()):
            if momento - v.creado > CADUCA:
                del _preparados[k]
        _preparados[(p.direccion.lower(), red, p.nonce)] = p
    return p


def firma_a_rsv(firma: str) -> dict[str, Any]:
    """La firma de la wallet (0x + 130 hex) como la espera Hyperliquid: r, s (hex) y v (27/28)."""
    h = firma.strip().removeprefix("0x")
    if len(h) != 130 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise AgenteError(
            "La firma de la wallet no tiene la forma de una firma (0x y 130 caracteres)."
        )
    v = int(h[128:130], 16)
    return {"r": "0x" + h[0:64], "s": "0x" + h[64:128], "v": v + 27 if v < 27 else v}


def quien_firmo(datos: dict[str, Any], firma: str) -> str:
    """La dirección que firmó esos datos tipados."""
    rsv = firma_a_rsv(firma)
    mensaje = encode_typed_data(full_message=datos)
    return Account.recover_message(mensaje, vrs=(rsv["v"], int(rsv["r"], 16), int(rsv["s"], 16)))


def confirmar(
    direccion: str,
    red: RedHl,
    nonce: int,
    firma: str,
    *,
    enviar: Callable[[RedHl, dict[str, Any]], Any],
    ahora: datetime | None = None,
) -> Preparado:
    """Comprueba la firma, la manda a Hyperliquid y devuelve lo preparado (con la clave del agente
    para guardarla). `AgenteError` en llano si algo no vale; entonces no se guarda nada."""
    clave = (direccion_valida(direccion).lower(), red, nonce)
    with _cerrojo:
        p = _preparados.pop(clave, None)
    momento = ahora or datetime.now(UTC)
    if p is None or momento - p.creado > CADUCA:
        raise AgenteError(
            "Esa autorización ya no vale (caduca a los 10 minutos): vuelve a empezar."
        )
    datos = datos_tipados(p.red, p.chain_id, p.agente, p.nonce)
    if quien_firmo(datos, firma).lower() != p.direccion.lower():
        raise AgenteError(
            "La firma no es de esa wallet: no se ha enviado nada a Hyperliquid. Firma con la cuenta "
            "que conectaste."
        )
    accion = {
        "type": "approveAgent",
        "signatureChainId": hex(p.chain_id),
        "hyperliquidChain": cadena_hyperliquid(p.red),
        "agentAddress": p.agente,
        "agentName": NOMBRE_AGENTE,
        "nonce": p.nonce,
    }
    respuesta: object = enviar(
        p.red,
        {
            "action": accion,
            "nonce": p.nonce,
            "signature": firma_a_rsv(firma),
            "vaultAddress": None,
            "expiresAfter": None,
        },
    )
    if not isinstance(respuesta, dict):
        raise AgenteError(f"Hyperliquid no aceptó la autorización: {respuesta!s}")
    datos = cast("dict[str, object]", respuesta)
    if datos.get("status") != "ok":
        raise AgenteError(f"Hyperliquid no aceptó la autorización: {datos.get('response')!s}")
    return p
