"""Un exchange de ccxt de mentira, para probar `ConectorCcxt` sin red y sin ccxt.

Hace lo justo de lo que usa el conector: mercados con pasos y mínimos, precio, libro, velas, saldo,
órdenes por id de cliente y los "métodos implícitos" de los permisos. Los errores se llaman como
los de ccxt (`Ccxt.NetworkError`...), porque el conector los reconoce por el nombre de su clase.
"""

# Los nombres son los de ccxt a propósito (errores sin sufijo Error, `precisionMode`, `id`).
# ruff: noqa: N815, N818, A002

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any, Literal

from invest_ll.exchanges.ccxt_conector import ConectorCcxt
from invest_ll.exchanges.fichas import BINANCE, Ficha

D = Decimal
AHORA_MS = 1_790_000_000_000  # 2026-09-21


class Ccxt:
    """La jerarquía de errores de ccxt (los nombres son lo que importa)."""

    class BaseError(Exception):
        pass

    class ExchangeError(BaseError):
        pass

    class AuthenticationError(ExchangeError):
        pass

    class InsufficientFunds(ExchangeError):
        pass

    class InvalidOrder(ExchangeError):
        pass

    class OrderNotFound(InvalidOrder):
        pass

    class DuplicateOrderId(InvalidOrder):
        pass

    class BadSymbol(ExchangeError):
        pass

    class OperationFailed(BaseError):
        pass

    class NetworkError(OperationFailed):
        pass

    class RequestTimeout(NetworkError):
        pass

    class InvalidNonce(NetworkError):
        pass

    class BadResponse(OperationFailed):
        pass


def mercado_ccxt(
    base: str = "BTC",
    cotizada: str = "USDT",
    *,
    paso: float = 0.00001,
    tick: float = 0.01,
    minimo_importe: float | None = 5,
    minimo_cantidad: float | None = 0.00001,
    contado: bool = True,
) -> dict[str, Any]:
    return {
        "id": f"{base}{cotizada}",
        "symbol": f"{base}/{cotizada}",
        "base": base,
        "quote": cotizada,
        "spot": contado,
        "active": True,
        "precision": {"amount": paso, "price": tick},
        "limits": {"amount": {"min": minimo_cantidad}, "cost": {"min": minimo_importe}},
        "taker": 0.001,
        "maker": 0.001,
    }


Estilo = Literal["completa", "solo_ids"]


