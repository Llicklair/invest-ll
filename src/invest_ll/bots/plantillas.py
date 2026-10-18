"""Las plantillas de bot (docs/panel-v3-vivo.md §3): qué hace cada una en llano y con qué decide.

Cada plantilla junta lo que se le dice al usuario (nombre, cómo funciona, avisos, evidencia,
riesgo, cuántas operaciones esperar, sus parámetros con su explicación) con la función que decide
(`decisiones`). Así la tarjeta no puede describir una cosa y el bot hacer otra.

**Evidencia, sin vender humo.** Solo "Bitcoin con freno" tiene detrás algo medido: es la regla de
la estrategia del catálogo, probada sobre el pasado y en prueba real desde el 15 oct 2026. La
tendencia y la rejilla no tienen ninguna, y lo dicen en la tarjeta de cada bot, no solo al crearlo.

`validar` comprueba lo que llega al desplegar y deja los parámetros completos y normalizados (lo
que falta, con su valor por defecto); los errores, en llano.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final, Literal

from invest_ll import llano
from invest_ll.bots import decisiones
from invest_ll.bots.decisiones import MINIMO_ORDEN
from invest_ll.errors import InvestLLError
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping, Sequence

    from invest_ll.bots.decisiones import Decision, Memoria, Orden, Situacion

TipoParametro = Literal["entero", "decimal", "opcion", "intervalo"]
TipoEvidencia = Literal["pasado", "prueba_real", "ninguna"]

RIESGO_TEXTO: Final = {1: "Tranquila", 2: "Suave", 3: "Moderada", 4: "Movida", 5: "Muy movida"}
"""Las mismas palabras que el catálogo de estrategias (`estrategias.catalogo.RIESGO_TEXTO`)."""

CAPITAL_MAXIMO: Final = Decimal(10_000_000)
MAX_MONEDAS: Final = 5
RANGO_POR_DEFECTO: Final = Decimal("0.10")
"""La rejilla, sin rango: del 10 % por debajo al 10 % por encima del precio al desplegar."""
_COIN = re.compile(r"^[A-Za-z0-9]{1,20}$")


class BotInvalidoError(InvestLLError):
    """Lo que se pide al desplegar no vale; el texto es para enseñárselo al usuario."""


@dataclass(frozen=True, slots=True)
class Evidencia:
    tipo: TipoEvidencia
    texto: str


@dataclass(frozen=True, slots=True)
class Parametro:
    clave: str
    nombre: str
    explicacion: str
    tipo: TipoParametro
    defecto: str
    """Vacío si se calcula al desplegar (el rango de la rejilla)."""
    minimo: str | None = None
    maximo: str | None = None
    opciones: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Plantilla:
    clave: str
    nombre: str
    frase: str
    como_funciona: tuple[str, ...]
    avisos: tuple[str, ...]
    evidencia: Evidencia
    riesgo: int
    operaciones_esperadas: str
    monedas: Literal["una", "varias"]
    monedas_sugeridas: tuple[str, ...]
    parametros: tuple[Parametro, ...]
    decidir: Callable[[Situacion], Decision]
    aplicar: Callable[[Mapping[str, str], Orden, Decimal], Memoria] | None = None
    """Cómo cambia la memoria al ejecutarse una orden (la rejilla apunta sus escalones)."""
    intervalo_fijo: str | None = None
    """Las velas con que decide, si no las elige el usuario. Sin velas (rejilla, periódica): None."""

    @property
    def riesgo_texto(self) -> str:
        return RIESGO_TEXTO[self.riesgo]

    def parametro(self, clave: str) -> Parametro | None:
        return next((p for p in self.parametros if p.clave == clave), None)

    def intervalo(self, parametros: Mapping[str, str]) -> str | None:
        """El intervalo de las velas con que decide, o None si no usa velas."""
        return parametros.get("intervalo", self.intervalo_fijo)

    def velas_necesarias(self, parametros: Mapping[str, str]) -> int:
        """Cuántas velas cerradas necesita para decidir (más una para saber si hubo cruce)."""
        if self.clave == "btc-freno":
            return int(parametros["dias"]) + 1
        if "media_larga" in parametros:
            return int(parametros["media_larga"]) + 1
        return 0

    def evidencia_para(self, monedas: Sequence[str]) -> Evidencia:
        """La evidencia de un bot concreto: la regla de Bitcoin con freno se probó con Bitcoin."""
        if self.clave == "btc-freno" and tuple(monedas) != ("BTC",):
            cuales = decisiones.y([nombre_hyperliquid(c) for c in monedas])
            return Evidencia(
                "ninguna",
                f"La regla de «Bitcoin con freno» se probó con Bitcoin; con {cuales} no hay "
                "ninguna prueba.",
            )
        return self.evidencia


# -- Las cuatro plantillas -------------------------------------------------------------------------

BTC_FRENO: Final = Plantilla(
    clave="btc-freno",
    nombre="Bitcoin con freno",
    frase="Dentro de Bitcoin mientras sube; en USDC cuando lleva un mes bajando.",
    como_funciona=(
        "Una vez al día, al cerrar la vela diaria, mira si Bitcoin vale más que hace 30 días.",
        "Si vale más, tiene todo su capital en Bitcoin; si vale menos, lo vende y espera en USDC.",
        "Es la regla de «Bitcoin con freno» del catálogo de estrategias, aplicada de una vez y no "
        "por tramos.",
    ),
    avisos=(
        "Pasa casi la mitad del tiempo fuera, en USDC: habrá rachas en que lo haga peor que "
        "mantener Bitcoin.",
        "Las velas diarias de Hyperliquid cierran a medianoche UTC (la 1:00 o las 2:00 en España): "
        "decide entonces, si el motor de los bots está en marcha (el ordenador encendido).",
    ),
    evidencia=Evidencia(
        "prueba_real",
        "La de «Bitcoin con freno» del catálogo: probada sobre el pasado y en prueba real desde "
        "el 15 oct 2026. Este bot la aplica de una vez, sin tramos.",
    ),
    riesgo=4,
    operaciones_esperadas="Unas pocas al mes",
    monedas="una",
    monedas_sugeridas=("BTC",),
    parametros=(
        Parametro(
            clave="dias",
            nombre="Días del filtro",
            explicacion=(
                "Con cuántos días atrás compara el precio. Menos días: reacciona antes, pero "
                "cambia más veces y paga más comisiones."
            ),
            tipo="entero",
            defecto="30",
            minimo="2",
            maximo="365",
        ),
    ),
    decidir=decisiones.btc_freno,
    intervalo_fijo="1d",
)

TENDENCIA: Final = Plantilla(
    clave="tendencia",
    nombre="Tendencia rápida",
    frase="Compra cuando la media corta cruza por encima de la larga; vende cuando cruza por debajo.",
    como_funciona=(
        "Al cierre de cada vela (por defecto, cada hora) calcula dos medias del precio: la de las "
        "últimas 20 velas y la de las últimas 50.",
        "Si la corta está por encima de la larga, está dentro de la moneda; si está por debajo, "
        "vende y espera en USDC.",
        "Con varias monedas reparte el capital a partes iguales y decide cada una por su cuenta.",
    ),
    avisos=(
        "Ninguna prueba: es un experimento. Nadie ha comprobado que gane.",
        "Cuando el precio va de lado da señales falsas: compra caro, vende barato y paga comisión "
        "cada vez.",
        "Con velas más cortas opera más y paga más comisiones.",
    ),
    evidencia=Evidencia(
        "ninguna", "Ninguna: es un experimento. No se ha probado ni sobre el pasado ni en real."
    ),
    riesgo=4,
    operaciones_esperadas="Varias a la semana",
    monedas="varias",
    monedas_sugeridas=("BTC", "ETH"),
    parametros=(
        Parametro(
            clave="media_corta",
            nombre="Media corta",
            explicacion="Cuántas velas mira la media rápida. Más corta: reacciona antes y se "
            "equivoca más.",
            tipo="entero",
            defecto="20",
            minimo="2",
            maximo="200",
        ),
        Parametro(
            clave="media_larga",
            nombre="Media larga",
            explicacion="Cuántas velas mira la media lenta, la que marca la tendencia. Tiene que "
            "ser mayor que la corta.",
            tipo="entero",
            defecto="50",
            minimo="3",
            maximo="500",
        ),
        Parametro(
            clave="intervalo",
            nombre="Velas de",
            explicacion="Cada cuánto cierra una vela; el bot decide al cierre de cada una. Más "
            "corto: más operaciones y más comisiones.",
            tipo="intervalo",
            defecto="1h",
            opciones=("15m", "30m", "1h", "2h", "4h"),
        ),
    ),
    decidir=decisiones.tendencia,
)

REJILLA: Final = Plantilla(
    clave="rejilla",
    nombre="Rejilla",
    frase="Reparte compras escalonadas en un rango de precios y vende cada escalón cuando sube.",
    como_funciona=(
        "Divide el rango (por defecto, del 10 % por debajo al 10 % por encima del precio al "
        "desplegar) en escalones iguales, cada uno con la misma parte del capital.",
        "Al desplegar compra los escalones que quedan por encima del precio; los de abajo esperan "
        "en USDC.",
        "Cuando el precio baja a un escalón, lo compra; cuando sube al siguiente, lo vende. Cada "
        "ida y vuelta gana la distancia entre escalones, menos las comisiones.",
    ),
    avisos=(
        "Ninguna prueba: es un experimento.",
        "Gana si el precio oscila dentro del rango. Si sale por abajo se queda con todo comprado "
        "y pierde; si sale por arriba lo ha vendido todo y no gana con la subida.",
        "Decide con cada precio, y cada escalón paga comisión al comprarse y al venderse.",
    ),
    evidencia=Evidencia(
        "ninguna",
        "Ninguna: gana si el precio oscila dentro del rango, pierde si sale por abajo.",
    ),
    riesgo=4,
    operaciones_esperadas="Una o dos al día si el precio oscila dentro del rango; ninguna fuera",
    monedas="una",
    monedas_sugeridas=("BTC", "ETH"),
    parametros=(
        Parametro(
            clave="precio_bajo",
            nombre="Precio bajo",
            explicacion="Por debajo de este precio ya no compra más. Vacío: un 10 % por debajo "
            "del precio al desplegar.",
            tipo="decimal",
            defecto="",
        ),
        Parametro(
            clave="precio_alto",
            nombre="Precio alto",
            explicacion="Por encima de este precio lo ha vendido todo. Vacío: un 10 % por encima "
            "del precio al desplegar.",
            tipo="decimal",
            defecto="",
        ),
        Parametro(
            clave="escalones",
            nombre="Escalones",
            explicacion="En cuántos tramos se divide el rango. Más escalones: operaciones más "
            "pequeñas y más frecuentes, y más comisiones.",
            tipo="entero",
            defecto="10",
            minimo="2",
            maximo="50",
        ),
    ),
    decidir=decisiones.rejilla,
    aplicar=decisiones.aplicar_rejilla,
)

PERIODICA: Final = Plantilla(
    clave="periodica",
    nombre="Compra periódica",
    frase="Compra una cantidad fija cada cierto tiempo, sin mirar el precio.",
    como_funciona=(
        "Hace la primera compra al desplegarlo y luego repite cada 24 horas (o lo que elijas).",
        "Cada vez gasta el mismo importe en USDC, repartido a partes iguales entre sus monedas.",
        "No vende nunca. Cuando se acaba el capital, deja de comprar.",
    ),
    avisos=(
        "No vende nunca: en una caída grande, cae con la moneda.",
        "Solo compra con el motor de los bots en marcha: si el ordenador está apagado o dormido "
        "cuando le toca, se salta esa compra.",
    ),
    evidencia=Evidencia(
        "pasado",
        "La de «aportar y mantener»: no intenta acertar el momento, así que gana o pierde lo que "
        "gane o pierda la moneda.",
    ),
    riesgo=5,
    operaciones_esperadas="Una por moneda cada vez que le toca (por defecto, una al día)",
    monedas="varias",
    monedas_sugeridas=("BTC", "ETH"),
    parametros=(
        Parametro(
            clave="importe",
            nombre="Importe por compra",
            explicacion="Cuántos USDC gasta cada vez, repartidos entre sus monedas. Hyperliquid "
            "no acepta órdenes de menos de 10 USDC.",
            tipo="decimal",
            defecto="100",
            minimo="10",
        ),
        Parametro(
            clave="cada_horas",
            nombre="Cada cuántas horas",
            explicacion="Cada cuántas horas compra. 24 es una vez al día; 168, una a la semana.",
            tipo="entero",
            defecto="24",
            minimo="1",
            maximo="720",
        ),
    ),
    decidir=decisiones.periodica,
)

PLANTILLAS: Final[dict[str, Plantilla]] = {
    p.clave: p for p in (BTC_FRENO, TENDENCIA, REJILLA, PERIODICA)
}


def plantilla(clave: str) -> Plantilla:
    try:
        return PLANTILLAS[clave]
    except KeyError:
        opciones = ", ".join(PLANTILLAS)
        raise BotInvalidoError(
            f"No hay ninguna plantilla «{clave}». Las que hay: {opciones}."
        ) from None


# -- Validación ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Validado:
    plantilla: Plantilla
    nombre: str
    monedas: tuple[str, ...]
    capital: Decimal
    parametros: dict[str, str]


def _numero(texto: str, p: Parametro) -> Decimal:
    """'60000', '60000.5' o '60000,5' (coma decimal, sin separador de miles)."""
    limpio = texto.strip().replace(" ", "")
    if "," in limpio and "." not in limpio:
        limpio = limpio.replace(",", ".")
    try:
        valor = Decimal(limpio)
    except InvalidOperation:
        raise BotInvalidoError(f"«{p.nombre}» tiene que ser un número, y es «{texto}».") from None
    if not valor.is_finite():
        raise BotInvalidoError(f"«{p.nombre}» tiene que ser un número normal.")
    return valor


def _en_su_rango(valor: Decimal, p: Parametro) -> None:
    minimo = Decimal(p.minimo) if p.minimo is not None else None
    maximo = Decimal(p.maximo) if p.maximo is not None else None
    if minimo is not None and maximo is not None and not minimo <= valor <= maximo:
        raise BotInvalidoError(f"«{p.nombre}» tiene que estar entre {p.minimo} y {p.maximo}.")
    if minimo is not None and valor < minimo:
        raise BotInvalidoError(f"«{p.nombre}» tiene que ser {p.minimo} o más.")
    if maximo is not None and valor > maximo:
        raise BotInvalidoError(f"«{p.nombre}» no puede pasar de {p.maximo}.")


def _parametro(p: Parametro, texto: str) -> str:
    """El valor normalizado (como texto) o un error en llano."""
    if p.tipo in ("opcion", "intervalo"):
        opciones = p.opciones or ()
        if texto.strip() not in opciones:
            raise BotInvalidoError(
                f"«{p.nombre}» tiene que ser una de estas: {', '.join(opciones)}."
            )
        return texto.strip()
    valor = _numero(texto, p)
    if p.tipo == "entero":
        if valor != valor.to_integral_value():
            raise BotInvalidoError(f"«{p.nombre}» tiene que ser un número entero, sin decimales.")
        valor = valor.to_integral_value()
    _en_su_rango(valor, p)
    return format(valor.normalize(), "f")


def _monedas(
    p: Plantilla, monedas: Sequence[str], precio: Callable[[str], Decimal | None]
) -> tuple[str, ...]:
    limpias: list[str] = []
    for texto in monedas:
        coin = texto.strip()
        if coin.islower():
            coin = coin.upper()
        if not _COIN.match(coin):
            raise BotInvalidoError(
                f"«{texto}» no parece el nombre de una moneda de Hyperliquid (BTC, ETH, SOL…)."
            )
        if coin in limpias:
            raise BotInvalidoError(f"{coin} está repetida: pon cada moneda una vez.")
        limpias.append(coin)
    if not limpias:
        raise BotInvalidoError("Elige al menos una moneda.")
    if p.monedas == "una" and len(limpias) > 1:
        raise BotInvalidoError(f"«{p.nombre}» funciona con una sola moneda.")
    if len(limpias) > MAX_MONEDAS:
        raise BotInvalidoError(f"Un bot lleva como mucho {MAX_MONEDAS} monedas.")
    sin_precio = [c for c in limpias if precio(c) is None]
    if sin_precio:
        raise BotInvalidoError(
            f"Hyperliquid no da precio de {', '.join(sin_precio)} ahora mismo: revisa el nombre "
            "(BTC, ETH, SOL…) o espera a que lleguen los precios."
        )
    return tuple(limpias)


def _rango_de_la_rejilla(parametros: dict[str, str], coin: str, precio: Decimal | None) -> None:
    """Completa el rango vacío con ±10 % del precio de ahora y comprueba que tenga sentido."""
    for clave, signo in (("precio_bajo", -1), ("precio_alto", 1)):
        if parametros.get(clave, "") == "":
            if precio is None:
                raise BotInvalidoError(
                    f"Aún no hay precio de {coin} para calcular el rango: escribe el precio bajo "
                    "y el alto, o espera a que lleguen los precios."
                )
            valor = _cinco_cifras(precio * (1 + signo * RANGO_POR_DEFECTO))
            parametros[clave] = format(valor, "f")
    bajo, alto = Decimal(parametros["precio_bajo"]), Decimal(parametros["precio_alto"])
    if bajo <= 0:
        raise BotInvalidoError("«Precio bajo» tiene que ser mayor que cero.")
    if alto <= bajo:
        raise BotInvalidoError(
            f"«Precio alto» ({llano.cantidad(alto)}) tiene que ser mayor que «Precio bajo» "
            f"({llano.cantidad(bajo)})."
        )


def _cinco_cifras(valor: Decimal) -> Decimal:
    """Un precio con cinco cifras significativas, como los de Hyperliquid (60.309, 2.161,4)."""
    return valor.quantize(Decimal(1).scaleb(valor.adjusted() - 4))


def validar(
    clave: str,
    nombre: str,
    monedas: Sequence[str],
    capital: Decimal,
    parametros: Mapping[str, str],
    precio: Callable[[str], Decimal | None],
) -> Validado:
    """Lo que llega al desplegar, comprobado y completo. `precio(coin)` es el precio de ahora
    (None si no se conoce): una moneda sin precio no se acepta."""
    p = plantilla(clave)
    nombre = nombre.strip()
    if not nombre:
        raise BotInvalidoError("Ponle un nombre al bot.")
    coins = _monedas(p, monedas, precio)
    if not capital.is_finite() or capital <= 0:
        raise BotInvalidoError("El capital tiene que ser mayor que cero.")
    if capital > CAPITAL_MAXIMO:
        raise BotInvalidoError(
            f"Como mucho {llano.numero(CAPITAL_MAXIMO, 0)} USDC ficticios por bot."
        )

    sobran = sorted(set(parametros) - {q.clave for q in p.parametros})
    if sobran:
        raise BotInvalidoError(
            f"«{p.nombre}» no tiene {'el parámetro' if len(sobran) == 1 else 'los parámetros'} "
            f"{', '.join(sobran)}."
        )
    normalizados: dict[str, str] = {}
    for q in p.parametros:
        texto = parametros.get(q.clave, "")
        if texto.strip() == "":
            texto = q.defecto
        normalizados[q.clave] = "" if texto == "" else _parametro(q, texto)

    minimo_txt = f"{llano.numero(MINIMO_ORDEN, 0)} USDC"
    if p is TENDENCIA and int(normalizados["media_larga"]) <= int(normalizados["media_corta"]):
        raise BotInvalidoError(
            f"La media larga ({normalizados['media_larga']}) tiene que ser mayor que la "
            f"corta ({normalizados['media_corta']})."
        )
    if p is REJILLA:
        _rango_de_la_rejilla(normalizados, coins[0], precio(coins[0]))
        parte = capital / int(normalizados["escalones"])
        if parte < MINIMO_ORDEN:
            raise BotInvalidoError(
                f"Cada escalón tendría {llano.numero(parte)} USDC y Hyperliquid no acepta órdenes "
                f"de menos de {minimo_txt}: pon más capital o menos escalones."
            )
    elif p is PERIODICA:
        importe = Decimal(normalizados["importe"])
        if importe > capital:
            raise BotInvalidoError(
                f"El importe por compra ({llano.numero(importe)} USDC) no puede pasar del capital "
                f"({llano.numero(capital)} USDC)."
            )
        if importe / len(coins) < MINIMO_ORDEN:
            raise BotInvalidoError(
                f"Repartido entre {len(coins)} monedas, cada compra sería de "
                f"{llano.numero(importe / len(coins))} USDC, y Hyperliquid no acepta órdenes de "
                f"menos de {minimo_txt}."
            )
    elif capital / len(coins) < MINIMO_ORDEN:
        raise BotInvalidoError(
            f"Con {llano.numero(capital)} USDC entre {len(coins)} monedas, cada compra no llegaría "
            f"al mínimo de {minimo_txt} de Hyperliquid."
        )
    return Validado(
        plantilla=p, nombre=nombre, monedas=coins, capital=capital, parametros=normalizados
    )
