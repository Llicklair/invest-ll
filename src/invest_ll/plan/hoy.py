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
línea; las demás se mantienen con el mismo importe.

Además, cualquier día, se mira si sobra algo de lo que el plan ya compró (`en_el_broker`: solo lo
anotado con el plan, nunca lo que tuvieras antes). La parte de bolsa es lo que valen esos fondos al
último cierre, más lo que toca comprar hoy con la aportación, más lo que cobraste al vender con el
plan y aún no has vuelto a invertir (`EnElBroker.libre`). Un fondo sobra cuando pesa en ella al
menos `UMBRAL_VENTA` (10 puntos, el mismo umbral con que se cuentan los `cambios_al_anio` de la
tarjeta) más de lo que quiere la estrategia: se propone venderlo hasta su objetivo, o entero si su
objetivo es ~0 (la Prudente con freno deja fuera lo que lleva meses bajando). Por debajo del
umbral, la diferencia la absorben las aportaciones. Medido sobre 2008-2026 con 6.000 € al empezar
y 200 € al mes (comprobando cada semana): la Prudente con freno pide vender unas 4-5 veces al año
y su peor caída queda en torno al -10 %; sin vender nunca, en torno al -16 %. Equilibrada pide
vender una vez cada 5-6 años (deriva grande) y Bolsa de EE.UU., nunca.

Las ventas van antes que las compras, y lo que liberan se reparte entre los fondos que quedan por
debajo de su objetivo, en la misma lista de la compra (sumado a la línea de la aportación, si la
hay). Si el objetivo deja una parte en liquidez, o las compras están en pausa, esa parte se queda
sin invertir en tu bróker y la explicación lo dice.

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
from invest_ll.errors import InvestLLError
from invest_ll.estrategias.historico import UMBRAL_CAMBIO
from invest_ll.nombres import (
    base,
    equivalente,
    equivalente_corto,
    es_cripto,
    moneda_de,
    nombre_llano,
)
from invest_ll.plan import calendario
from invest_ll.portfolio.models import ActivityType

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping, Sequence

    from invest_ll.estrategias.catalogo import Ficha
    from invest_ll.portfolio.models import Activity

UMBRAL_CRIPTO: Final = Decimal(10)
"""USDT: por debajo, la orden no merece la comisión (y Binance tiene mínimos parecidos)."""
IMPORTE_MINIMO_BOLSA: Final = Decimal(1)
DECIMALES_CRIPTO: Final = Decimal("0.000001")
DECIMALES_BOLSA: Final = Decimal("0.0001")
CENTIMO: Final = Decimal("0.01")
PESO_MINIMO_BOLSA: Final = 0.005
UMBRAL_VENTA: Final = Decimal(str(UMBRAL_CAMBIO))
"""Un fondo que tienes sobra cuando pesa en tu parte de bolsa al menos esto más de lo que quiere
tu estrategia (fracción del dinero de la parte). Es el umbral de `historico.UMBRAL_CAMBIO`: lo que
la tarjeta cuenta como "algo que hacer además de aportar" es lo que aquí te pide vender."""
HOLGURA_VENTA: Final = Decimal("0.25")
"""Cuánto puede separarse lo que cobraste (euros, fondo europeo) de lo que vale tu parte en el
fondo de EE.UU. de referencia (dólares) sin que sea un error de tecleo: el cambio euro-dólar y la
diferencia entre los dos fondos. Por encima de lo que tienes y dentro de esta holgura, se anota la
venta de todo; más allá, la cifra está mal (`venta_en_unidades`)."""
UNIDADES_DE_REFERENCIA: Final = Decimal("0.00000001")
PRECIO_DE_VENTA: Final = Decimal("0.000001")
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
    posiciones_bolsa: Mapping[str, Decimal] | None = None
    """Lo que tienes en la cartera de `actividades_bolsa`; `None` = `posiciones`."""
    broker_legible: bool = True
    """False si la cartera del bróker cuenta una historia imposible: entonces no se proponen
    ventas ni se reinvierte nada (solo la aportación, que no depende de lo que tienes)."""