@dataclass
class CcxtFalso:
    """Ver el docstring del módulo. `estilo` dice qué devuelve `create_order`: la orden entera
    (Binance, Hyperliquid) o solo los ids (OKX, Bybit, Kraken, Coinbase)."""

    markets: dict[str, Any] = field(
        default_factory=lambda: {
            "BTC/USDT": mercado_ccxt(),
            "ETH/USDT": mercado_ccxt("ETH", paso=0.0001),
            "BTC-PERP": mercado_ccxt("BTC", "USD", contado=False) | {"symbol": "BTC-PERP"},
        }
    )
    has: dict[str, Any] = field(
        default_factory=lambda: {"fetchOrderTrades": True, "fetchMyTrades": True}
    )
    timeframes: dict[str, str] = field(default_factory=lambda: {"1m": "1m", "1h": "1h", "1d": "1d"})
    precisionMode: int = 4
    precio: float = 60000.0
    estilo: Estilo = "completa"
    comision_en_la_orden: bool = True
    velas_por_peticion: int = 1000
    filas: list[list[Any]] = field(default_factory=list[list[Any]])
    balance: dict[str, Any] = field(default_factory=lambda: {"free": {"USDT": 1000.0}})
    walletAddress: str = ""
    privateKey: str = ""

    cargas: int = 0
    ordenes: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    creadas: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    trades: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    llamadas: list[str] = field(default_factory=list[str])
    libros_pedidos: list[int | None] = field(default_factory=list[int | None])
    fallo_al_crear: Exception | None = None
    llega_aunque_falle: bool = False
    fallo_al_buscar: Exception | None = None
    fallo_al_leer: Exception | None = None
    abierta_tras_crear: int = 0
    """Cuántas lecturas sigue abierta una orden de mercado recién creada."""

    # -- mercado -----------------------------------------------------------------------------------

    def load_markets(self, reload: bool = False) -> dict[str, Any]:
        self.cargas += 1
        return self.markets

    def _leer(self, que: str) -> None:
        self.llamadas.append(que)
        if self.fallo_al_leer is not None:
            raise self.fallo_al_leer

    def amount_to_precision(self, symbol: str, amount: str) -> str:
        paso = D(str(self.markets[symbol]["precision"]["amount"]))
        valor = (D(str(amount)) / paso).to_integral_value(rounding=ROUND_DOWN) * paso
        if valor == 0:
            raise Ccxt.InvalidOrder(f"amount of {symbol} must be greater than minimum precision")
        return format(valor.normalize(), "f")

    def price_to_precision(self, symbol: str, price: str) -> str:
        tick = D(str(self.markets[symbol]["precision"]["price"]))
        valor = (D(str(price)) / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick
        return format(valor.normalize(), "f")

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        self._leer("ticker")
        return {
            "symbol": symbol,
            "last": self.precio,
            "bid": self.precio - 1,
            "ask": self.precio + 1,
        }

    def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        self._leer("libro")
        self.libros_pedidos.append(limit)
        return {
            "bids": [[self.precio - i, 0.5] for i in range(1, 60)],
            "asks": [[self.precio + i, 0.5] for i in range(1, 60)],
            "timestamp": AHORA_MS,
        }

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[list[Any]]:
        self._leer(f"velas since={since} limit={limit}")
        filas = [f for f in self.filas if since is None or f[0] >= since]
        cuantas = min(limit or self.velas_por_peticion, self.velas_por_peticion)
        return filas[:cuantas] if since is not None else filas[-cuantas:]

    def fetch_balance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._leer(f"saldo {params}")
        return self.balance

    # -- órdenes ----------------------------------------------------------------------------------

    def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = dict(params or {})
        id_cliente = str(
            params.get("clientOrderId")
            or params.get("client_order_id")
            or f"ccxt-{len(self.creadas)}"
        )
        self.creadas.append(
            {
                "symbol": symbol,
                "type": type,
                "side": side,
                "amount": amount,
                "price": price,
                **params,
            }
        )
        if self.fallo_al_crear is not None and not self.llega_aunque_falle:
            raise self.fallo_al_crear
        id_orden = str(1000 + len(self.creadas))
        ejecuta = type == "market"
        coste = amount * self.precio
        orden: dict[str, Any] = {
            "id": id_orden,
            "clientOrderId": id_cliente,
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": amount,
            "price": price if type == "limit" else None,
            "status": "closed" if ejecuta else "open",
            "filled": amount if ejecuta else 0.0,
            "average": self.precio if ejecuta else None,
            "cost": coste if ejecuta else 0.0,
            "timestamp": AHORA_MS,
            "fee": {"cost": coste * 0.001, "currency": "USDT"}
            if ejecuta and self.comision_en_la_orden
            else None,
        }
        self.ordenes[id_cliente] = orden
        if ejecuta:
            self.trades.append(
                {
                    "order": id_orden,
                    "symbol": symbol,
                    "fee": {"cost": coste * 0.001, "currency": "USDT"},
                    "timestamp": AHORA_MS,
                }
            )
        if self.fallo_al_crear is not None:
            raise self.fallo_al_crear
        if self.estilo == "solo_ids":
            return {
                "id": id_orden,
                "clientOrderId": id_cliente,
                "symbol": symbol,
                "status": None,
                "filled": None,
            }
        return dict(orden)

    def _leida(self, orden: dict[str, Any]) -> dict[str, Any]:
        if self.abierta_tras_crear > 0 and orden["type"] == "market":
            self.abierta_tras_crear -= 1
            return orden | {"status": "open", "filled": 0.0, "fee": None}
        if not self.comision_en_la_orden:
            return orden | {"fee": None}
        return dict(orden)

    def _buscar(self, params: dict[str, Any] | None) -> dict[str, Any] | None:
        self.llamadas.append(f"buscar {params}")
        if self.fallo_al_buscar is not None:
            raise self.fallo_al_buscar
        valor = next(iter((params or {}).values()), None)
        orden = self.ordenes.get(str(valor))
        return self._leida(orden) if orden is not None else None

    def fetch_order(
        self,
        id: str,
        symbol: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        orden = self._buscar(params)
        if orden is None:
            raise Ccxt.OrderNotFound("Order does not exist.")
        return orden

    def fetch_open_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if params:
            orden = self._buscar(params)
            return [orden] if orden is not None and orden["status"] == "open" else []
        self._leer("abiertas")
        return [
            dict(o)
            for o in self.ordenes.values()
            if o["status"] == "open" and (symbol is None or o["symbol"] == symbol)
        ]

    def fetch_closed_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        orden = self._buscar(params)
        return [orden] if orden is not None and orden["status"] != "open" else []

    def fetch_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.llamadas.append(f"recientes since={since}")
        if self.fallo_al_buscar is not None:
            raise self.fallo_al_buscar
        return [self._leida(o) for o in self.ordenes.values() if o["symbol"] == symbol]

    def cancel_order(
        self,
        id: str,
        symbol: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for orden in self.ordenes.values():
            if orden["id"] == id:
                orden["status"] = "canceled"
                return dict(orden)
        raise Ccxt.OrderNotFound("no existe")

    def fetch_order_trades(
        self,
        id: str,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        self.llamadas.append("operaciones de la orden")
        return [t for t in self.trades if t["order"] == id]

    def fetch_my_trades(self, symbol: str | None = None, since: int | None = None) -> list[Any]:
        self.llamadas.append(f"mis operaciones since={since}")
        return list(self.trades)

    # -- Hyperliquid -------------------------------------------------------------------------------

    @staticmethod
    def eth_get_address_from_private_key(private_key: str) -> str:
        if not private_key.startswith("0x") or len(private_key) != 66:
            raise ValueError("no es una clave")
        return "0x" + private_key[-40:]


def conector(
    ex: CcxtFalso | None = None,
    ficha: Ficha = BINANCE,
    *,
    red: Literal["pruebas", "real"] = "pruebas",
    claves: dict[str, str] | None = None,
) -> ConectorCcxt:
    return ConectorCcxt(
        ex or CcxtFalso(),
        ficha,
        red,
        claves={"apiKey": "CLAVE-PUBLICA-1", "secret": "SECRETO-DE-VERDAD-1"}
        if claves is None
        else claves,
        dormir=lambda _: None,
    )
