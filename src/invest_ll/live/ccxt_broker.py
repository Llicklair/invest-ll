"""Ejecución real en exchanges de cripto, vía ccxt.

**Es el único módulo del proyecto que puede mover dinero de verdad.** Todo lo que hay aquí está
escrito para que eso sea difícil, no cómodo:

- **No acepta `Simulation`.** El constructor lo rechaza. Un broker real no puede existir en modo
  simulación ni por accidente ni por configuración heredada: para eso está `SimulatedBroker`.
- **El modo se comprueba al ENVIAR, no al construir** (FR-032). Entre construir el broker y mandar
  una orden puede pasar cualquier cosa; la comprobación que importa es la de justo antes.
- **La confirmación es de esa orden concreta** y no tiene valor por defecto. "Autorizar todas" no
  se puede escribir.
- **Perder la conexión da `UNKNOWN`**, nunca `FILLED` ni `REJECTED` (FR-035). Suponer cualquiera de
  las dos cosas cuesta dinero: una lleva a no reintentar algo que no se ejecutó, la otra a duplicar
  una orden que sí salió.
- **Ninguna credencial aparece en un mensaje de error** (FR-034). Los mensajes de ccxt se recortan
  y se filtran antes de propagarse.

Los tests lo prueban con un doble. La suite corre con los sockets bloqueados, así que una
implementación que intentara salir a la red fallaría de forma ruidosa.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, cast

from invest_ll.live.broker import (
    Confirmation,
    ConfirmationMismatchError,
    ExecutionError,
    OrderRequest,
    OrderResult,
    OrderStatus,
)
from invest_ll.live.mode import Real, Simulation, Testnet

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.live.mode import OperatingMode

# Errores de ccxt que significan "no sabemos si la orden salió". Cualquier fallo de red tras el
# envío entra aquí: el exchange puede haberla aceptado y habernos fallado la respuesta.
ERRORES_INCIERTOS = ("NetworkError", "RequestTimeout", "ExchangeNotAvailable", "DDoSProtection")

LONGITUD_MAXIMA_ERROR = 200


class CcxtExchange(Protocol):
    """Lo que necesitamos de un exchange. Recortado a propósito.

    Declarar solo estos tres métodos hace evidente qué superficie de ccxt usamos, y permite
    sustituirlo en los tests sin arrastrar la librería entera.
    """

    def create_order(
        self,
        symbol: str,
        type: str,  # noqa: A002 - es el nombre del parametro en ccxt; renombrarlo romperia la llamada
        side: str,
        amount: float,
        price: float | None = None,
    ) -> dict[str, Any]: ...

    def fetch_balance(self) -> dict[str, Any]: ...

    @property
    def id(self) -> str: ...


class CcxtBroker:
    """Envía órdenes a un exchange de cripto.

    El `exchange` se recibe ya construido: así este módulo no decide de dónde salen las
    credenciales, y un test puede pasar un doble sin tocar la red.
    """

    __slots__ = ("_exchange", "_mode")

    def __init__(self, exchange: CcxtExchange, *, mode: OperatingMode) -> None:
        if isinstance(mode, Simulation):
            raise ValueError(
                "CcxtBroker no admite modo simulacion: manda ordenes de verdad. "
                "Para simular usa SimulatedBroker, que no sale al exterior."
            )
        self._exchange = exchange
        self._mode = mode

    @property
    def mode(self) -> Testnet | Real:
        return self._mode  # type: ignore[return-value]

    @property
    def is_real_money(self) -> bool:
        return isinstance(self._mode, Real)

    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult:
        """Envía una orden. Exige confirmación de **esta** orden."""
        if not confirmation.authorises(request):
            raise ConfirmationMismatchError(
                "la confirmacion no corresponde a esta orden. Cada orden se autoriza por separado."
            )

        # FR-032: se comprueba AQUI, no en el constructor. Entre construir y enviar puede haber
        # pasado cualquier cosa; lo que importa es el estado en el momento de mandar.
        if not self._mode.sends_real_orders:  # pragma: no cover - imposible por el constructor
            raise ExecutionError(f"el modo {self._mode.name} no puede enviar ordenes reales")

        try:
            crudo = self._exchange.create_order(
                symbol=request.symbol,
                type="market",
                side=request.side.value,
                amount=float(request.quantity),
            )
        except Exception as error:
            return self._interpretar_fallo(request, error)

        return self._leer(request, crudo)

    def balance(self) -> dict[str, Decimal]:
        try:
            crudo = self._exchange.fetch_balance()
        except Exception as error:
            raise ExecutionError(f"no se pudo leer el saldo: {_limpiar(error)}") from None

        libres = crudo.get("free", {})
        if not isinstance(libres, dict):  # pragma: no cover - respuesta inesperada
            return {}

        # Frontera con ccxt, que no publica tipos: aqui acaba la garantia del comprobador y
        # empieza la confianza en la respuesta del exchange. Todo pasa por str antes de Decimal
        # porque son cantidades de dinero.
        entradas = cast("dict[str, Any]", libres)
        return {
            str(moneda): Decimal(str(cantidad)) for moneda, cantidad in entradas.items() if cantidad
        }

    def _interpretar_fallo(self, request: OrderRequest, error: Exception) -> OrderResult:
        """Decide si el fallo significa 'rechazada' o 'no lo sabemos'.

        La distinción es lo que evita perder dinero: un timeout de red **no** significa que la
        orden no saliera. Puede estar ejecutada en el exchange y habernos fallado la respuesta.
        """
        nombre = type(error).__name__
        incierto = any(marca in nombre for marca in ERRORES_INCIERTOS)

        return OrderResult(
            request=request,
            status=OrderStatus.UNKNOWN if incierto else OrderStatus.REJECTED,
            filled_quantity=Decimal(0),
            fill_price=None,
            executed_at=None,
            broker_reference=f"{nombre}: {_limpiar(error)}",
        )

    def _leer(self, request: OrderRequest, crudo: dict[str, Any]) -> OrderResult:
        ejecutada = Decimal(str(crudo.get("filled") or 0))
        precio = crudo.get("average") or crudo.get("price")

        if ejecutada <= 0:
            estado = OrderStatus.REJECTED
        elif ejecutada < request.quantity:
            estado = OrderStatus.PARTIAL
        else:
            estado = OrderStatus.FILLED

        return OrderResult(
            request=request,
            status=estado,
            filled_quantity=ejecutada,
            fill_price=Decimal(str(precio)) if precio else None,
            executed_at=datetime.now(UTC),
            broker_reference=str(crudo.get("id") or ""),
        )


def _limpiar(error: Exception) -> str:
    """Recorta el mensaje de ccxt.

    FR-034: los mensajes de ccxt a veces incluyen la petición completa, y ahí viaja la clave.
    Recortar no es cosmético — es lo que evita que una credencial acabe en un log.
    """
    texto = str(error)
    for marca in ("apiKey", "api_key", "secret", "signature", "Authorization"):
        if marca in texto:
            return f"error del exchange (mensaje omitido: contenia {marca})"
    return texto[:LONGITUD_MAXIMA_ERROR]


def build_exchange(mode: Testnet | Real, *, exchange_id: str = "binance") -> CcxtExchange:
    """Construye el exchange de ccxt con las credenciales del modo.

    Vive aquí y no en `CcxtBroker` para que el broker sea testeable sin ccxt: esta función es la
    única que importa la librería, y ningún test la llama.
    """
    import ccxt

    clase = getattr(ccxt, exchange_id, None)
    if clase is None:
        raise ExecutionError(f"exchange desconocido: {exchange_id!r}")

    exchange = clase(
        {
            "apiKey": mode.key,
            "secret": mode.secret,
            "enableRateLimit": True,
        }
    )

    if isinstance(mode, Testnet):
        # La red de pruebas es donde se descubren los fallos de ejecucion sin pagarlos.
        exchange.set_sandbox_mode(True)

    return exchange  # type: ignore[no-any-return]
