"""Qué toca hacer hoy según tu plan (docs/panel-v2.md, sección 7). Calcula; no envía nada.

**Cripto (Binance).** El dinero de la parte es lo que le toca por el plan —el inicial más una
aportación por cada mes vencido— menos lo que ya se invirtió en cripto desde que se creó el plan,
más lo que valen hoy tus posiciones de cripto. Recién creado el plan, sin movimientos, es
exactamente "inicial + mensual x aportaciones vencidas", como dice la especificación; después
sigue la cuenta de la parte: si Bitcoin se dobla, la parte vale el doble y no se vende la subida
para volver a lo aportado. Ese dinero se reparte con los pesos que la estrategia quiere hoy, se
compara con lo que hay (valorado al último cierre) y sale una orden por moneda cuya diferencia
supere 10 USDT. Las cantidades se redondean hacia abajo a 6 decimales (el paso de cada par no se
conoce sin preguntar al exchange) y las ventas van antes que las compras. Si la estrategia lleva
banda de no operar (la cesta, 2 puntos), los cambios más pequeños que la banda no se proponen,
salvo salir del todo de una moneda.

**Bolsa (tu bróker).** Una aportación vence el día del mes del plan; desde ese día, y mientras no
se anote la compra de un fondo con el plan, se propone una línea por fondo: importe = aportación x
peso objetivo (la primera vez, también el inicial). Las compras anotadas en ese periodo quitan su
línea; las demás se mantienen con el mismo importe. No se ajusta el reparto con ventas: aportar a
los pesos objetivo es más barato y casi igual de bueno.

**Lo que no se inventa.** Sin precio de algo que tienes o que habría que comprar, no hay orden: hay
un aviso que dice qué falta. Con las compras en pausa, solo se proponen ventas.

Los identificadores son estables durante el día (fecha, dónde, estrategia, activo y lado): el
frontend puede pedir la lista dos veces y anotar una acción por su id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from hashlib import sha256
from typing import TYPE_CHECKING, Final, Literal

from invest_ll import llano
from invest_ll.nombres import base, equivalente, equivalente_corto, es_cripto, nombre_llano
from invest_ll.plan import calendario
from invest_ll.portfolio.models import ActivityType

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    from invest_ll.estrategias.catalogo import Ficha
    from invest_ll.portfolio.models import Activity

UMBRAL_CRIPTO: Final = Decimal(10)
"""USDT: por debajo, la orden no merece la comisión (y Binance tiene mínimos parecidos)."""
IMPORTE_MINIMO_BOLSA: Final = Decimal(1)
DECIMALES_CRIPTO: Final = Decimal("0.000001")
DECIMALES_BOLSA: Final = Decimal("0.0001")
CENTIMO: Final = Decimal("0.01")
PESO_MINIMO_BOLSA: Final = 0.005
FUENTE_PLAN: Final = "plan"
MONEDA_CRIPTO: Final = "USDT"
MONEDA_BOLSA: Final = "EUR"
LONGITUD_ID: Final = 16

AVISO_USDT: Final = (
    "Para comprar en Binance necesitas ese dinero en USDT en tu cuenta: ingrésalo antes de "
    "confirmar las compras."
)

Donde = Literal["binance", "broker"]
Lado = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class Precio:
    valor: Decimal
    fecha: date


@dataclass(frozen=True, slots=True)
class ParteDeHoy:
    """Una parte del plan con lo que su estrategia quiere hoy.

    `objetivo`: peso por activo (cripto: la moneda, `BTC`; bolsa: el fondo, `SPY`). `precios`: el
    último cierre de cada activo del objetivo y, en cripto, de cada moneda que ya tienes.
    """

    ficha: Ficha
    inicial: Decimal
    mensual: Decimal
    objetivo: Mapping[str, float]
    precios: Mapping[str, Precio]


@dataclass(frozen=True, slots=True)
class Entrada:
    hoy: date
    creado: date
    dia: int
    actividades: Sequence[Activity]
    """Los movimientos de la cartera del modo activo."""
    posiciones: Mapping[str, Decimal]
    """Lo que tienes ahora: símbolo de la cartera (`BTC/USDT`, `SPY`) y cantidad."""
    cripto: ParteDeHoy | None = None
    bolsa: ParteDeHoy | None = None
    pausa: str | None = None
    actividades_bolsa: Sequence[Activity] | None = None
    """Los movimientos de la cartera real, donde se anota lo del bróker; `None` = `actividades`.

    El modo es de Binance: lo que compras en tu bróker es dinero de verdad en cualquier modo."""


@dataclass(frozen=True, slots=True)
class Accion:
    """Lo mismo que `schemas_v2.Accion`, más `periodo` (desde cuándo cuenta una compra anotada)."""

    id: str
    donde: Donde
    estrategia: str
    titulo: str
    explicacion: str
    activo: str
    simbolo: str
    par: str | None
    lado: Lado
    cantidad: Decimal | None
    importe: Decimal
    moneda: str
    precio_ref: Decimal | None
    precio_fecha: date | None
    equivalente: str | None
    periodo: date | None = None


@dataclass(frozen=True, slots=True)
class Resultado:
    acciones: tuple[Accion, ...]
    avisos: tuple[str, ...]
    proxima_fecha: date
    resumen: str


@dataclass(slots=True)
class _Avisos:
    lista: list[str] = field(default_factory=lambda: list[str]())

    def __call__(self, texto: str) -> None:
        if texto not in self.lista:
            self.lista.append(texto)


def _aviso_pausa(pausa: str) -> str:
    """Uno solo para las dos partes (los avisos iguales se juntan): antes salía dos veces."""
    return (
        f"Las compras están en pausa: {pausa}. Mientras dure no se propone ninguna compra; "
        "si toca vender algo, sí."
    )


def id_de_accion(hoy: date, donde: str, estrategia: str, simbolo: str, lado: str) -> str:
    material = "|".join((hoy.isoformat(), donde, estrategia, simbolo, lado))
    return sha256(material.encode("utf-8")).hexdigest()[:LONGITUD_ID]


def calcular(e: Entrada) -> Resultado:
    avisos = _Avisos()
    acciones: list[Accion] = []
    if e.cripto is not None:
        acciones.extend(_cripto(e, e.cripto, avisos))
    if e.bolsa is not None:
        acciones.extend(_bolsa(e, e.bolsa, avisos))
    if any(a.donde == "binance" and a.lado == "buy" for a in acciones):
        avisos(AVISO_USDT)
    proxima = calendario.proxima(e.creado, e.dia, e.hoy)
    return Resultado(
        acciones=tuple(acciones),
        avisos=tuple(avisos.lista),
        proxima_fecha=proxima,
        resumen=resumen(acciones, proxima),
    )


def resumen(acciones: Sequence[Accion], proxima: date) -> str:
    if not acciones:
        return f"No toca hacer nada. Tu próxima aportación es el {llano.fecha_larga(proxima)}."
    partes: list[str] = []
    en_binance = sum(1 for a in acciones if a.donde == "binance")
    en_broker = len(acciones) - en_binance
    if en_binance:
        partes.append(f"{en_binance} {'orden' if en_binance == 1 else 'órdenes'} en Binance")
    if en_broker:
        partes.append(f"{en_broker} {'compra' if en_broker == 1 else 'compras'} en tu bróker")
    return "Hoy toca: " + " y ".join(partes) + "."


# -- Cripto -----------------------------------------------------------------------------------


def _neto_invertido_en_cripto(actividades: Sequence[Activity], desde: date) -> Decimal:
    """Lo pagado por compras de cripto menos lo cobrado por ventas, desde la creación del plan."""
    neto = Decimal(0)
    for a in actividades:
        if a.symbol is None or not es_cripto(a.symbol) or a.timestamp.date() < desde:
            continue
        if a.type is ActivityType.BUY:
            neto += a.gross + a.fee
        elif a.type is ActivityType.SELL:
            neto -= a.gross - a.fee
    return neto


def _cripto(e: Entrada, parte: ParteDeHoy, aviso: _Avisos) -> list[Accion]:
    meses = calendario.vencidas(e.creado, e.dia, e.hoy)
    if meses == 0:
        return []
    aportado = parte.inicial + parte.mensual * meses
    efectivo = max(Decimal(0), aportado - _neto_invertido_en_cripto(e.actividades, e.creado))

    cantidades: dict[str, Decimal] = {}
    for simbolo, cantidad in e.posiciones.items():
        if es_cripto(simbolo) and cantidad > 0:
            cantidades[base(simbolo)] = cantidades.get(base(simbolo), Decimal(0)) + cantidad
    faltan = sorted(
        b
        for b in {*cantidades, *(k for k, w in parte.objetivo.items() if w > 0)}
        if b not in parte.precios
    )
    if faltan:
        aviso(
            "No se pueden calcular las órdenes de Binance: falta el precio de "
            + ", ".join(nombre_llano(b) for b in faltan)
            + ". Descarga los datos de Binance: uv run invest-ll-quant download"
        )
        return []

    valores = {b: q * parte.precios[b].valor for b, q in cantidades.items()}
    capital = efectivo + sum(valores.values(), Decimal(0))
    if capital <= 0:
        return []

    ventas: list[tuple[Decimal, Accion]] = []
    compras: list[tuple[Decimal, Accion]] = []
    for moneda in sorted({*parte.objetivo, *cantidades}):
        peso = Decimal(str(parte.objetivo.get(moneda, 0.0)))
        actual = valores.get(moneda, Decimal(0))
        objetivo = capital * peso
        diferencia = objetivo - actual
        sale_del_todo = peso == 0 and cantidades.get(moneda, Decimal(0)) > 0
        if not sale_del_todo and abs(peso - actual / capital) < Decimal(
            str(parte.ficha.motor.banda)
        ):
            continue
        if abs(diferencia) <= UMBRAL_CRIPTO:
            continue
        precio = parte.precios[moneda]
        if diferencia < 0:
            tenido = cantidades.get(moneda, Decimal(0))
            cantidad = tenido if sale_del_todo else min(tenido, -diferencia / precio.valor)
        else:
            if e.pausa is not None:
                aviso(_aviso_pausa(e.pausa))
                continue
            cantidad = diferencia / precio.valor
        cantidad = cantidad.quantize(DECIMALES_CRIPTO, rounding=ROUND_DOWN)
        if cantidad <= 0:
            continue
        lado: Lado = "sell" if diferencia < 0 else "buy"
        motivo = parte.ficha.motivo_dentro if peso > 0 else parte.ficha.motivo_fuera
        nombre = nombre_llano(moneda)
        par = f"{moneda}/USDT"
        accion = Accion(
            id=id_de_accion(e.hoy, "binance", parte.ficha.clave, par, lado),
            donde="binance",
            estrategia=parte.ficha.clave,
            titulo=f"{'Vender' if lado == 'sell' else 'Comprar'} {nombre}",
            explicacion=(
                f"{motivo}; tu parte de cripto debería tener unos "
                f"{llano.numero(objetivo, 0)} USDT en {nombre} "
                f"({llano.porcentaje(float(peso))}) y ahora tiene unos "
                f"{llano.numero(actual, 0)} USDT."
            ),
            activo=nombre,
            simbolo=par,
            par=par,
            lado=lado,
            cantidad=cantidad,
            importe=(cantidad * precio.valor).quantize(CENTIMO, rounding=ROUND_HALF_UP),
            moneda=MONEDA_CRIPTO,
            precio_ref=precio.valor,
            precio_fecha=precio.fecha,
            equivalente=None,
        )
        (ventas if lado == "sell" else compras).append((abs(diferencia), accion))
    # Ventas antes que compras: el dinero de las ventas es el que paga las compras.
    ventas.sort(key=lambda x: x[0], reverse=True)
    compras.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in ventas] + [a for _, a in compras]


# -- Bolsa ------------------------------------------------------------------------------------


def compras_del_plan(
    actividades: Sequence[Activity], simbolos: Sequence[str], desde: date
) -> list[Activity]:
    """Las compras anotadas con el plan (fuente 'plan') de esos fondos, desde la creación."""
    buscados = {s.upper() for s in simbolos}
    return [
        a
        for a in actividades
        if a.type is ActivityType.BUY
        and a.source == FUENTE_PLAN
        and a.symbol is not None
        and a.symbol.upper() in buscados
        and a.timestamp.date() >= desde
    ]


def _bolsa(e: Entrada, parte: ParteDeHoy, aviso: _Avisos) -> list[Accion]:
    periodo = calendario.periodo_actual(e.creado, e.dia, e.hoy)
    if periodo is None:
        return []
    if e.pausa is not None:
        aviso(_aviso_pausa(e.pausa))
        return []
    simbolos = parte.ficha.motor.simbolos or tuple(parte.objetivo)
    del_broker = e.actividades if e.actividades_bolsa is None else e.actividades_bolsa
    hechas = compras_del_plan(del_broker, simbolos, e.creado)
    primera = not any(a.timestamp.date() < periodo for a in hechas)
    ya = {
        a.symbol.upper() for a in hechas if a.symbol is not None and a.timestamp.date() >= periodo
    }
    aporte = parte.mensual + (parte.inicial if primera else Decimal(0))

    acciones: list[Accion] = []
    for simbolo, peso in sorted(parte.objetivo.items(), key=lambda x: (-x[1], x[0])):
        if peso < PESO_MINIMO_BOLSA or simbolo.upper() in ya:
            continue
        importe = (aporte * Decimal(str(peso))).quantize(CENTIMO, rounding=ROUND_HALF_UP)
        if importe < IMPORTE_MINIMO_BOLSA:
            continue
        precio = parte.precios.get(simbolo)
        if precio is None:
            aviso(
                f"Falta el precio de {nombre_llano(simbolo)}: descarga los datos de los fondos "
                "(uv run invest-ll-quant download --etf)."
            )
            continue
        nombre = nombre_llano(simbolo)
        cuanto = llano.euros(aporte)
        if primera and parte.inicial > 0:
            cuanto += ", con lo que pones al empezar"
        detalle = (
            f"Tu aportación de {llano.mes(periodo)} ({cuanto}): el {llano.porcentaje(peso)} va a "
            f"{nombre}, según el reparto de {parte.ficha.nombre}"
        )
        acciones.append(
            Accion(
                id=id_de_accion(e.hoy, "broker", parte.ficha.clave, simbolo, "buy"),
                donde="broker",
                estrategia=parte.ficha.clave,
                titulo=f"Compra unos {llano.euros(importe.to_integral_value())} de "
                f"{equivalente_corto(simbolo)}",
                explicacion=detalle + ".",
                activo=nombre,
                simbolo=simbolo,
                par=None,
                lado="buy",
                cantidad=(importe / precio.valor).quantize(DECIMALES_BOLSA, rounding=ROUND_DOWN),
                importe=importe,
                moneda=MONEDA_BOLSA,
                precio_ref=precio.valor,
                precio_fecha=precio.fecha,
                equivalente=equivalente(simbolo),
                periodo=periodo,
            )
        )
    return acciones
