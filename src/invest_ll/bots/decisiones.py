"""Qué quiere hacer cada bot ahora y por qué. Puro: no toca la red, el disco ni el reloj.

Cada plantilla es una función `Situacion -> Decision`. La situación es lo que el bot puede saber
en este momento: su efectivo y sus posiciones, el precio de ahora y las velas que le da la fuente.
**Nada de mirar el futuro**: de las velas solo cuentan las CERRADAS antes de `ahora`
(`cerradas`), aunque la fuente le pase alguna más (la vela en curso, o cualquier otra por un fallo
de la fuente). La rejilla y la compra periódica no usan velas: la rejilla mira el precio de ahora y
la periódica, su horario.

Las órdenes llevan su porqué en llano ("la media de 20 velas cruzó por encima de la de 50"); quien
las ejecuta antepone lo que pasó ("Compré 0,01 BTC a 67.010: …"), que solo se sabe después.

La memoria de un bot (lo que tiene que recordar entre decisiones: qué escalones de la rejilla
tiene comprados, cuándo le toca la siguiente compra periódica) es un `dict[str, str]`: se guarda
tal cual en JSON. Una decisión propone los cambios de memoria, que solo se adoptan si ninguna de
sus órdenes se queda sin ejecutar por falta de libro; entonces se vuelve a decidir en la vuelta
siguiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Final, Literal

from invest_ll import llano
from invest_ll.nombres import nombre_llano

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    from invest_ll.vivo.fuente import Vela

Lado = Literal["compra", "venta"]
Memoria = dict[str, str]

CERO: Final = Decimal(0)
UNO: Final = Decimal(1)
MINIMO_ORDEN: Final = Decimal(10)
"""USDC. Hyperliquid no acepta órdenes de menos de 10 USDC; un bot ficticio tampoco las hace."""
CANTIDAD: Final = Decimal("1e-8")
"""Precisión de las cantidades de moneda que guarda un bot."""


@dataclass(frozen=True, slots=True)
class Orden:
    """Lo que un bot quiere hacer.

    Una compra gasta `importe` USDC (comisión incluida) o, si no se da, `fraccion` del efectivo
    que haya al ejecutarla; nunca más del efectivo que tenga. Una venta vende `cantidad` o, sin
    ella, toda la posición.
    """

    coin: str
    lado: Lado
    porque: str
    importe: Decimal | None = None
    fraccion: Decimal | None = None
    cantidad: Decimal | None = None
    escalones: tuple[int, ...] = ()
    """Rejilla: los escalones (desde 0, de abajo arriba) a los que pertenece la orden."""
    memoria: tuple[tuple[str, str], ...] = ()
    """Lo que se apunta en la memoria en cuanto ESTA orden se ejecuta (aunque otra espere)."""


def _sin_velas() -> dict[str, Sequence[Vela]]:
    return {}


@dataclass(frozen=True, slots=True)
class Situacion:
    """Lo que el bot sabe ahora mismo."""

    ahora: datetime
    capital: Decimal
    monedas: tuple[str, ...]
    parametros: Mapping[str, str]
    efectivo: Decimal
    posiciones: Mapping[str, Decimal]
    precios: Mapping[str, Decimal]
    """Solo las monedas cuyo precio se conoce."""
    velas: Mapping[str, Sequence[Vela]] = field(default_factory=_sin_velas)
    memoria: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class Decision:
    ordenes: tuple[Orden, ...] = ()
    memoria: Memoria | None = None
    """Claves de la memoria que cambian si ninguna orden se queda esperando libro."""
    notas: tuple[str, ...] = ()
    """Lo que contar en los eventos del bot (una vez): "Esperando historia de BTC…"."""
    aviso: str | None = None
    """Lo que la tarjeta del bot debe decir mientras dure: "El precio salió del rango…"."""


# -- Ayudas ----------------------------------------------------------------------------------------


def cerradas(velas: Sequence[Vela], ahora: datetime) -> list[Vela]:
    """Las velas que ya habían cerrado en `ahora`, de la más antigua a la más reciente.

    Es la frontera contra el futuro: la vela en curso aún se mueve, y una vela que termina después
    de `ahora` no se podía conocer.
    """
    return [v for v in velas if v.cerrada and v.fin <= ahora]


def media(velas: Sequence[Vela], n: int) -> Decimal:
    """La media de los cierres de las últimas `n` velas."""
    ultimas = velas[-n:]
    return sum((v.cierre for v in ultimas), CERO) / len(ultimas)


def precio_txt(precio: Decimal) -> str:
    """'67.010' por encima de 1.000; '2,45' entre 1 y 1.000; '0,00001234' por debajo."""
    if precio >= 1000:
        return llano.numero(precio, 0)
    if precio >= 1:
        return llano.numero(precio, 2)
    return llano.cantidad(precio, 8)


def pct_txt(fraccion: Decimal) -> str:
    """'+4,2 %' o '-3,1 %'."""
    signo = "+" if fraccion >= 0 else "-"
    return f"{signo}{llano.numero(abs(fraccion) * 100, 1)} %"


def horas_txt(horas: int) -> str:
    return "hora" if horas == 1 else f"{horas} horas"


def y(textos: Sequence[str]) -> str:
    """'Bitcoin', 'Bitcoin y Ethereum', 'Bitcoin, Ethereum y Solana'."""
    if len(textos) <= 1:
        return "".join(textos)
    return f"{', '.join(textos[:-1])} y {textos[-1]}"


def _entero(parametros: Mapping[str, str], clave: str) -> int:
    return int(parametros[clave])


def _decimal(parametros: Mapping[str, str], clave: str) -> Decimal:
    return Decimal(parametros[clave])


def _tiene(s: Situacion, coin: str) -> bool:
    return s.posiciones.get(coin, CERO) > 0


# -- Bitcoin con freno -----------------------------------------------------------------------------


def btc_freno(s: Situacion) -> Decision:
    """Dentro mientras la moneda vale más que hace `dias` velas diarias; en USDC si no.

    La regla de `quant.strategies.TrendAsset` (la de "Bitcoin con freno" del catálogo): el cierre
    de la última vela diaria cerrada contra el de `dias` velas antes.
    """
    dias = _entero(s.parametros, "dias")
    coin = s.monedas[0]
    velas = cerradas(s.velas.get(coin, ()), s.ahora)
    if len(velas) < dias + 1:
        return Decision(
            notas=(f"Esperando historia de {coin}: necesita {dias + 1} velas diarias cerradas.",)
        )
    cambio = velas[-1].cierre / velas[-1 - dias].cierre - 1
    nombre = nombre_llano(coin)
    if cambio > 0 and not _tiene(s, coin) and s.efectivo >= MINIMO_ORDEN:
        porque = f"{nombre} vale un {pct_txt(cambio)} respecto a hace {dias} días"
        return Decision(ordenes=(Orden(coin, "compra", porque, fraccion=UNO),))
    if cambio <= 0 and _tiene(s, coin):
        porque = f"{nombre} vale un {pct_txt(cambio)} respecto a hace {dias} días: paso a USDC"
        return Decision(ordenes=(Orden(coin, "venta", porque),))
    return Decision()


# -- Tendencia rápida ------------------------------------------------------------------------------


def tendencia(s: Situacion) -> Decision:
    """Dentro de cada moneda mientras su media corta está por encima de la larga.

    Con varias monedas, cada una tiene su parte del capital: una compra gasta el efectivo
    repartido entre las monedas que quedarán fuera (las que no tienen posición y las que se venden
    en esta misma decisión), así que la parte de una moneda que está fuera sigue esperándola.
    """
    corta = _entero(s.parametros, "media_corta")
    larga = _entero(s.parametros, "media_larga")
    intervalo = s.parametros["intervalo"]
    ventas: list[Orden] = []
    compras: list[tuple[str, str]] = []
    notas: list[str] = []
    for coin in s.monedas:
        velas = cerradas(s.velas.get(coin, ()), s.ahora)
        if len(velas) < larga:
            notas.append(
                f"Esperando historia de {coin}: necesita {larga} velas de {intervalo} cerradas."
            )
            continue
        diferencia = media(velas, corta) - media(velas, larga)
        antes = None
        if len(velas) > larga:
            antes = media(velas[:-1], corta) - media(velas[:-1], larga)
        if diferencia > 0 and not _tiene(s, coin):
            verbo = "cruzó" if antes is not None and antes <= 0 else "está"
            compras.append((coin, f"la media de {corta} velas {verbo} por encima de la de {larga}"))
        elif diferencia < 0 and _tiene(s, coin):
            verbo = "cruzó" if antes is not None and antes >= 0 else "está"
            porque = f"la media de {corta} velas {verbo} por debajo de la de {larga}"
            ventas.append(Orden(coin, "venta", porque))
    fuera = sum(1 for c in s.monedas if not _tiene(s, c)) + len(ventas)
    ordenes = list(ventas)
    # Sin ventas en esta decisión, el efectivo de ahora es el que habrá al comprar: si no llega al
    # mínimo por moneda, no se propone una compra que no se podría hacer.
    if compras and (ventas or s.efectivo / fuera >= MINIMO_ORDEN):
        fraccion = UNO / fuera
        ordenes.extend(Orden(c, "compra", porque, fraccion=fraccion) for c, porque in compras)
    return Decision(ordenes=tuple(ordenes), notas=tuple(notas))


# -- Rejilla ---------------------------------------------------------------------------------------


def niveles_rejilla(bajo: Decimal, alto: Decimal, escalones: int) -> list[Decimal]:
    """Los `escalones + 1` precios que separan los escalones, de abajo arriba. El escalón `k`
    compra en `niveles[k]` y vende en `niveles[k + 1]`."""
    paso = (alto - bajo) / escalones
    return [bajo + paso * k for k in range(escalones + 1)]


def comprado(memoria: Mapping[str, str], k: int) -> Decimal:
    """Lo que tiene comprado el escalón `k` (cero si espera para comprar)."""
    return Decimal(memoria.get(f"escalon_{k}", "0"))


def _escalones_txt(escalones: Sequence[int], total: int) -> str:
    """'el escalón 3 de 10' o 'los escalones 3, 4 y 5 de 10' (contados desde 1)."""
    numeros = [str(k + 1) for k in escalones]
    if len(numeros) == 1:
        return f"el escalón {numeros[0]} de {total}"
    return f"los escalones {y(numeros)} de {total}"


def rejilla(s: Situacion) -> Decision:
    """Compra cada escalón cuando el precio baja a él y lo vende cuando sube al siguiente.

    Cada escalón tiene la misma parte del capital. Al empezar compra los escalones que quedan
    por encima del precio (los que habría comprado si el precio hubiera bajado hasta aquí), para
    poder venderlos si sube; los de abajo esperan en USDC. Decide con el precio de ahora.
    """
    coin = s.monedas[0]
    precio = s.precios.get(coin)
    if precio is None:
        return Decision()
    total = _entero(s.parametros, "escalones")
    bajo = _decimal(s.parametros, "precio_bajo")
    alto = _decimal(s.parametros, "precio_alto")
    niveles = niveles_rejilla(bajo, alto, total)
    presupuesto = s.capital / total
    m = s.memoria
    rango = f"{precio_txt(bajo)} a {precio_txt(alto)}"

    # Fuera del rango hasta que vuelva un escalón dentro (cuando la rejilla vuelve a operar): sin
    # ese margen, un precio que ronda el borde entraría y saldría en cada vuelta.
    previo = m.get("fuera", "")
    if previo == "arriba" and precio > niveles[-2]:
        fuera = "arriba"
    elif previo == "abajo" and precio < niveles[1]:
        fuera = "abajo"
    else:
        fuera = "abajo" if precio < bajo else "arriba" if precio > alto else ""
    aviso = None
    if fuera == "abajo":
        aviso = (
            f"El precio cayó por debajo del rango ({rango}): la rejilla lo tiene todo comprado y "
            "pierde mientras siga bajando."
        )
    elif fuera == "arriba":
        aviso = (
            f"El precio superó el rango ({rango}): la rejilla lo ha vendido todo y espera en USDC "
            "a que vuelva a bajar."
        )
    notas: tuple[str, ...] = ()
    if fuera != previo and m.get("iniciada") == "si":
        notas = (aviso,) if aviso else (f"El precio volvió al rango ({rango}): vuelve a operar.",)
    cambios: Memoria = {"fuera": fuera, "iniciada": "si"}

    if m.get("iniciada") != "si":
        arriba = [k for k in range(total) if niveles[k] >= precio]
        if not arriba:
            return Decision(memoria=cambios, aviso=aviso)
        cuales = "el escalón" if len(arriba) == 1 else f"los {len(arriba)} escalones"
        porque = (
            f"arranque de la rejilla: compro {cuales} que quedan por encima del precio, para "
            "venderlos si sube"
        )
        orden = Orden(
            coin, "compra", porque, importe=presupuesto * len(arriba), escalones=tuple(arriba)
        )
        return Decision(ordenes=(orden,), memoria=cambios, aviso=aviso)

    ordenes: list[Orden] = []
    ventas = [k for k in range(total) if comprado(m, k) > 0 and precio >= niveles[k + 1]]
    if ventas:
        cantidad = sum((comprado(m, k) for k in ventas), CERO)
        porque = (
            f"el precio subió a {precio_txt(niveles[ventas[0] + 1])}: vendo "
            f"{_escalones_txt(ventas, total)}, comprado más abajo"
            if len(ventas) == 1
            else f"el precio subió a {precio_txt(precio)}: vendo {_escalones_txt(ventas, total)}"
        )
        ordenes.append(Orden(coin, "venta", porque, cantidad=cantidad, escalones=tuple(ventas)))
    compras = [k for k in range(total) if comprado(m, k) <= 0 and precio <= niveles[k]]
    if compras and (ventas or s.efectivo >= MINIMO_ORDEN):
        porque = (
            f"el precio bajó a {precio_txt(niveles[compras[0]])}: compro "
            f"{_escalones_txt(compras, total)}"
            if len(compras) == 1
            else f"el precio bajó a {precio_txt(precio)}: compro {_escalones_txt(compras, total)}"
        )
        importe = presupuesto * len(compras)
        ordenes.append(Orden(coin, "compra", porque, importe=importe, escalones=tuple(compras)))
    return Decision(ordenes=tuple(ordenes), memoria=cambios, notas=notas, aviso=aviso)


def aplicar_rejilla(memoria: Mapping[str, str], orden: Orden, cantidad: Decimal) -> Memoria:
    """La memoria después de ejecutar `orden` por `cantidad`: los escalones vendidos vuelven a
    esperar; los comprados se reparten lo comprado a partes iguales (tienen el mismo capital)."""
    nueva = dict(memoria)
    if orden.lado == "venta":
        for k in orden.escalones:
            nueva[f"escalon_{k}"] = "0"
        return nueva
    n = len(orden.escalones)
    parte = (cantidad / n).quantize(CANTIDAD, rounding=ROUND_DOWN)
    for i, k in enumerate(orden.escalones):
        nueva[f"escalon_{k}"] = str(parte if i < n - 1 else cantidad - parte * (n - 1))
    return nueva


# -- Compra periódica ------------------------------------------------------------------------------


def periodica(s: Situacion) -> Decision:
    """Compra `importe` USDC repartidos entre sus monedas en cuanto se despliega y luego cada
    `cada_horas`. Si una compra le pilla con el panel cerrado, se la salta: no recupera las que
    perdió, sigue con su horario.

    Cada moneda apunta qué compra del horario ya hizo (`hecha_<coin>`): si una espera libro, al
    reintentarlo no se repite la de las demás.
    """
    importe = _decimal(s.parametros, "importe")
    horas = _entero(s.parametros, "cada_horas")
    cada = timedelta(hours=horas)
    m = s.memoria
    agotado = "Gastó todo su capital: ya no compra más (lo comprado se sigue valorando)."
    proxima = datetime.fromisoformat(m["proxima"]) if m.get("proxima") else None
    if proxima is not None and s.ahora < proxima:
        return Decision(aviso=agotado if m.get("sin_efectivo") == "si" else None)

    turno = m.get("proxima") or "primera"
    base = proxima or s.ahora
    siguiente = base + cada * ((s.ahora - base) // cada + 1)
    cambios: Memoria = {"proxima": siguiente.isoformat(), "sin_efectivo": ""}
    gastar = min(importe, s.efectivo)
    por_moneda = gastar / len(s.monedas)
    pendientes = [c for c in s.monedas if m.get(f"hecha_{c}") != turno]
    if por_moneda < MINIMO_ORDEN:
        cambios["sin_efectivo"] = "si"
        if m.get("sin_efectivo") == "si":
            return Decision(memoria=cambios, aviso=agotado)
        nota = (
            f"Le quedan {llano.numero(s.efectivo)} USDC, menos que el mínimo de "
            f"{llano.numero(MINIMO_ORDEN, 0)} USDC por orden: deja de comprar."
        )
        return Decision(memoria=cambios, notas=(nota,), aviso=agotado)
    repartido = " repartidos" if len(s.monedas) > 1 else ""
    porque = f"toca la compra de cada {horas_txt(horas)} ({llano.numero(importe)} USDC{repartido})"
    ordenes = tuple(
        Orden(c, "compra", porque, importe=por_moneda, memoria=((f"hecha_{c}", turno),))
        for c in pendientes
    )
    return Decision(ordenes=ordenes, memoria=cambios)
