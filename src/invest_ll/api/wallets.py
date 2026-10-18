"""Wallets del navegador (docs/panel-v5.md §5): conectar (solo la dirección), ver sus saldos y
autorizar con ellas la wallet agente de Hyperliquid, que opera pero no puede retirar.

La API nunca recibe ni devuelve una clave de la wallet de Marcos. La del agente se crea aquí, se
guarda en el almacén de claves (como las de un exchange, por `conexiones.guardar_claves`) y no
sale nunca. Lo que sale a la red, en `invest_ll.wallets.red` (los tests lo sustituyen).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter

from invest_ll.api import conexiones as rutas_conexiones
from invest_ll.api.errores import invalido, no_encontrado
from invest_ll.api.schemas_v4 import ClavesExchange
from invest_ll.api.schemas_wallets import (
    AgenteConectado,
    AgentePreparado,
    ConfirmarAgente,
    NuevaWallet,
    PrepararAgente,
    RedHl,
    SaldosCadenaWallet,
    SaldosWallet,
    SaldoWallet,
    WalletConectada,
    Wallets,
)
from invest_ll.wallets import agente as agentes
from invest_ll.wallets import red
from invest_ll.wallets import saldos as calcular
from invest_ll.wallets.registro import RegistroWallets, Wallet

router = APIRouter()


def _wallet(w: Wallet) -> WalletConectada:
    redes: list[RedHl] = [r for r in ("pruebas", "real") if r in w.agente_hyperliquid]
    return WalletConectada(
        direccion=w.direccion, nombre=w.nombre, conectada=w.conectada, agente_hyperliquid=redes
    )


def _buscar(registro: RegistroWallets, direccion: str) -> Wallet:
    w = registro.buscar(direccion)
    if w is None:
        raise no_encontrado(f"No hay ninguna wallet {direccion[:12]}… conectada.")
    return w


def _valida(direccion: str) -> str:
    try:
        return agentes.direccion_valida(direccion)
    except agentes.AgenteError as error:
        raise invalido(str(error)) from error


@router.get("/wallets", tags=["wallets"])
def lista() -> Wallets:
    return Wallets(wallets=[_wallet(w) for w in RegistroWallets().lista()])


@router.post("/wallets", tags=["wallets"], status_code=201)
def conectar(nueva: NuevaWallet) -> WalletConectada:
    """Guarda la dirección (y el nombre de la wallet). 422 si no es una dirección."""
    direccion = _valida(nueva.direccion)
    w = RegistroWallets().anadir(
        Wallet(
            direccion=direccion,
            nombre=nueva.nombre.strip() or "Wallet",
            conectada=datetime.now(UTC),
        )
    )
    return _wallet(w)


@router.delete("/wallets/{direccion}", tags=["wallets"], status_code=204)
def desconectar(direccion: str) -> None:
    """La quita del panel. Si tenía el agente de Hyperliquid, sus claves se borran de este equipo
    (en Hyperliquid se quita desde su página de API)."""
    registro = RegistroWallets()
    w = _buscar(registro, direccion)
    redes: list[RedHl] = [r for r in ("pruebas", "real") if r in w.agente_hyperliquid]
    for r in redes:
        # Si ya no estaban, o vienen del entorno, no hay nada más que hacer.
        with contextlib.suppress(Exception):
            rutas_conexiones.borrar_claves("hyperliquid", r)
    registro.quitar(w.direccion)


@router.get("/wallets/{direccion}/saldos", tags=["wallets"])
def saldos(direccion: str) -> SaldosWallet:
    """Lo que tiene en Ethereum, Arbitrum, Base y Hyperliquid (solo lectura, con su hora)."""
    w = _buscar(RegistroWallets(), direccion)
    s = calcular.saldos(w.direccion)
    return SaldosWallet(
        direccion=w.direccion,
        cadenas=[
            SaldosCadenaWallet(
                cadena=c.cadena,
                nombre=c.nombre,
                saldos=[
                    SaldoWallet(
                        simbolo=x.simbolo,
                        cantidad=Decimal(format(x.cantidad.normalize(), "f")),
                        valor_usd=x.valor_usd.quantize(calcular.CENTIMO)
                        if x.valor_usd is not None
                        else None,
                    )
                    for x in c.saldos
                ],
                error=c.error,
            )
            for c in s.cadenas
        ],
        total_usd=s.total_usd.quantize(calcular.CENTIMO),
        sin_precio=s.sin_precio,
        at=datetime.now(UTC),
    )


@router.post("/wallets/{direccion}/hyperliquid/preparar", tags=["wallets"])
def preparar_agente(direccion: str, peticion: PrepararAgente) -> AgentePreparado:
    """Crea la wallet agente y los datos que tu wallet tiene que firmar (eth_signTypedData_v4)."""
    w = _buscar(RegistroWallets(), direccion)
    try:
        p = agentes.preparar(w.direccion, peticion.red, peticion.chain_id)
    except agentes.AgenteError as error:
        raise invalido(str(error)) from error
    donde = "la red de pruebas" if peticion.red == "pruebas" else "dinero real"
    return AgentePreparado(
        datos_tipados=agentes.datos_tipados(p.red, p.chain_id, p.agente, p.nonce),
        agente=p.agente,
        nonce=p.nonce,
        texto=(
            f"Tu wallet te pedirá firmar «ApproveAgent» para {donde} de Hyperliquid: autoriza a la "
            f"wallet agente {p.agente[:6]}…{p.agente[-4:]} a operar en tu nombre. No puede retirar "
            "ni mover tus fondos. Firmar no cuesta nada (no es una transacción)."
        ),
    )


@router.post("/wallets/{direccion}/hyperliquid/confirmar", tags=["wallets"])
def confirmar_agente(direccion: str, peticion: ConfirmarAgente) -> AgenteConectado:
    """Comprueba la firma, la envía a Hyperliquid y, si la acepta, guarda la conexión de
    Hyperliquid en esa red (la dirección de tu wallet y la clave del agente)."""
    registro = RegistroWallets()
    w = _buscar(registro, direccion)
    try:
        p = agentes.confirmar(
            w.direccion, peticion.red, peticion.nonce, peticion.firma, enviar=red.hyperliquid_enviar
        )
    except (agentes.AgenteError, red.RedWalletError) as error:
        raise invalido(str(error)) from error
    rutas_conexiones.guardar_claves(
        "hyperliquid",
        p.red,
        ClavesExchange(valores={"walletAddress": w.direccion, "privateKey": p.clave_agente}),
    )
    registro.poner_agente(w.direccion, p.red, p.agente)
    siguiente = (
        "Ahora actívala para probar la conexión."
        if p.red == "pruebas"
        else "Para operar con dinero real, actívala en Hyperliquid (Conexiones), que pide teclear «DINERO REAL»."
    )
    return AgenteConectado(
        red=p.red,
        agente=p.agente,
        texto=f"Hyperliquid aceptó la wallet agente: ya está guardada en este equipo. {siguiente}",
    )
