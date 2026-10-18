"""Los bots de pruebas y reales: lo que se comprueba antes de cada orden, cómo sale al exchange y
cómo se concilia lo que cree tener cada bot con el saldo del exchange (docs/panel-v4-real.md §3).

El motor (`bots.motor`) decide igual para todos los bots; lo que cambia es la ejecución. Un bot
ficticio ejecuta contra el libro de Hyperliquid sin mover nada; uno de pruebas o real, con el
conector de su exchange (`exchanges.registro.conector`, que vuelve a mirar en cada orden que el
exchange siga activo en esa red):

- **Límites antes de cada orden** (`por_que_no`): operaciones del día, máximo por orden y capital
  máximo. Si no cabe, no sale y se apunta en llano. Vender lo suyo siempre se puede: los límites
  frenan lo que gasta, no lo atrapan en una posición.
- **Una orden, un id de cliente** (`nuevo_id_cliente`): el motor lo guarda en disco *antes* de
  enviarla (como pausa «desconocido»); si el motor muere a mitad, al volver el bot está en pausa y
  esa orden se consulta al reanudar en vez de adivinar.
- **A mercado, al paso del exchange** (`enviar`): una compra pide la cantidad que cabe en el
  importe con un margen para la comisión y el deslizamiento; una venta, lo que tiene, hacia abajo.
- **Conciliación** (`descuadre`): lo que los bots de un exchange creen tener frente a su saldo.
  El exchange puede tener más (lo de Marcos fuera de los bots), nunca menos.
- **Globales** (`config/bots_real.json`): la pérdida máxima diaria de todos los bots reales y el
  interruptor «Parar todo lo real».
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from invest_ll import llano
from invest_ll.bots.cuenta import Hecha, OrdenPequenaError, usdc
from invest_ll.errors import InvestLLError
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.mercados import al_paso, mercado_de
from invest_ll.fetch.atomic_write import replace_atomically
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Mapping
    from datetime import tzinfo

    from invest_ll.bots.cuenta import Cuenta
    from invest_ll.bots.decisiones import Lado
    from invest_ll.bots.registro import Limites
    from invest_ll.exchanges.conector import Conector, Mercado, OrdenExchange

GLOBALES: Final = Path("config") / "bots_real.json"
MARGEN_COMPRA: Final = Decimal("0.01")
"""Lo que una compra deja sin gastar por si el precio se mueve entre leerlo y ejecutar."""
COMISION_SUPUESTA: Final = Decimal("0.001")
"""Si el exchange no dice su comisión de tomador."""
TOLERANCIA: Final = Decimal("0.005")
"""Lo que puede faltar en el exchange sin que sea un descuadre (redondeos, polvo de comisiones)."""


class NoSePuedeError(InvestLLError):
    """Lo que el estado de ahora no deja hacer (la API lo da como 409): reanudar un bot real con
    «Parar todo lo real» puesto, reanudar sin resolver una orden desconocida…"""


# -- Globales --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Globales:
    limite_diario: Decimal | None = None
    """Pérdida máxima de hoy entre todos los bots reales; al llegar, se para todo lo real."""
    parado_todo: bool = False
    parado_desde: datetime | None = None
    motivo: str | None = None
    """Por qué se paró todo («Lo paraste tú», «Se llegó al límite diario…»)."""


def leer_globales(ruta: Path = GLOBALES) -> Globales:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Globales()
    if not isinstance(datos, dict):
        return Globales()
    d = cast("dict[str, Any]", datos)
    limite = d.get("limite_diario")
    desde = d.get("parado_desde")
    return Globales(
        limite_diario=Decimal(str(limite)) if limite not in (None, "") else None,
        parado_todo=bool(d.get("parado_todo", False)),
        parado_desde=datetime.fromisoformat(str(desde)) if desde else None,
        motivo=str(d["motivo"]) if d.get("motivo") else None,
    )


def guardar_globales(g: Globales, ruta: Path = GLOBALES) -> None:
    datos = {
        "limite_diario": format(g.limite_diario, "f") if g.limite_diario is not None else None,
        "parado_todo": g.parado_todo,
        "parado_desde": g.parado_desde.isoformat() if g.parado_desde else None,
        "motivo": g.motivo,
    }
    texto = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    replace_atomically(ruta, lambda tmp: tmp.write_text(texto, encoding="utf-8"))


# -- Límites ---------------------------------------------------------------------------------------


def dia_de(ahora: datetime, zona: tzinfo) -> str:
    """El día en la hora de Marcos: las operaciones del día y la pérdida de hoy cuentan desde las
    00:00 de Madrid."""
    return ahora.astimezone(zona).date().isoformat()


def gastado(cuenta: Cuenta) -> Decimal:
    """El capital comprometido ahora: lo que costó lo que tiene."""
    return usdc(sum((p.coste for p in cuenta.posiciones.values()), Decimal(0)))


def perdida_pct(valor: Decimal | None, capital: Decimal) -> float:
    """Lo perdido desde su capital, como fracción (0 si gana o no se sabe)."""
    if valor is None or capital <= 0 or valor >= capital:
        return 0.0
    return float(1 - valor / capital)


def por_que_no(
    limites: Limites | None,
    lado: Lado,
    importe: Decimal,
    *,
    gastado_ahora: Decimal,
    operaciones_hoy: int,
) -> str | None:
    """Por qué esta orden no puede salir, en llano; None si cabe en sus límites."""
    if limites is None:
        return "No tiene límites puestos: un bot de exchange no opera sin ellos."
    if lado == "venta":
        return None
    if operaciones_hoy >= limites.operaciones_max_dia:
        return (
            f"Ya hizo hoy {operaciones_hoy} operaciones, su máximo por día: la compra no sale "
            "hasta mañana."
        )
    if importe > limites.orden_max:
        return (
            f"La compra de {llano.numero(importe)} USDC pasa de su máximo por orden "
            f"({llano.numero(limites.orden_max)} USDC): no sale."
        )
    if gastado_ahora + importe > limites.capital_max:
        return (
            f"Con esta compra tendría {llano.numero(gastado_ahora + importe)} USDC invertidos, más "
            f"que su capital máximo ({llano.numero(limites.capital_max)} USDC): no sale."
        )
    return None


def perdida_superada(
    limites: Limites | None, valor: Decimal | None, capital: Decimal
) -> str | None:
    """Si el bot ha caído hasta su pérdida máxima, el texto de por qué se para."""
    if limites is None:
        return None
    pct = perdida_pct(valor, capital)
    if pct < limites.perdida_max_pct:
        return None
    return (
        f"Ha perdido un {llano.porcentaje(pct, 1)} desde su capital y su máximo es "
        f"{llano.porcentaje(limites.perdida_max_pct, 1)}: se para."
    )


def nombre_exchange(exchange: str | None) -> str:
    """'Binance' para 'binance' (el id si no se conoce)."""
    from invest_ll.exchanges.fichas import POR_ID

    ficha = POR_ID.get(exchange or "")
    return ficha.nombre if ficha is not None else str(exchange)


# -- Órdenes ---------------------------------------------------------------------------------------


def nuevo_id_cliente() -> str:
    """Un id por orden (el conector lo adapta al formato de cada exchange)."""
    return f"ilb{secrets.token_hex(12)}"


def mercado(conector: Conector, coin: str) -> Mercado:
    m = mercado_de(conector, coin)
    if m is None:
        raise ExchangeError(
            f"{nombre_exchange(conector.exchange)} no tiene par de contado de {nombre_hyperliquid(coin)} en USDC "
            "ni en USDT."
        )
    return m


def cantidad_a_comprar(m: Mercado, importe: Decimal, precio: Decimal) -> Decimal:
    """Lo que cabe en ese importe con la comisión y el margen, al paso del mercado."""
    comision = m.comision_tomador if m.comision_tomador is not None else COMISION_SUPUESTA
    return al_paso(importe / (precio * (1 + comision + MARGEN_COMPRA)), m.paso_cantidad)


def enviar(
    conector: Conector,
    coin: str,
    lado: Lado,
    *,
    id_cliente: str,
    importe: Decimal | None = None,
    cantidad: Decimal | None = None,
) -> OrdenExchange:
    """Una orden a mercado: la compra por importe (USDC), la venta por cantidad.

    `OrdenPequenaError` si no llega al mínimo del exchange (no se envía nada y no hay que esperar);
    `ExchangeError` si el exchange la rechaza; `EstadoDesconocidoError` si salió y no se sabe cómo
    quedó.
    """
    m = mercado(conector, coin)
    if lado == "compra":
        if importe is None or importe <= 0:
            raise OrdenPequenaError("Nada que gastar.")
        precio = conector.precio(m.par)
        if precio is None or precio <= 0:
            raise ExchangeError(f"No se pudo leer el precio de {m.par}: no se ha enviado nada.")
        cant = cantidad_a_comprar(m, importe, precio)
    else:
        if cantidad is None or cantidad <= 0:
            raise OrdenPequenaError("Nada que vender.")
        cant = al_paso(cantidad, m.paso_cantidad)
        precio = conector.precio(m.par)
    if cant <= 0 or (m.minimo_cantidad is not None and cant < m.minimo_cantidad):
        raise OrdenPequenaError(f"Por debajo del mínimo de {m.par}.")
    if m.minimo_importe is not None and precio is not None and cant * precio < m.minimo_importe:
        raise OrdenPequenaError(f"Por debajo del importe mínimo de {m.par}.")
    return conector.enviar(m.par, lado, cant, id_cliente=id_cliente, tipo="mercado")


def hecha_de(orden: OrdenExchange, coin: str) -> Hecha | None:
    """Lo ejecutado de una orden, para la cuenta del bot (None si no se ejecutó nada).

    La comisión se pasa a la moneda cotizada. Si se cobró en la moneda comprada, lo que entra es lo
    ejecutado menos ella; si se cobró en otra (BNB…), no se puede restar y se deja en cero.
    """
    if orden.ejecutada <= 0 or orden.precio_medio is None:
        return None
    base, _, cotizada = orden.par.partition("/")
    precio = orden.precio_medio
    cantidad = orden.ejecutada
    comision = Decimal(0)
    if orden.comision is not None and orden.comision_moneda is not None:
        if orden.comision_moneda == cotizada:
            comision = orden.comision
        elif orden.comision_moneda == base:
            comision = orden.comision * precio
            if orden.lado == "compra":
                cantidad -= orden.comision
    return Hecha(
        coin=coin,
        lado=orden.lado,
        cantidad=cantidad,
        precio=precio,
        importe=cantidad * precio,
        comision=comision,
    )


# -- Conciliación ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tenencia:
    """Lo que un bot cree tener en su exchange."""

    efectivo: Decimal
    cantidades: Mapping[str, Decimal]


def descuadre(
    conector: Conector, tenencias: Iterable[Tenencia], saldo: Mapping[str, Decimal]
) -> str | None:
    """Lo que falta en el exchange frente a lo que creen tener sus bots, en llano; None si cuadra.

    Se suman los bots del mismo exchange y red (comparten la cuenta). El efectivo se compara con la
    moneda cotizada de su par (USDC o USDT): con la primera que tenga alguna de sus monedas.
    """
    por_moneda: dict[str, Decimal] = {}
    efectivo = Decimal(0)
    for t in tenencias:
        efectivo += t.efectivo
        for coin, cantidad in t.cantidades.items():
            por_moneda[coin] = por_moneda.get(coin, Decimal(0)) + cantidad
    faltas: list[str] = []
    cotizada: str | None = None
    for coin, cree in sorted(por_moneda.items()):
        m = mercado(conector, coin)
        cotizada = cotizada or m.cotizada
        hay = saldo.get(m.base, Decimal(0))
        if hay < cree - _tolerancia(cree, m.paso_cantidad):
            faltas.append(
                f"{nombre_hyperliquid(coin)}: los bots creen tener {llano.cantidad(cree)} y en "
                f"{nombre_exchange(conector.exchange)} hay {llano.cantidad(hay)}"
            )
    if cotizada is None and efectivo > 0:
        cotizada = "USDC" if "USDC" in saldo or "USDT" not in saldo else "USDT"
    if cotizada is not None:
        hay = saldo.get(cotizada, Decimal(0))
        if hay < efectivo - _tolerancia(efectivo, Decimal("0.01")):
            faltas.append(
                f"{cotizada}: los bots creen tener {llano.numero(usdc(efectivo))} y en "
                f"{nombre_exchange(conector.exchange)} hay {llano.numero(usdc(hay))}"
            )
    return "; ".join(faltas) + "." if faltas else None


def _tolerancia(cantidad: Decimal, paso: Decimal | None) -> Decimal:
    return max(cantidad * TOLERANCIA, paso or Decimal(0))