@dataclass(frozen=True, slots=True)
class Accion:
    """Lo mismo que `schemas_v2.Accion`, más `periodo` (desde cuándo cuenta una compra anotada) y
    `todo` (una venta de todo lo que el plan tiene de ese fondo: la estrategia sale de él)."""

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
    precio_ref_moneda: str | None
    referencia: str | None
    precio_fecha: date | None
    equivalente: str | None
    periodo: date | None = None
    todo: bool = False


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
    ventas = sum(1 for a in acciones if a.donde == "broker" and a.lado == "sell")
    compras = sum(1 for a in acciones if a.donde == "broker" and a.lado == "buy")
    if en_binance:
        partes.append(f"{en_binance} {'orden' if en_binance == 1 else 'órdenes'} en Binance")
    del_broker: list[str] = []
    if ventas:
        del_broker.append(f"{ventas} {'venta' if ventas == 1 else 'ventas'}")
    if compras:
        del_broker.append(f"{compras} {'compra' if compras == 1 else 'compras'}")
    if del_broker:
        partes.append(" y ".join(del_broker) + " en tu bróker")
    # Con ventas y compras en el bróker, la "y" ya está dentro: las dos partes van con punto y coma.
    return "Hoy toca: " + ("; " if len(del_broker) > 1 and en_binance else " y ").join(partes) + "."


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
            precio_ref_moneda=MONEDA_CRIPTO,
            referencia=None,
            precio_fecha=precio.fecha,
            equivalente=None,
        )
        (ventas if lado == "sell" else compras).append((abs(diferencia), accion))
    # Ventas antes que compras: el dinero de las ventas es el que paga las compras.
    ventas.sort(key=lambda x: x[0], reverse=True)
    compras.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in ventas] + [a for _, a in compras]


# -- Bolsa ------------------------------------------------------------------------------------


def es_de_referencia(a: Activity) -> bool:
    """Una compra o una venta de tu bróker anotada con el plan: va en unidades del fondo de EE.UU.
    de referencia (`api.plan.hecho`), así que su cantidad y su precio no son tus participaciones ni
    tu precio; su importe sí es lo que pagaste o cobraste, en euros."""
    return (
        a.type in (ActivityType.BUY, ActivityType.SELL)
        and a.source == FUENTE_PLAN
        and a.symbol is not None
        and not es_cripto(a.symbol)
    )


@dataclass(frozen=True, slots=True)
class EnElBroker:
    """Lo que tu plan tiene en tu bróker según tu registro: solo lo anotado con el plan."""

    unidades: Mapping[str, Decimal]
    """Fondo de referencia (`SPY`) -> unidades compradas con el plan y aún no vendidas con él, sin
    pasar de lo que tienes de ese fondo en la cartera (si vendiste a mano, cuenta lo que queda)."""
    libre: Decimal
    """Lo cobrado al vender con el plan que aún no has vuelto a invertir con él: las compras del
    plan gastan primero de aquí. Es el dinero sin invertir de tu parte de bolsa."""


def en_el_broker(
    actividades: Sequence[Activity],
    desde: date,
    posiciones: Mapping[str, Decimal],
    *,
    hasta: date | None = None,
) -> EnElBroker:
    """Recorre lo anotado con el plan desde `desde` (y hasta `hasta`, si se da).

    En el orden del registro: por fecha y, el mismo día, en el que se anotaron (`activities()` ya
    viene así). Las compras de la aportación anotadas por la mañana no gastan lo que cobras al
    vender por la tarde; la lista pone las ventas primero para que se anoten antes que lo que se
    paga con ellas. (Poner las ventas del día delante de todo, como se probó primero, hacía que esas
    compras de la mañana se comieran lo cobrado: con los datos reales, la venta dejaba la parte sin
    su dinero.)
    """
    del_plan = [
        a
        for a in actividades
        if es_de_referencia(a)
        and a.timestamp.date() >= desde
        and (hasta is None or a.timestamp.date() <= hasta)
    ]
    unidades: dict[str, Decimal] = {}
    libre = Decimal(0)
    for a in sorted(del_plan, key=lambda a: a.timestamp):  # estable: el mismo día, como se anotó
        simbolo = (a.symbol or "").strip().upper()
        if a.type is ActivityType.SELL:
            unidades[simbolo] = max(Decimal(0), unidades.get(simbolo, Decimal(0)) - a.quantity)
            libre += a.gross - a.fee
        else:
            unidades[simbolo] = unidades.get(simbolo, Decimal(0)) + a.quantity
            libre = max(Decimal(0), libre - (a.gross + a.fee))
    tienes: dict[str, Decimal] = {}
    for simbolo, cantidad in posiciones.items():
        clave = simbolo.strip().upper()
        tienes[clave] = tienes.get(clave, Decimal(0)) + cantidad
    topadas = {s: min(q, tienes.get(s, Decimal(0))) for s, q in unidades.items()}
    return EnElBroker(unidades={s: q for s, q in topadas.items() if q > 0}, libre=libre)


