"""Wallets (`/api/wallets`) y la wallet agente de Hyperliquid, sin red: las cadenas y Hyperliquid se
sustituyen, y "la wallet del navegador" es una cuenta creada aquí que firma como lo haría MetaMask
(`eth_signTypedData_v4` = firmar los datos tipados EIP-712)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from invest_ll.exchanges import credenciales
from invest_ll.exchanges.fichas import POR_ID
from invest_ll.wallets import agente, red

if TYPE_CHECKING:  # pragma: no cover
    from eth_account.signers.local import LocalAccount

    from .api_apoyo import Api

D = Decimal


def firmar(cuenta: LocalAccount, datos: dict[str, Any]) -> str:
    firmada = Account.sign_message(encode_typed_data(full_message=datos), cuenta.key)
    return "0x" + firmada.signature.hex().removeprefix("0x")


@pytest.fixture
def duena() -> LocalAccount:
    return Account.create()


@pytest.fixture
def enviadas(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Lo que se habría mandado a `/exchange` de Hyperliquid (que contesta que sí)."""
    lista: list[tuple[str, dict[str, Any]]] = []

    def enviar(r: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
        lista.append((r, cuerpo))
        return {"status": "ok", "response": {"type": "default"}}

    monkeypatch.setattr(red, "hyperliquid_enviar", enviar)
    return lista


class TestFirma:
    def test_los_datos_tipados_son_los_del_sdk_oficial(self) -> None:
        # hyperliquid-python-sdk 0.24.0, utils/signing.py: user_signed_payload + sign_agent.
        datos = agente.datos_tipados("real", 42161, "0x" + "ab" * 20, 1_700_000_000_000)
        assert datos["domain"] == {
            "name": "HyperliquidSignTransaction",
            "version": "1",
            "chainId": 42161,
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        }
        assert datos["primaryType"] == "HyperliquidTransaction:ApproveAgent"
        assert datos["types"]["HyperliquidTransaction:ApproveAgent"] == [
            {"name": "hyperliquidChain", "type": "string"},
            {"name": "agentAddress", "type": "address"},
            {"name": "agentName", "type": "string"},
            {"name": "nonce", "type": "uint64"},
        ]
        assert datos["message"]["hyperliquidChain"] == "Mainnet"
        assert (
            agente.datos_tipados("pruebas", 1, "0x" + "ab" * 20, 1)["message"]["hyperliquidChain"]
            == "Testnet"
        )

    def test_ida_y_vuelta_y_lo_que_se_envia(self, duena: LocalAccount) -> None:
        p = agente.preparar(duena.address, "pruebas", 0xA4B1)
        firma = firmar(duena, agente.datos_tipados(p.red, p.chain_id, p.agente, p.nonce))
        enviado: dict[str, Any] = {}

        def enviar(r: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
            enviado.update(cuerpo, red=r)
            return {"status": "ok"}

        hecho = agente.confirmar(duena.address, "pruebas", p.nonce, firma, enviar=enviar)
        assert Account.from_key(hecho.clave_agente).address == p.agente
        assert enviado["red"] == "pruebas"
        assert enviado["action"] == {
            "type": "approveAgent",
            "signatureChainId": "0xa4b1",
            "hyperliquidChain": "Testnet",
            "agentAddress": p.agente,
            "agentName": "invest-ll",
            "nonce": p.nonce,
        }
        assert enviado["nonce"] == p.nonce
        assert set(enviado["signature"]) == {"r", "s", "v"}
        assert enviado["signature"]["v"] in (27, 28)

    def test_una_firma_de_otra_wallet_no_se_envia(self, duena: LocalAccount) -> None:
        otra = Account.create()
        p = agente.preparar(duena.address, "real", 1)
        firma = firmar(otra, agente.datos_tipados(p.red, p.chain_id, p.agente, p.nonce))
        enviado: list[object] = []
        with pytest.raises(agente.AgenteError, match="La firma no es de esa wallet"):
            agente.confirmar(
                duena.address, "real", p.nonce, firma, enviar=lambda r, c: enviado.append(c)
            )
        assert enviado == []

    def test_caduca_y_no_se_puede_usar_dos_veces(self, duena: LocalAccount) -> None:
        hace = datetime.now(UTC) - timedelta(minutes=11)
        p = agente.preparar(duena.address, "pruebas", 1, ahora=hace)
        firma = firmar(duena, agente.datos_tipados(p.red, p.chain_id, p.agente, p.nonce))
        with pytest.raises(agente.AgenteError, match="caduca a los 10 minutos"):
            agente.confirmar(
                duena.address, "pruebas", p.nonce, firma, enviar=lambda r, c: {"status": "ok"}
            )

    def test_si_hyperliquid_dice_que_no(self, duena: LocalAccount) -> None:
        p = agente.preparar(duena.address, "pruebas", 1)
        firma = firmar(duena, agente.datos_tipados(p.red, p.chain_id, p.agente, p.nonce))
        with pytest.raises(
            agente.AgenteError, match="no aceptó la autorización: User has no deposits"
        ):
            agente.confirmar(
                duena.address,
                "pruebas",
                p.nonce,
                firma,
                enviar=lambda r, c: {"status": "err", "response": "User has no deposits"},
            )

    @pytest.mark.parametrize("firma", ["", "0x1234", "0x" + "zz" * 65])
    def test_una_firma_rota(self, firma: str) -> None:
        with pytest.raises(agente.AgenteError, match="no tiene la forma de una firma"):
            agente.firma_a_rsv(firma)


class TestApi:
    def test_conectar_lista_y_desconectar(self, cliente: Api, duena: LocalAccount) -> None:
        r = cliente.post(
            "/api/wallets", json={"direccion": duena.address.lower(), "nombre": "MetaMask"}
        )
        assert r.status_code == 201
        assert r.json()["direccion"] == duena.address  # con su checksum
        assert r.json()["agente_hyperliquid"] == []
        assert [w["nombre"] for w in cliente.get("/api/wallets").json()["wallets"]] == ["MetaMask"]
        assert cliente.post("/api/wallets", json={"direccion": "0xnoesuna"}).status_code == 422
        assert cliente.delete(f"/api/wallets/{duena.address}").status_code == 204
        assert cliente.get("/api/wallets").json()["wallets"] == []
        assert cliente.delete(f"/api/wallets/{duena.address}").status_code == 404

    def test_saldos_con_una_cadena_caida(
        self, cliente: Api, duena: LocalAccount, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cliente.post("/api/wallets", json={"direccion": duena.address, "nombre": "Rabby"})

        def nativo(cadena: str, direccion: str) -> Decimal:
            if cadena == "base":
                raise red.RedWalletError("No se pudo leer Base: se cortó.")
            return D("0.5") if cadena == "ethereum" else D(0)

        def token(cadena: str, t: red.Token, direccion: str) -> Decimal:
            return D(100) if (cadena, t.simbolo) == ("arbitrum", "USDC") else D(0)

        monkeypatch.setattr(red, "saldo_nativo", nativo)
        monkeypatch.setattr(red, "saldo_token", token)

        def precios(_r: str) -> dict[str, Decimal]:
            return {"ETH": D(2400), "HYPE": D(40)}

        def contado(_r: str, _d: str) -> list[tuple[str, Decimal]]:
            return [("USDC", D(50)), ("HYPE", D(2)), ("RARO", D(1))]

        def perpetuos(_r: str, _d: str) -> Decimal:
            return D(0)

        monkeypatch.setattr(red, "hyperliquid_precios", precios)
        monkeypatch.setattr(red, "hyperliquid_contado", contado)
        monkeypatch.setattr(red, "hyperliquid_perpetuos", perpetuos)
        datos = cliente.get(f"/api/wallets/{duena.address}/saldos").json()
        por_cadena = {c["cadena"]: c for c in datos["cadenas"]}
        assert por_cadena["ethereum"]["saldos"] == [
            {"simbolo": "ETH", "cantidad": "0.5", "valor_usd": "1200.00"}
        ]
        assert por_cadena["arbitrum"]["saldos"] == [
            {"simbolo": "USDC", "cantidad": "100", "valor_usd": "100.00"}
        ]
        assert por_cadena["base"]["error"] == "No se pudo leer Base: se cortó."
        assert [s["simbolo"] for s in por_cadena["hyperliquid"]["saldos"]] == [
            "USDC",
            "HYPE",
            "RARO",
        ]
        assert datos["total_usd"] == "1430.00"  # 1200 + 100 + 50 + 80; RARO no tiene precio
        assert datos["sin_precio"] is True

    def test_autorizar_el_agente_guarda_la_conexion_de_hyperliquid(
        self, cliente: Api, duena: LocalAccount, enviadas: list[tuple[str, dict[str, Any]]]
    ) -> None:
        cliente.post("/api/wallets", json={"direccion": duena.address, "nombre": "MetaMask"})
        r = cliente.post(
            f"/api/wallets/{duena.address}/hyperliquid/preparar",
            json={"red": "pruebas", "chain_id": 42161},
        )
        assert r.status_code == 200
        preparado = r.json()
        assert "No puede retirar" in preparado["texto"]
        assert "privateKey" not in r.text and "clave" not in preparado
        firma = firmar(duena, preparado["datos_tipados"])
        r = cliente.post(
            f"/api/wallets/{duena.address}/hyperliquid/confirmar",
            json={"red": "pruebas", "nonce": preparado["nonce"], "firma": firma},
        )
        assert r.status_code == 200, r.text
        assert r.json()["agente"] == preparado["agente"]
        assert len(enviadas) == 1
        claves = credenciales.leer(POR_ID["hyperliquid"], "pruebas")
        assert claves is not None
        assert claves["walletAddress"] == duena.address
        assert Account.from_key(claves["privateKey"]).address == preparado["agente"]
        assert cliente.get("/api/wallets").json()["wallets"][0]["agente_hyperliquid"] == ["pruebas"]
        # Desconectar la wallet borra también la clave del agente de este equipo.
        assert cliente.delete(f"/api/wallets/{duena.address}").status_code == 204
        assert credenciales.leer(POR_ID["hyperliquid"], "pruebas") is None

    def test_una_firma_que_no_vale_no_guarda_nada(
        self, cliente: Api, duena: LocalAccount, enviadas: list[tuple[str, dict[str, Any]]]
    ) -> None:
        cliente.post("/api/wallets", json={"direccion": duena.address})
        preparado = cliente.post(
            f"/api/wallets/{duena.address}/hyperliquid/preparar",
            json={"red": "pruebas", "chain_id": 1},
        ).json()
        firma = firmar(Account.create(), preparado["datos_tipados"])
        r = cliente.post(
            f"/api/wallets/{duena.address}/hyperliquid/confirmar",
            json={"red": "pruebas", "nonce": preparado["nonce"], "firma": firma},
        )
        assert r.status_code == 422
        assert "La firma no es de esa wallet" in r.json()["detail"]
        assert enviadas == []
        assert credenciales.leer(POR_ID["hyperliquid"], "pruebas") is None
