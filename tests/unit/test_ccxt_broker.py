"""El broker que puede mover dinero de verdad (T066).

Con un doble en lugar de ccxt: la suite corre con los sockets bloqueados, así que una
implementación que intentara salir a la red fallaría aquí de forma ruidosa.

El test que más importa es `test_no_se_puede_construir_en_simulacion`. Un broker real que existe
en modo simulación es una contradicción que solo se descubre cuando ya ha mandado algo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from invest_ll.live.broker import (
    Confirmation,
    ConfirmationMismatchError,
    ExecutionError,
    OrderRequest,
    OrderStatus,
    Side,
)
from invest_ll.live.ccxt_broker import CcxtBroker
from invest_ll.live.mode import Real, Simulation, Testnet

D = Decimal
CUANDO = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)

PRUEBAS = Testnet(key="clave-pruebas", secret="secreto-pruebas")
REAL = Real(key="clave-real", secret="secreto-real")


def orden(cantidad: str = "0.001") -> OrderRequest:
    return OrderRequest(symbol="BTC/USDT", side=Side.BUY, quantity=D(cantidad), requested_at=CUANDO)


class ExchangeFalso:
    """Doble de ccxt. Registra lo que se le pide y devuelve lo que se le diga."""

    id = "falso"

    def __init__(self, respuesta: dict[str, Any] | None = None, error: Exception | None = None):
        self.respuesta = respuesta or {"id": "ref-1", "filled": 0.001, "average": 50000.0}
        self.error = error
        self.llamadas: list[dict[str, Any]] = []

    def create_order(
        self,
        symbol: str,
        type: str,  # noqa: A002 - el doble imita la firma de ccxt
        side: str,
        amount: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        self.llamadas.append({"symbol": symbol, "type": type, "side": side, "amount": amount})
        if self.error is not None:
            raise self.error
        return self.respuesta

    def fetch_balance(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return {"free": {"BTC": 0.5, "USDT": 1000.0, "ETH": 0}}


class NetworkError(Exception):
    """Imita el error de red de ccxt. El nombre es lo que se inspecciona."""


class RequestTimeout(Exception):  # noqa: N818 - imita el nombre exacto de ccxt, que es lo que se inspecciona
    """Imita el timeout de ccxt."""


class InsufficientFunds(Exception):  # noqa: N818 - imita el nombre exacto de ccxt
    """Imita un rechazo legítimo del exchange."""


class TestNoExisteEnSimulacion:
    """La garantía que protege el estado por defecto."""

    def test_no_se_puede_construir_en_simulacion(self) -> None:
        """Un broker real en modo simulacion es una contradiccion."""
        with pytest.raises(ValueError, match="no admite modo simulacion"):
            CcxtBroker(ExchangeFalso(), mode=Simulation())

    def test_el_mensaje_dice_que_usar_en_su_lugar(self) -> None:
        with pytest.raises(ValueError, match="SimulatedBroker"):
            CcxtBroker(ExchangeFalso(), mode=Simulation())

    def test_en_pruebas_si_se_construye(self) -> None:
        assert CcxtBroker(ExchangeFalso(), mode=PRUEBAS).mode is PRUEBAS

    def test_distingue_dinero_real_de_pruebas(self) -> None:
        assert not CcxtBroker(ExchangeFalso(), mode=PRUEBAS).is_real_money
        assert CcxtBroker(ExchangeFalso(), mode=REAL).is_real_money


class TestConfirmacionPorOrden:
    def test_sin_confirmacion_no_compila_la_llamada(self) -> None:
        broker = CcxtBroker(ExchangeFalso(), mode=PRUEBAS)
        with pytest.raises(TypeError):
            broker.submit(orden())  # type: ignore[call-arg]

    def test_la_confirmacion_de_otra_orden_no_sirve(self) -> None:
        exchange = ExchangeFalso()
        broker = CcxtBroker(exchange, mode=PRUEBAS)
        with pytest.raises(ConfirmationMismatchError):
            broker.submit(orden("1.0"), confirmation=Confirmation.para(orden("0.001"), at=CUANDO))
        assert exchange.llamadas == [], "no debe llegar al exchange"

    def test_con_la_confirmacion_correcta_se_envia(self) -> None:
        exchange = ExchangeFalso()
        o = orden()
        CcxtBroker(exchange, mode=PRUEBAS).submit(o, confirmation=Confirmation.para(o, at=CUANDO))
        assert len(exchange.llamadas) == 1
        assert exchange.llamadas[0]["symbol"] == "BTC/USDT"


class TestLecturaDelResultado:
    def enviar(self, respuesta: dict[str, Any], cantidad: str = "0.001"):  # type: ignore[no-untyped-def]
        o = orden(cantidad)
        broker = CcxtBroker(ExchangeFalso(respuesta), mode=PRUEBAS)
        return broker.submit(o, confirmation=Confirmation.para(o, at=CUANDO))

    def test_ejecucion_completa(self) -> None:
        r = self.enviar({"id": "x", "filled": 0.001, "average": 50000.0})
        assert r.status is OrderStatus.FILLED
        assert r.matches_request

    def test_ejecucion_parcial_pide_atencion(self) -> None:
        r = self.enviar({"id": "x", "filled": 0.0005, "average": 50000.0})
        assert r.status is OrderStatus.PARTIAL
        assert r.needs_attention

    def test_sin_ejecutar_es_rechazo(self) -> None:
        r = self.enviar({"id": "x", "filled": 0})
        assert r.status is OrderStatus.REJECTED

    def test_el_precio_no_pierde_precision(self) -> None:
        """Es dinero: pasa por str antes de Decimal."""
        r = self.enviar({"id": "x", "filled": 0.001, "average": 50000.123456789})
        assert r.fill_price == D("50000.123456789")


class TestPerderLaConexionNoSeInterpreta:
    """FR-035: suponer cualquiera de las dos cosas cuesta dinero."""

    def fallar_con(self, error: Exception):  # type: ignore[no-untyped-def]
        o = orden()
        broker = CcxtBroker(ExchangeFalso(error=error), mode=PRUEBAS)
        return broker.submit(o, confirmation=Confirmation.para(o, at=CUANDO))

    def test_un_error_de_red_da_desconocido(self) -> None:
        r = self.fallar_con(NetworkError("conexion perdida"))
        assert r.status is OrderStatus.UNKNOWN

    def test_un_timeout_da_desconocido(self) -> None:
        assert self.fallar_con(RequestTimeout("tardo demasiado")).status is OrderStatus.UNKNOWN

    def test_un_rechazo_legitimo_si_es_rechazo(self) -> None:
        """Saldo insuficiente NO es incertidumbre: la orden no salio."""
        assert self.fallar_con(InsufficientFunds("sin saldo")).status is OrderStatus.REJECTED

    def test_el_desconocido_pide_comprobarlo_a_mano(self) -> None:
        texto = self.fallar_con(NetworkError("x")).describe()
        assert "NO se asume" in texto
        assert "compruebalo en el exchange" in texto


class TestNingunaCredencialEnLosMensajes:
    """FR-034: los mensajes de ccxt a veces traen la peticion entera, y ahi viaja la clave."""

    @pytest.mark.parametrize(
        "mensaje",
        [
            "auth failed: apiKey=abc123secreto",
            "invalid signature for secret=xyz789",
            "Authorization: Bearer token-que-no-debe-verse",
        ],
    )
    def test_un_error_con_credenciales_no_las_propaga(self, mensaje: str) -> None:
        o = orden()
        broker = CcxtBroker(ExchangeFalso(error=RuntimeError(mensaje)), mode=REAL)
        resultado = broker.submit(o, confirmation=Confirmation.para(o, at=CUANDO))

        referencia = resultado.broker_reference or ""
        for fragmento in ("abc123secreto", "xyz789", "token-que-no-debe-verse"):
            assert fragmento not in referencia

    def test_un_error_normal_si_se_ve(self) -> None:
        """Filtrar de mas dejaria errores indiagnosticables."""
        o = orden()
        broker = CcxtBroker(ExchangeFalso(error=RuntimeError("mercado cerrado")), mode=PRUEBAS)
        r = broker.submit(o, confirmation=Confirmation.para(o, at=CUANDO))
        assert "mercado cerrado" in (r.broker_reference or "")

    def test_el_error_de_saldo_tampoco_filtra(self) -> None:
        broker = CcxtBroker(ExchangeFalso(error=RuntimeError("apiKey=secreta")), mode=REAL)
        with pytest.raises(ExecutionError) as error:
            broker.balance()
        assert "secreta" not in str(error.value)


class TestSaldo:
    def test_lee_el_saldo_libre(self) -> None:
        saldo = CcxtBroker(ExchangeFalso(), mode=PRUEBAS).balance()
        assert saldo["BTC"] == D("0.5")
        assert saldo["USDT"] == D("1000.0")

    def test_omite_los_saldos_a_cero(self) -> None:
        assert "ETH" not in CcxtBroker(ExchangeFalso(), mode=PRUEBAS).balance()

    def test_no_pierde_precision(self) -> None:
        exchange = ExchangeFalso()
        exchange.fetch_balance = lambda: {"free": {"BTC": 0.123456789}}  # type: ignore[method-assign]
        assert CcxtBroker(exchange, mode=PRUEBAS).balance()["BTC"] == D("0.123456789")