class VentaImposibleError(InvestLLError):
    """Lo que dices haber vendido no cabe en lo que tu registro dice que tienes."""


@dataclass(frozen=True, slots=True)
class VentaAnotada:
    """Cómo se anota una venta del bróker en el fondo de referencia."""

    unidades: Decimal
    precio: Decimal
    """El de referencia; si se anota la venta de todo, lo cobrado entre esas unidades (así el
    importe anotado es lo que cobraste, exacto)."""
    todo: bool


def venta_en_unidades(
    cobrado: Decimal,
    referencia: Decimal,
    tienes: Decimal,
    *,
    sale_del_todo: bool,
    nombre: str,
) -> VentaAnotada:
    """Las unidades del fondo de referencia que corresponden a lo cobrado: cobrado / referencia.

    Nunca más de lo que tienes. Si sale más (el cambio euro-dólar, o que el fondo europeo y el de
    EE.UU. no se mueven igual) y no pasa de la holgura, es que lo vendiste todo; si pasa, la cifra
    está mal. Si la acción era salir del todo y lo cobrado se queda dentro de la holgura por
    debajo, también se anota todo: si no, quedaría para siempre un resto que ya no tienes.
    """
    if tienes <= 0:
        raise VentaImposibleError(
            f"Según tu registro no tienes nada de {nombre} comprado con tu plan en esa fecha."
        )
    unidades = cobrado / referencia
    if unidades > tienes * (1 + HOLGURA_VENTA):
        valen = (tienes * referencia).quantize(Decimal(1), ROUND_HALF_UP)
        raise VentaImposibleError(
            f"Según tu registro, lo que tienes de {nombre} valía unos {llano.euros(valen)} ese día "
            f"y dices haber cobrado {llano.euros(cobrado.quantize(CENTIMO, ROUND_HALF_UP))}: es "
            "más de lo que tienes. Revisa las participaciones y el precio. Si tenías más de lo que "
            "consta aquí, anota antes lo que falte con «Anotar un movimiento»."
        )
    if unidades >= tienes or (sale_del_todo and unidades >= tienes * (1 - HOLGURA_VENTA)):
        return VentaAnotada(
            unidades=tienes,
            precio=(cobrado / tienes).quantize(PRECIO_DE_VENTA, ROUND_HALF_UP),
            todo=True,
        )
    return VentaAnotada(
        unidades=min(unidades.quantize(UNIDADES_DE_REFERENCIA, ROUND_HALF_UP), tienes),
        precio=referencia,
        todo=False,
    )


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


AVISO_PRECIO_FONDOS: Final = (
    "descarga los datos de los fondos (uv run invest-ll-quant download --etf)"
)


@dataclass(frozen=True, slots=True)
class _Aportacion:
    """Lo que toca comprar con la aportación de este periodo, fondo a fondo."""

    periodo: date | None
    importe: Decimal
    primera: bool
    lineas: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class _Venta:
    simbolo: str
    importe: Decimal
    cantidad: Decimal
    peso_actual: Decimal
    peso_objetivo: Decimal
    todo: bool


