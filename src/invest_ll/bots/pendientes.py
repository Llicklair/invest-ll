"""Qué hará un bot después, en llano y con sus datos (docs/panel-v5.md §4).

Lo que cada plantilla tiene preparado, sacado de lo mismo con que decide (sus parámetros, su
memoria, su cuenta y las velas): la rejilla, sus escalones (cuáles comprará si baja y cuáles venderá
si sube); la compra periódica, la próxima compra; Bitcoin con freno, el precio que lo hará vender
(o comprar) al cerrar la vela diaria; la tendencia, cuándo vuelve a mirar y cómo van sus medias.

No decide nada: lo que hace el bot lo decide `decisiones`. Si las dos cosas no cuadraran, manda
la decisión; esto solo lo cuenta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Final, Literal

from invest_ll import llano
from invest_ll.bots.decisiones import (
    CERO,
    cerradas,
    comprado,
    media,
    niveles_rejilla,
    pct_txt,
    precio_txt,
    y,
)
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence
    from datetime import tzinfo

    from invest_ll.bots.motor import Bot
    from invest_ll.vivo.fuente import Vela

TipoPendiente = Literal["compra", "venta", "mirar", "nada"]

DURACION: Final[dict[str, timedelta]] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}
NOMBRE_INTERVALO: Final[dict[str, str]] = {
    "1m": "1 minuto",
    "5m": "5 minutos",
    "15m": "15 minutos",
    "30m": "30 minutos",
    "1h": "1 hora",
    "2h": "2 horas",
    "4h": "4 horas",
    "1d": "1 día",
}


@dataclass(frozen=True, slots=True)
class Pendiente:
    tipo: TipoPendiente
    texto: str
    coin: str | None = None
    precio: Decimal | None = None
    """El precio al que se dispara (la rejilla) o con el que compara (Bitcoin con freno)."""
    importe: Decimal | None = None
    cantidad: Decimal | None = None
    cuando: datetime | None = None


def proximo_cierre(intervalo: str, ahora: datetime) -> datetime | None:
    """Cuándo cierra la vela en curso: las de Hyperliquid empiezan en múltiplos de su duración
    desde 1970 en UTC (las diarias, a medianoche UTC)."""
    duracion = DURACION.get(intervalo)
    if duracion is None:
        return None
    segundos = duracion.total_seconds()
    siguiente = (math.floor(ahora.timestamp() / segundos) + 1) * segundos
    return datetime.fromtimestamp(siguiente, UTC)


def cuando_txt(cuando: datetime, ahora: datetime, zona: tzinfo) -> str:
    """'a las 23:30' hoy; 'el 19 oct a las 02:00' otro día (en la hora de Marcos)."""
    local, hoy = cuando.astimezone(zona), ahora.astimezone(zona)
    if local.date() == hoy.date():
        return f"a las {local:%H:%M}"
    return f"el {llano.fecha_corta(local.date())} a las {local:%H:%M}"


def pendientes(
    bot: Bot, ahora: datetime, velas: Mapping[str, Sequence[Vela]], zona: tzinfo
) -> list[Pendiente]:
    """Lo que el bot hará después, lo más cercano primero."""
    e = bot.estado
    if e.estado == "parado":
        return [Pendiente("nada", "Está parado: no hará nada hasta que lo reanudes.")]
    if e.estado == "error":
        return [Pendiente("nada", "Se paró por un error: no hará nada hasta que lo reanudes.")]
    clave = bot.plantilla.clave
    if clave == "rejilla":
        return _rejilla(bot)
    if clave == "periodica":
        return _periodica(bot, ahora, zona)
    if clave == "btc-freno":
        return _btc_freno(bot, ahora, velas, zona)
    if clave == "tendencia":
        return _tendencia(bot, ahora, velas, zona)
    return []


def _rejilla(bot: Bot) -> list[Pendiente]:
    d, m = bot.definicion, bot.estado.memoria
    coin = d.monedas[0]
    total = int(d.parametros["escalones"])
    niveles = niveles_rejilla(
        Decimal(d.parametros["precio_bajo"]), Decimal(d.parametros["precio_alto"]), total
    )
    if m.get("iniciada") != "si":
        return [
            Pendiente(
                "mirar",
                "Arranca en cuanto tenga precio: comprará los escalones que queden por encima, "
                "para venderlos si sube.",
                coin,
            )
        ]
    presupuesto = d.capital / total
    lista: list[Pendiente] = []
    for k in range(total):
        tiene = comprado(m, k)
        if tiene > 0:
            lista.append(
                Pendiente(
                    "venta",
                    f"Venderá el escalón {k + 1} ({llano.cantidad(tiene)} {coin}) si sube a "
                    f"{precio_txt(niveles[k + 1])}.",
                    coin,
                    precio=niveles[k + 1],
                    cantidad=tiene,
                )
            )
        else:
            lista.append(
                Pendiente(
                    "compra",
                    f"Comprará el escalón {k + 1} (unos {llano.numero(presupuesto)} USDC) si baja "
                    f"a {precio_txt(niveles[k])}.",
                    coin,
                    precio=niveles[k],
                    importe=presupuesto,
                )
            )
    return sorted(lista, key=lambda p: p.precio or CERO, reverse=True)


def _periodica(bot: Bot, ahora: datetime, zona: tzinfo) -> list[Pendiente]:
    d, m = bot.definicion, bot.estado.memoria
    if m.get("sin_efectivo") == "si":
        return [Pendiente("nada", "Gastó todo su capital: ya no compra más.")]
    importe = min(Decimal(d.parametros["importe"]), bot.cuenta.efectivo)
    nombres = y([nombre_hyperliquid(c) for c in d.monedas])
    repartidos = f" repartidos entre {nombres}" if len(d.monedas) > 1 else f" de {nombres}"
    coin = d.monedas[0] if len(d.monedas) == 1 else None
    proxima = datetime.fromisoformat(m["proxima"]) if m.get("proxima") else None
    if proxima is None or proxima <= ahora:
        texto = f"Compra ahora mismo: {llano.numero(importe)} USDC{repartidos}."
        return [Pendiente("compra", texto, coin, importe=importe, cuando=ahora)]
    texto = (
        f"Próxima compra {cuando_txt(proxima, ahora, zona)}: {llano.numero(importe)} USDC"
        f"{repartidos}."
    )
    return [Pendiente("compra", texto, coin, importe=importe, cuando=proxima)]


def _btc_freno(
    bot: Bot, ahora: datetime, velas: Mapping[str, Sequence[Vela]], zona: tzinfo
) -> list[Pendiente]:
    d, e = bot.definicion, bot.estado
    dias = int(d.parametros["dias"])
    coin = d.monedas[0]
    nombre = nombre_hyperliquid(coin)
    cuando = proximo_cierre("1d", ahora)
    hechas = cerradas(velas.get(coin, ()), ahora)
    a_las = cuando_txt(cuando, ahora, zona) if cuando is not None else "al cerrar la vela diaria"
    if len(hechas) < dias:
        texto = (
            f"Esperando historia de {nombre}: necesita {dias + 1} velas diarias cerradas. Vuelve a "
            f"mirar {a_las}."
        )
        return [Pendiente("mirar", texto, coin, cuando=cuando)]
    # Tras el cierre que viene, la vela de hace `dias` será la que hoy es la `dias`-ésima por el
    # final: su cierre es el listón.
    liston = hechas[-dias].cierre
    actual = e.ultimos_precios.get(coin)
    ahora_txt = (
        f" Ahora vale {precio_txt(actual)} ({pct_txt(actual / liston - 1)})." if actual else ""
    )
    if bot.cuenta.posiciones.get(coin) is not None:
        texto = (
            f"Al cerrar la vela diaria ({a_las}) venderá todo su {nombre} si vale menos de "
            f"{precio_txt(liston)} USDC, lo que valía hace {dias} días.{ahora_txt}"
        )
        return [Pendiente("venta", texto, coin, precio=liston, cuando=cuando)]
    texto = (
        f"Al cerrar la vela diaria ({a_las}) comprará {nombre} con todo su efectivo si vale más de "
        f"{precio_txt(liston)} USDC, lo que valía hace {dias} días.{ahora_txt}"
    )
    return [Pendiente("compra", texto, coin, precio=liston, cuando=cuando)]


def _tendencia(
    bot: Bot, ahora: datetime, velas: Mapping[str, Sequence[Vela]], zona: tzinfo
) -> list[Pendiente]:
    d = bot.definicion
    corta, larga = int(d.parametros["media_corta"]), int(d.parametros["media_larga"])
    intervalo = d.parametros["intervalo"]
    de_vela = f"la vela de {NOMBRE_INTERVALO.get(intervalo, intervalo)}"
    cuando = proximo_cierre(intervalo, ahora)
    a_las = f" ({cuando_txt(cuando, ahora, zona)})" if cuando is not None else ""
    lista: list[Pendiente] = []
    for coin in d.monedas:
        nombre = nombre_hyperliquid(coin)
        hechas = cerradas(velas.get(coin, ()), ahora)
        if len(hechas) < larga:
            texto = (
                f"Esperando historia de {nombre}: necesita {larga} velas de "
                f"{NOMBRE_INTERVALO.get(intervalo, intervalo)} cerradas y tiene {len(hechas)}."
            )
            lista.append(Pendiente("mirar", texto, coin, cuando=cuando))
            continue
        m_larga = media(hechas, larga)
        diferencia = media(hechas, corta) / m_larga - 1 if m_larga > 0 else CERO
        lado = "por encima" if diferencia >= 0 else "por debajo"
        como_va = (
            f" Ahora la corta va un {llano.numero(abs(diferencia) * 100, 2)} % {lado} de la larga."
        )
        if bot.cuenta.posiciones.get(coin) is not None:
            texto = (
                f"Al cerrar {de_vela}{a_las} venderá su {nombre} si la media de {corta} velas "
                f"queda por debajo de la de {larga}.{como_va}"
            )
            lista.append(Pendiente("venta", texto, coin, cuando=cuando))
        else:
            texto = (
                f"Al cerrar {de_vela}{a_las} comprará {nombre} si la media de {corta} velas queda "
                f"por encima de la de {larga}.{como_va}"
            )
            lista.append(Pendiente("compra", texto, coin, cuando=cuando))
    return lista
