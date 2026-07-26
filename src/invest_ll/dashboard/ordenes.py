"""La puerta del panel al dinero, con los mismos cerrojos que la del terminal.

Un botón es cómodo, y por eso es peligroso: un clic distraído no debería mover dinero. Aquí vive
la decisión de **si se puede enviar** y el envío en sí, separados de cómo se pinta la pantalla, para
que sean comprobables sin levantar Streamlit.

Las garantías son las mismas que en `invest-ll-execute`, ni una menos:

- `Simulation` no envía **nada**. Ni con confirmación. Se levanta `EnvioBloqueadoError` en lugar de
  devolver un resultado inventado: fingir que se operó sería peor que fallar.
- Hay que escribir la cantidad. Obliga a mirar el número que se va a mover, que es justo lo que un
  botón se salta.
- La confirmación se construye a partir de **esa** orden concreta, así que no autoriza ninguna otra.
- Todo lo enviado va al registro con el modo dentro, igual que desde el terminal.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from invest_ll.errors import InvestLLError
from invest_ll.live.broker import Confirmation, OrderRequest, Side
from invest_ll.live.mode import Simulation

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from invest_ll.live.broker import Broker, OrderResult
    from invest_ll.live.ledger import ExecutionLedger
    from invest_ll.live.mode import OperatingMode


class EnvioBloqueadoError(InvestLLError):
    """Se intentó enviar sin cumplir alguna condición."""


def _cantidad_escrita(escrito: str) -> Decimal | None:
    """Lo tecleado, como número. `None` si no es uno.

    Se compara el valor y no la cadena: `0.0010` y `0.001` son la misma cantidad, y exigir la
    escritura exacta convertiría una confirmación en un acertijo de formato.
    """
    try:
        return Decimal(escrito.strip())
    except (InvalidOperation, ValueError):
        return None


def puede_enviar(modo: OperatingMode, *, cantidad: Decimal, escrito: str) -> bool:
    """Si con este modo y esto tecleado se puede enviar la orden."""
    return motivo_para_no_enviar(modo, cantidad=cantidad, escrito=escrito) is None


def motivo_para_no_enviar(modo: OperatingMode, *, cantidad: Decimal, escrito: str) -> str | None:
    """Por qué no se puede enviar, en algo que se le pueda enseñar a alguien. `None` si se puede.

    Devuelve el motivo en vez de un booleano porque la pantalla tiene que **explicar** el bloqueo:
    un botón gris sin razón se interpreta como un fallo del programa.
    """
    if isinstance(modo, Simulation):
        return (
            "Modo simulacion: no se envia nada al exterior. Para operar de verdad, arranca el "
            "panel con INVEST_LL_MODE=testnet (o =real) y sus credenciales."
        )
    if cantidad <= 0:
        return "La cantidad tiene que ser positiva."

    tecleado = _cantidad_escrita(escrito)
    if tecleado is None:
        return f"Escribe la cantidad exacta ({cantidad}) para confirmar."
    if tecleado != cantidad:
        return f"Lo escrito ({escrito.strip()}) no coincide con la cantidad ({cantidad})."
    return None


def enviar_orden(
    broker: Broker,
    *,
    symbol: str,
    side: Side,
    cantidad: Decimal,
    escrito: str,
    ahora: datetime,
    ledger: ExecutionLedger | None = None,
) -> OrderResult:
    """Envía la orden si todo está en regla, y la registra.

    No comprueba el modo del broker por separado: se lo pregunta a `broker.mode`, que es el que de
    verdad va a ejecutar. Comprobar una copia del modo guardada en la pantalla dejaría un hueco
    entre lo que se valida y lo que se hace.
    """
    motivo = motivo_para_no_enviar(broker.mode, cantidad=cantidad, escrito=escrito)
    if motivo is not None:
        raise EnvioBloqueadoError(motivo)

    peticion = OrderRequest(symbol=symbol, side=side, quantity=cantidad, requested_at=ahora)
    resultado = broker.submit(peticion, confirmation=Confirmation.para(peticion, at=ahora))

    if ledger is not None:
        ledger.record(resultado, mode_name=broker.mode.name)
    return resultado