def _aportacion(e: Entrada, parte: ParteDeHoy, aviso: _Avisos) -> _Aportacion:
    periodo = calendario.periodo_actual(e.creado, e.dia, e.hoy)
    if periodo is None:
        return _Aportacion(None, Decimal(0), False, {})
    if e.pausa is not None:
        aviso(_aviso_pausa(e.pausa))
        return _Aportacion(periodo, Decimal(0), False, {})
    simbolos = parte.ficha.motor.simbolos or tuple(parte.objetivo)
    del_broker = e.actividades if e.actividades_bolsa is None else e.actividades_bolsa
    hechas = compras_del_plan(del_broker, simbolos, calendario.inicio(e.creado, e.dia))
    primera = not any(a.timestamp.date() < periodo for a in hechas)
    ya = {
        a.symbol.upper() for a in hechas if a.symbol is not None and a.timestamp.date() >= periodo
    }
    aporte = parte.mensual + (parte.inicial if primera else Decimal(0))
    lineas: dict[str, Decimal] = {}
    for simbolo, peso in parte.objetivo.items():
        if peso < PESO_MINIMO_BOLSA or simbolo.upper() in ya:
            continue
        importe = (aporte * Decimal(str(peso))).quantize(CENTIMO, rounding=ROUND_HALF_UP)
        if importe < IMPORTE_MINIMO_BOLSA:
            continue
        if simbolo not in parte.precios:
            aviso(f"Falta el precio de {nombre_llano(simbolo)}: {AVISO_PRECIO_FONDOS}.")
            continue
        lineas[simbolo] = importe
    return _Aportacion(periodo, aporte, primera, lineas)


def _sobra(
    parte: ParteDeHoy,
    tenido: Mapping[str, Decimal],
    valores: Mapping[str, Decimal],
    peso_de: Mapping[str, Decimal],
    actual: Callable[[str], Decimal],
    capital: Decimal,
    lineas: dict[str, Decimal],
) -> tuple[list[_Venta], Decimal]:
    """Los fondos que sobran y lo que liberan (las ventas y la aportación que ya no se compra)."""
    ventas: list[_Venta] = []
    liberado = Decimal(0)
    for simbolo in sorted(tenido):
        peso = peso_de.get(simbolo, Decimal(0))
        pesa = actual(simbolo)
        sobra = pesa - peso
        if sobra < UMBRAL_VENTA:
            continue
        todo = peso < Decimal(str(PESO_MINIMO_BOLSA))
        # Lo que toca vender no se compra con la aportación: esa parte también queda libre.
        pendiente = lineas.pop(simbolo, Decimal(0))
        liberado += pendiente
        importe = valores[simbolo] if todo else min(valores[simbolo], sobra * capital - pendiente)
        importe = importe.quantize(CENTIMO, rounding=ROUND_HALF_UP)
        if importe < IMPORTE_MINIMO_BOLSA:
            continue
        precio = parte.precios[simbolo].valor
        cantidad = tenido[simbolo] if todo else min(tenido[simbolo], importe / precio)
        ventas.append(
            _Venta(
                simbolo=simbolo,
                importe=importe,
                cantidad=cantidad.quantize(DECIMALES_BOLSA, rounding=ROUND_DOWN),
                peso_actual=pesa,
                peso_objetivo=peso,
                todo=todo,
            )
        )
        liberado += importe
    return ventas, liberado


