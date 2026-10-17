"""Las claves de cada exchange en el almacén y los cerrojos para activar cada red.

El almacén es el de memoria de la suite (`tests/conftest.py`); la configuración y el registro de
órdenes, de un directorio temporal. Los cerrojos son los de v2 generalizados: claves de real
distintas, evidencia de pruebas de ESE exchange, una clave que no pueda retirar y lo que se prueba
al activar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.exchanges import activacion, credenciales
from invest_ll.exchanges.activacion import (
    Comprobacion,
    ConfigExchanges,
    activo_efectivo,
    huella,
    por_que_no,
    problema_de_permisos,
    que_falta,
)
from invest_ll.exchanges.credenciales import ClavesExchange, normalizar
from invest_ll.exchanges.fichas import BINANCE, BYBIT, COINBASE, HYPERLIQUID, KRAKEN, OKX, Ficha
from invest_ll.live import credenciales as credenciales_v2
from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import ExecutionLedger

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.exchanges.conector import Red

    from ..almacen_en_memoria import AlmacenEnMemoria

T0 = datetime(2026, 10, 17, 12, tzinfo=UTC)
PRUEBAS = {"apiKey": "CLAVE-PRUEBAS-111", "secret": "SECRETO-PRUEBAS-222"}
REALES = {"apiKey": "CLAVE-REAL-333", "secret": "SECRETO-REAL-444"}


def _claves(valores: dict[str, str]) -> ClavesExchange:
    return ClavesExchange(valores=valores)


def _orden(
    ledger: ExecutionLedger, modo: str, exchange: str | None, ejecutada: str = "0.001"
) -> None:
    peticion = OrderRequest(
        symbol="BTC/USDT", side=Side.BUY, quantity=Decimal("0.001"), requested_at=T0
    )
    resultado = OrderResult(
        request=peticion,
        status=OrderStatus.FILLED if Decimal(ejecutada) > 0 else OrderStatus.REJECTED,
        filled_quantity=Decimal(ejecutada),
        fill_price=Decimal(60000),
        executed_at=T0,
    )
    ledger.record(resultado, mode_name=modo, exchange=exchange)


class Mundo:
    """Un exchange, sus claves guardadas, su configuración y su registro, en un tmp_path."""

    def __init__(self, tmp_path: Path, ficha: Ficha = BYBIT) -> None:
        self.ficha = ficha
        self.config = ConfigExchanges(tmp_path / "config")
        self.ledger = ExecutionLedger(tmp_path / "ledger")
        self.entorno: dict[str, str] = {}

    def guardar(self, red: Red, valores: dict[str, str]) -> ClavesExchange:
        claves = normalizar(self.ficha, valores)
        credenciales.guardar(self.ficha, red, claves)
        return claves

    def estado(self) -> activacion.Estado:
        return activacion.leer(
            self.ficha, entorno=self.entorno, config=self.config, registro=self.ledger
        )

    def comprobada(self, red: Red, *, retirar: bool | None = False) -> None:
        claves = self.estado().claves[red]
        assert claves is not None
        self.config.guardar_comprobacion(
            self.ficha.id,
            red,
            Comprobacion(
                at=T0,
                huella=huella(self.ficha, red, claves),
                puede_operar=True,
                puede_retirar=retirar,
                permisos="…",
            ),
        )

    def activar(self, red: Red) -> None:
        self.comprobada(red)
        self.config.guardar_activo(self.ficha.id, red, at=T0)


# -- Las claves en el almacén ------------------------------------------------------------------


class TestCredenciales:
    def test_guardar_leer_y_borrar_por_exchange_y_red(
        self, almacen_de_claves: AlmacenEnMemoria
    ) -> None:
        okx = {"apiKey": "k", "secret": "s", "password": "frase"}
        credenciales.guardar(OKX, "pruebas", normalizar(OKX, okx))
        assert credenciales.leer(OKX, "pruebas") == _claves(okx)
        assert credenciales.leer(OKX, "real") is None
        assert credenciales.leer(BYBIT, "pruebas") is None
        assert ("invest-ll", "okx-pruebas:password") in almacen_de_claves.guardado
        assert credenciales.borrar(OKX, "pruebas") is True
        assert credenciales.borrar(OKX, "pruebas") is False
        assert credenciales.leer(OKX, "pruebas") is None

    def test_binance_lee_las_claves_que_guardo_v2_y_al_reves(self) -> None:
        credenciales_v2.guardar("real", credenciales_v2.Claves(clave="K-V2", secreto="S-V2"))
        assert credenciales.leer(BINANCE, "real") == _claves({"apiKey": "K-V2", "secret": "S-V2"})

        credenciales.guardar(BINANCE, "pruebas", _claves({"apiKey": "K4", "secret": "S4"}))
        leidas = credenciales_v2.leer("pruebas")
        assert leidas is not None
        assert (leidas.clave, leidas.secreto) == ("K4", "S4")

    def test_el_repr_no_ensena_nada(self) -> None:
        assert "SECRETO" not in repr(_claves(PRUEBAS))

    def test_falta_un_campo_o_sobra_otro(self) -> None:
        with pytest.raises(ValueError, match="Falta «Frase de contraseña"):
            normalizar(OKX, {"apiKey": "k", "secret": "s"})
        with pytest.raises(ValueError, match="no usa password"):
            normalizar(BYBIT, {"apiKey": "k", "secret": "s", "password": "p"})
        with pytest.raises(ValueError, match="lleva espacios"):
            normalizar(BYBIT, {"apiKey": "k k", "secret": "s"})

    def test_se_quitan_los_espacios_de_los_bordes(self) -> None:
        assert normalizar(BYBIT, {"apiKey": " k ", "secret": "s\n"}) == _claves(
            {"apiKey": "k", "secret": "s"}
        )

    def test_hyperliquid_comprueba_la_direccion_y_la_clave(self) -> None:
        bien = {"walletAddress": "0x" + "a" * 40, "privateKey": "0x" + "1" * 64}
        assert normalizar(HYPERLIQUID, bien).valores == bien
        with pytest.raises(ValueError, match="0x seguido de 40"):
            normalizar(HYPERLIQUID, {**bien, "walletAddress": "0x123"})
        with pytest.raises(ValueError, match="64 caracteres"):
            normalizar(HYPERLIQUID, {**bien, "privateKey": "abc"})

    def test_coinbase_pem_en_una_linea_y_rechaza_ed25519(self) -> None:
        pem = "-----BEGIN EC PRIVATE KEY-----\\nMHcCAQEE\\n-----END EC PRIVATE KEY-----"
        claves = normalizar(COINBASE, {"apiKey": "organizations/o/apiKeys/k", "secret": pem})
        assert claves["secret"] == (
            "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEE\n-----END EC PRIVATE KEY-----\n"
        )
        with pytest.raises(ValueError, match="Ed25519"):
            normalizar(COINBASE, {"apiKey": "id", "secret": "A" * 86 + "=="})

    def test_mismas_claves(self) -> None:
        assert _claves(PRUEBAS).mismas_que(_claves({**REALES, "apiKey": PRUEBAS["apiKey"]}))
        assert not _claves(PRUEBAS).mismas_que(_claves(REALES))
        # Hyperliquid: la cartera es la misma en las dos redes; lo que cuenta es la API wallet.
        cartera = "0x" + "a" * 40
        assert not _claves({"walletAddress": cartera, "privateKey": "1"}).mismas_que(
            _claves({"walletAddress": cartera, "privateKey": "2"})
        )
        # OKX: la passphrase se puede repetir.
        assert not _claves({**PRUEBAS, "password": "p"}).mismas_que(
            _claves({**REALES, "password": "p"})
        )


# -- La configuración ----------------------------------------------------------------------------


class TestConfig:
    def test_guarda_el_activo_y_la_comprobacion(self, tmp_path: Path) -> None:
        config = ConfigExchanges(tmp_path)
        assert config.activo("bybit") is None
        config.guardar_activo("bybit", "pruebas", at=T0)
        comprobacion = Comprobacion(T0, "abc", True, False, "Puede operar.")
        config.guardar_comprobacion("bybit", "pruebas", comprobacion)
        assert config.activo("bybit") == "pruebas"
        assert config.comprobacion("bybit", "pruebas") == comprobacion
        assert config.comprobacion("bybit", "real") is None

    def test_olvidar_una_red_activa_la_desconecta(self, tmp_path: Path) -> None:
        config = ConfigExchanges(tmp_path)
        config.guardar_activo("bybit", "real", at=T0)
        config.guardar_comprobacion("bybit", "real", Comprobacion(T0, "abc", True, False, ""))
        config.olvidar("bybit", "real", at=T0)
        assert config.activo("bybit") == "sin_conectar"
        assert config.comprobacion("bybit", "real") is None

    def test_estropeada_no_tumba_nada_y_se_dice(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.config.path.parent.mkdir(parents=True)
        mundo.config.path.write_text("{roto", encoding="utf-8")
        estado = mundo.estado()
        assert estado.activo_guardado is None
        assert estado.aviso is not None
        assert "no se puede leer" in estado.aviso
        # y activar otra vez lo reescribe
        mundo.config.guardar_activo("bybit", "pruebas", at=T0)
        assert mundo.config.activo("bybit") == "pruebas"

    def test_no_guarda_ninguna_clave(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.activar("pruebas")
        texto = mundo.config.path.read_text(encoding="utf-8")
        for valor in PRUEBAS.values():
            assert valor not in texto


# -- Los cerrojos --------------------------------------------------------------------------------


class TestCerrojos:
    def test_de_entrada_sin_conectar_y_que_falta_todo(self, tmp_path: Path) -> None:
        estado = Mundo(tmp_path).estado()
        assert activo_efectivo(estado) == "sin_conectar"
        assert que_falta(estado, "pruebas") == [
            "Guarda las claves de la red de pruebas (testnet.bybit.com)."
        ]
        assert len(que_falta(estado, "real")) == 2  # claves y evidencia

    def test_real_exige_claves_distintas(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.guardar("real", {**REALES, "secret": PRUEBAS["secret"]})
        assert "distintas de las de pruebas" in " ".join(que_falta(mundo.estado(), "real"))

    def test_real_exige_una_orden_de_pruebas_de_ese_exchange(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.guardar("real", REALES)
        _orden(mundo.ledger, "pruebas", "binance")  # de otro exchange: no cuenta
        _orden(mundo.ledger, "pruebas", "bybit", ejecutada="0")  # rechazada: no cuenta
        _orden(mundo.ledger, "REAL", "bybit")  # real: no es de pruebas
        assert "orden en la red de pruebas de Bybit" in " ".join(que_falta(mundo.estado(), "real"))
        _orden(mundo.ledger, "pruebas", "bybit")
        assert que_falta(mundo.estado(), "real") == []

    def test_las_ordenes_de_antes_de_v4_son_de_binance(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, BINANCE)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.guardar("real", REALES)
        _orden(mundo.ledger, "pruebas", None)
        assert que_falta(mundo.estado(), "real") == []

    def test_sin_red_de_pruebas_no_se_exige_evidencia(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, KRAKEN)
        mundo.guardar("real", REALES)
        assert que_falta(mundo.estado(), "real") == []
        assert que_falta(mundo.estado(), "pruebas") == ["Kraken no tiene red de pruebas."]

    def test_una_clave_que_puede_retirar_no_se_activa(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, KRAKEN)
        mundo.guardar("real", REALES)
        mundo.comprobada("real", retirar=True)
        assert "puede retirar fondos" in " ".join(que_falta(mundo.estado(), "real"))
        assert problema_de_permisos(KRAKEN, "real", True) is not None
        assert (
            problema_de_permisos(KRAKEN, "real", None) is not None
        )  # Kraken lo dice: hay que saberlo
        assert problema_de_permisos(KRAKEN, "real", False) is None
        assert problema_de_permisos(BINANCE, "pruebas", None) is None

    def test_activo_en_real_mientras_se_cumpla_todo(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.guardar("real", REALES)
        _orden(mundo.ledger, "pruebas", "bybit")
        mundo.activar("real")
        assert activo_efectivo(mundo.estado()) == "real"
        assert por_que_no(mundo.estado(), "real") == []

        # Las claves cambian sin pasar por el panel: la comprobación ya no vale.
        mundo.guardar("real", {**REALES, "secret": "OTRO-SECRETO-555"})
        assert activo_efectivo(mundo.estado()) == "sin_conectar"
        assert "no está activo con dinero real" in " ".join(por_que_no(mundo.estado(), "real"))

    def test_pruebas_activo_no_da_real(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.activar("pruebas")
        assert activo_efectivo(mundo.estado()) == "pruebas"
        assert por_que_no(mundo.estado(), "pruebas") == []
        assert por_que_no(mundo.estado(), "real")

    def test_real_activo_tambien_deja_operar_en_pruebas_si_se_probaron(
        self, tmp_path: Path
    ) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        mundo.guardar("real", REALES)
        _orden(mundo.ledger, "pruebas", "bybit")
        mundo.activar("real")
        assert por_que_no(mundo.estado(), "pruebas")  # las de pruebas no se probaron
        mundo.comprobada("pruebas")
        assert por_que_no(mundo.estado(), "pruebas") == []

    def test_sin_conectar_no_da_ningun_conector(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path)
        mundo.guardar("pruebas", PRUEBAS)
        assert por_que_no(mundo.estado(), "pruebas") == [
            "Bybit no está conectado: actívalo en Conexiones."
        ]

    def test_la_huella_cambia_con_las_claves_y_no_las_lleva(self) -> None:
        a = huella(BYBIT, "real", _claves(REALES))
        assert a == huella(BYBIT, "real", _claves(dict(REALES)))
        assert a != huella(BYBIT, "real", _claves({**REALES, "secret": "otro"}))
        assert a != huella(BYBIT, "pruebas", _claves(REALES))
        assert all(v not in a for v in REALES.values())


class TestBinanceYElEntorno:
    """Como en v2: lo del entorno manda sobre lo guardado en el panel."""

    def test_las_claves_del_entorno_mandan(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, BINANCE)
        mundo.guardar("real", REALES)
        mundo.entorno = {"INVEST_LL_LIVE_KEY": "K-ENV", "INVEST_LL_LIVE_SECRET": "S-ENV"}
        estado = mundo.estado()
        assert estado.origen["real"] == "entorno"
        assert estado.claves["real"] == _claves({"apiKey": "K-ENV", "secret": "S-ENV"})
        assert estado.origen["pruebas"] == "ninguno"

    def test_media_clave_en_el_entorno_es_ninguna(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, BINANCE)
        mundo.guardar("real", REALES)
        mundo.entorno = {"INVEST_LL_LIVE_KEY": "K-ENV"}
        estado = mundo.estado()
        assert (estado.origen["real"], estado.claves["real"]) == ("entorno", None)

    def test_la_marca_de_pruebas_del_entorno_cuenta(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, BINANCE)
        mundo.guardar("real", REALES)
        mundo.entorno = {"INVEST_LL_TESTNET_VERIFIED": "1"}
        assert que_falta(mundo.estado(), "real") == []

    def test_el_entorno_no_cuenta_para_otros_exchanges(self, tmp_path: Path) -> None:
        mundo = Mundo(tmp_path, BYBIT)
        mundo.entorno = {
            "INVEST_LL_LIVE_KEY": "K-ENV",
            "INVEST_LL_LIVE_SECRET": "S-ENV",
            "INVEST_LL_TESTNET_VERIFIED": "1",
        }
        estado = mundo.estado()
        assert estado.claves["real"] is None
        assert not estado.declarada_en_entorno
