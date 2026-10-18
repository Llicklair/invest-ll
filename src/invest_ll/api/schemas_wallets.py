"""Contrato de las wallets (docs/panel-v5.md §5): solo direcciones públicas y saldos de lectura;
la autorización de la wallet agente de Hyperliquid. Nunca una clave en ninguna respuesta."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

RedHl = Literal["pruebas", "real"]


class WalletConectada(BaseModel):
    direccion: str = Field(description="Pública, con su checksum (EIP-55)")
    nombre: str = Field(description="La wallet con que se conectó: MetaMask, Rabby…")
    conectada: datetime
    agente_hyperliquid: list[RedHl] = Field(
        description="Las redes de Hyperliquid en que esta wallet tiene autorizado el agente del panel"
    )


class Wallets(BaseModel):
    wallets: list[WalletConectada]


class NuevaWallet(BaseModel):
    direccion: str = Field(min_length=1, max_length=100)
    nombre: str = Field(default="Wallet", max_length=60)


class SaldoWallet(BaseModel):
    simbolo: str
    cantidad: Decimal
    valor_usd: Decimal | None = Field(description="None si no hay precio")


class SaldosCadenaWallet(BaseModel):
    cadena: str
    nombre: str
    saldos: list[SaldoWallet]
    error: str | None


class SaldosWallet(BaseModel):
    direccion: str
    cadenas: list[SaldosCadenaWallet]
    total_usd: Decimal
    sin_precio: bool = Field(description="Algo no se pudo valorar y el total no lo cuenta")
    at: datetime


class PrepararAgente(BaseModel):
    red: RedHl
    chain_id: int = Field(gt=0, description="La cadena en que está la wallet (eth_chainId)")


class AgentePreparado(BaseModel):
    datos_tipados: dict[str, Any] = Field(description="Para eth_signTypedData_v4, tal cual")
    agente: str = Field(description="La dirección pública del agente que se autoriza")
    nonce: int
    texto: str


class ConfirmarAgente(BaseModel):
    red: RedHl
    nonce: int
    firma: str = Field(description="Lo que devolvió eth_signTypedData_v4 (0x y 130 hex)")


class AgenteConectado(BaseModel):
    red: RedHl
    agente: str
    texto: str