def _bolsa(e: Entrada, parte: ParteDeHoy, aviso: _Avisos) -> list[Accion]:
    aportacion = _aportacion(e, parte, aviso)
    lineas = dict(aportacion.lineas)

    # Lo que el plan ya tiene en tu bróker, valorado al último cierre.
    fondos = {s.upper() for s in (parte.ficha.motor.simbolos or tuple(parte.objetivo))}
    tenido: dict[str, Decimal] = {}
    libre = Decimal(0)
    if e.broker_legible:
        en_broker = en_el_broker(
            e.actividades if e.actividades_bolsa is None else e.actividades_bolsa,
            calendario.inicio(e.creado, e.dia),
            e.posiciones if e.posiciones_bolsa is None else e.posiciones_bolsa,
        )
        tenido = {s: q for s, q in en_broker.unidades.items() if s in fondos}
        libre = en_broker.libre
    sin_precio = sorted(s for s in tenido if s not in parte.precios)
    if sin_precio:
        aviso(
            "No se puede saber si toca vender algo en tu bróker: falta el precio de "
            + ", ".join(nombre_llano(s) for s in sin_precio)
            + f"; {AVISO_PRECIO_FONDOS}."
        )
        tenido, libre = {}, Decimal(0)
    valores = {s: q * parte.precios[s].valor for s, q in tenido.items()}
    capital = sum(valores.values(), Decimal(0)) + sum(lineas.values(), Decimal(0)) + libre
    peso_de = {s.upper(): Decimal(str(w)) for s, w in parte.objetivo.items()}

    def actual(simbolo: str) -> Decimal:
        """Lo que pesa en la parte, contando lo que toca comprar hoy con la aportación."""
        if capital <= 0:
            return Decimal(0)
        return (valores.get(simbolo, Decimal(0)) + lineas.get(simbolo, Decimal(0))) / capital

    ventas: list[_Venta] = []
    liberado = libre
    if capital > 0:
        ventas, de_ventas = _sobra(parte, tenido, valores, peso_de, actual, capital, lineas)
        liberado += de_ventas

    # Lo liberado va a lo que queda por debajo de su objetivo (o se queda en liquidez).
    reinversion: dict[str, Decimal] = {}
    if liberado > 0 and e.pausa is None:
        vendidos = {v.simbolo for v in ventas}
        faltan = {
            s: peso - actual(s)
            for s, peso in peso_de.items()
            if s not in vendidos
            and peso >= Decimal(str(PESO_MINIMO_BOLSA))
            and s in parte.precios
            and peso > actual(s)
        }
        liquidez = max(Decimal(0), 1 - sum(peso_de.values(), Decimal(0)))
        total = sum(faltan.values(), Decimal(0)) + liquidez
        if total > 0:
            for s, falta in faltan.items():
                cuanto = min(liberado * falta / total, falta * capital)
                reinversion[s] = cuanto.quantize(CENTIMO, rounding=ROUND_HALF_UP)
    queda = liberado - sum(reinversion.values(), Decimal(0))

    acciones = [
        _accion_de_venta(e, parte, v, destino=_destino(e, reinversion, queda))
        for v in sorted(ventas, key=lambda v: (-v.importe, v.simbolo))
    ]
    origen = (
        "lo que sacas al vender" if ventas else "lo que cobraste al vender y aún no has invertido"
    )
    for simbolo, peso in sorted(parte.objetivo.items(), key=lambda x: (-x[1], x[0])):
        de_aporte = lineas.get(simbolo, Decimal(0))
        de_ventas = reinversion.get(simbolo.upper(), Decimal(0))
        importe = de_aporte + de_ventas
        if importe < IMPORTE_MINIMO_BOLSA:
            continue
        nombre = nombre_llano(simbolo)
        if de_aporte > 0 and aportacion.periodo is not None:
            cuanto = llano.euros(aportacion.importe)
            if aportacion.primera and parte.inicial > 0:
                cuanto += ", con lo que pones al empezar"
            detalle = (
                f"Tu aportación de {llano.mes(aportacion.periodo)} ({cuanto}): el "
                f"{llano.porcentaje(peso)} va a {nombre}, según el reparto de {parte.ficha.nombre}"
            )
            if de_ventas >= IMPORTE_MINIMO_BOLSA:
                detalle += f"; y unos {llano.euros(de_ventas.to_integral_value())} de {origen}"
        else:
            tiene = float(actual(simbolo))
            # "quiere un 2 % y tiene un 2 %" no se entiende: si redondeados coinciden, con un decimal.
            decimales = 1 if llano.porcentaje(peso) == llano.porcentaje(tiene) else 0
            detalle = (
                f"Con {origen}: tu estrategia quiere un {llano.porcentaje(peso, decimales)} de tu "
                f"parte de bolsa en {nombre} y ahora tiene un {llano.porcentaje(tiene, decimales)}"
            )
        acciones.append(
            _accion_de_compra(
                e,
                parte,
                simbolo,
                importe,
                detalle + ".",
                periodo=aportacion.periodo if de_aporte > 0 else None,
            )
        )
    return acciones


def _destino(e: Entrada, reinversion: Mapping[str, Decimal], queda: Decimal) -> str:
    """Qué pasa con el dinero de las ventas, para decirlo en cada una."""
    if e.pausa is not None:
        return (
            "con las compras en pausa, lo que saques se queda sin invertir en tu bróker hasta que "
            "acabe la pausa"
        )
    reinvertido = sum(reinversion.values(), Decimal(0))
    if reinvertido < IMPORTE_MINIMO_BOLSA:
        return (
            "lo que saques se queda sin invertir en tu bróker: tu estrategia lo quiere en "
            "liquidez por ahora"
        )
    if queda >= IMPORTE_MINIMO_BOLSA:
        return (
            f"de lo que saques, unos {llano.euros(queda.to_integral_value())} se quedan sin "
            "invertir en tu bróker (tu estrategia quiere esa parte en liquidez) y el resto va a "
            "la lista de la compra"
        )
    return "lo que saques va a la lista de la compra"


def _accion_de_venta(e: Entrada, parte: ParteDeHoy, v: _Venta, *, destino: str) -> Accion:
    precio = parte.precios[v.simbolo]
    corto = equivalente_corto(v.simbolo)
    redondo = llano.euros(v.importe.to_integral_value())
    if v.todo:
        tuyo = f"tu {corto.removeprefix('un ')}" if corto.startswith("un ") else f"tu {corto}"
        titulo = f"Vende todo {tuyo} (unos {redondo})"
        porque = (
            f"{parte.ficha.motivo_fuera}. Es el {llano.porcentaje(float(v.peso_actual))} de tu "
            f"parte de bolsa; {destino}."
        )
    else:
        titulo = f"Vende unos {redondo} de {corto}"
        porque = (
            f"Pesa el {llano.porcentaje(float(v.peso_actual))} de tu parte de bolsa y tu "
            f"estrategia quiere un {llano.porcentaje(float(v.peso_objetivo))}: vende lo que "
            f"sobra; {destino}."
        )
    return Accion(
        id=id_de_accion(e.hoy, "broker", parte.ficha.clave, v.simbolo, "sell"),
        donde="broker",
        estrategia=parte.ficha.clave,
        titulo=titulo,
        explicacion=porque,
        activo=nombre_llano(v.simbolo),
        simbolo=v.simbolo,
        par=None,
        lado="sell",
        cantidad=v.cantidad,
        importe=v.importe,
        moneda=MONEDA_BOLSA,
        precio_ref=precio.valor,
        precio_ref_moneda=moneda_de(v.simbolo),
        referencia=v.simbolo,
        precio_fecha=precio.fecha,
        equivalente=equivalente(v.simbolo),
        todo=v.todo,
    )


def _accion_de_compra(
    e: Entrada,
    parte: ParteDeHoy,
    simbolo: str,
    importe: Decimal,
    explicacion: str,
    *,
    periodo: date | None,
) -> Accion:
    precio = parte.precios[simbolo]
    return Accion(
        id=id_de_accion(e.hoy, "broker", parte.ficha.clave, simbolo, "buy"),
        donde="broker",
        estrategia=parte.ficha.clave,
        titulo=f"Compra unos {llano.euros(importe.to_integral_value())} de "
        f"{equivalente_corto(simbolo)}",
        explicacion=explicacion,
        activo=nombre_llano(simbolo),
        simbolo=simbolo,
        par=None,
        lado="buy",
        cantidad=(importe / precio.valor).quantize(DECIMALES_BOLSA, rounding=ROUND_DOWN),
        importe=importe,
        moneda=MONEDA_BOLSA,
        precio_ref=precio.valor,
        precio_ref_moneda=moneda_de(simbolo),
        referencia=simbolo,
        precio_fecha=precio.fecha,
        equivalente=equivalente(simbolo),
        periodo=periodo,
    )
