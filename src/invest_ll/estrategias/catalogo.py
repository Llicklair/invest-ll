"""El catálogo: qué es cada estrategia en llano y con qué motor se ejecuta (docs/panel-v2.md, 5).

Cada ficha junta dos cosas que no deben separarse: lo que se le dice al usuario (nombre, frase,
riesgo, avisos) y la configuración EXACTA del estudio del 2026-10-16 con la que se calculan sus
cifras (`Motor`). Así la tarjeta que dice "Bitcoin con freno" no puede describir una cosa y medir
otra. Las cifras no están aquí: salen de ejecutar `Motor` sobre los datos (`historico`).

Seis estrategias para el camino principal y el resto en Laboratorio (`laboratorio=True`): la
cartera prerregistrada, la rotación de antes (retirada, con su porqué) y las demás del estudio de
ETF.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final, Literal

from invest_ll.nombres import es_cripto, nombre_llano
from invest_ll.quant.engine import BINANCE_SPOT, Costs
from invest_ll.quant.etf_study import ASSETS, CASH, ETF_COSTS, MONTH, TREND
from invest_ll.quant.etf_study import TRANCHES as TRAMOS_BOLSA
from invest_ll.quant.strategies import (
    CashSleeve,
    ConstantMix,
    HoldAsset,
    MarketFilter,
    MomentumPortfolio,
    RiskParity,
    RotationTop1,
    TrendAsset,
)
from invest_ll.quant.study import FLAGSHIP, FLAGSHIP_UNIVERSE, NO_TRADE_BAND, REBALANCE_EVERY
from invest_ll.quant.study import TRANCHES as TRAMOS_CRIPTO

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.quant.strategies import WeightStrategy
    from invest_ll.quant.universe import UniverseRule

Mercado = Literal["bolsa", "cripto"]
Ejecucion = Literal["binance", "broker"]

RIESGO_TEXTO: Final = {1: "Tranquila", 2: "Suave", 3: "Moderada", 4: "Movida", 5: "Muy movida"}

INICIO_BOLSA: Final = date(2008, 1, 1)
INICIO_CRIPTO: Final = date(2018, 1, 1)
CALENTAMIENTO_CRIPTO: Final = 200
"""Días previos al inicio que el estudio deja para que las tendencias tengan historia."""

AVISOS_BOLSA: Final = (
    "Las cifras usan fondos de EE.UU.; desde España se compran sus versiones europeas (UCITS), "
    "que se comportan casi igual.",
    "Sin contar el cambio euro-dólar.",
)
AVISOS_CRIPTO: Final = ("En dólares digitales (USDT).",)


@dataclass(frozen=True, slots=True)
class Motor:
    """Cómo se ejecuta con `invest_ll.quant.engine.run`, tal cual lo hizo el estudio.

    `fabrica` da una instancia NUEVA en cada ejecución: `HoldAsset` guarda si ya compró, y una
    instancia compartida diría "no hagas nada" a partir de la segunda vez.
    """

    fabrica: Callable[[], WeightStrategy]
    rebalanceo: int
    tramos: int
    costes: Costs
    inicio: date
    banda: float = 0.0
    universo: UniverseRule | None = None
    liquidez: str | None = None
    """Símbolo donde espera el dinero que está fuera (SHY): no cuenta como tiempo invertido."""
    simbolos: tuple[str, ...] = ()
    """Lo que puede llegar a comprar; vacío si elige de un universo que cambia cada día."""


@dataclass(frozen=True, slots=True)
class Ficha:
    clave: str
    nombre: str
    frase: str
    para_quien: str
    mercado: Mercado
    riesgo: int
    como_funciona: tuple[str, str, str]
    avisos: tuple[str, ...]
    activos: tuple[str, ...]
    motor: Motor
    laboratorio: bool = False
    retirada: bool = False
    prueba_real: str | None = None
    """Clave de `quant.paper.variants()` si tiene prueba hacia delante registrada."""
    motivo_dentro: str = "Tu estrategia la quiere en cartera"
    """Cripto: el porqué de una orden cuando la estrategia quiere estar en esa moneda."""
    motivo_fuera: str = "Tu estrategia ya no la quiere en cartera"
    """El porqué cuando la estrategia sale del todo de una moneda (cripto) o de un fondo (bolsa:
    "Vende todo tu ETF de…")."""

    @property
    def ejecucion(self) -> Ejecucion:
        return "binance" if self.mercado == "cripto" else "broker"

    @property
    def riesgo_texto(self) -> str:
        return RIESGO_TEXTO[self.riesgo]

    def posee(self, simbolo: str) -> bool:
        """Si un activo de la cartera es de esta parte del plan: cripto, o uno de sus fondos."""
        if self.mercado == "cripto":
            return es_cripto(simbolo)
        fondos = {s.upper() for s in self.motor.simbolos}
        return not es_cripto(simbolo) and (not fondos or simbolo.strip().upper() in fondos)

    @property
    def principal(self) -> bool:
        """Se enseña en el camino principal (y se puede poner en un plan)."""
        return not self.laboratorio and not self.retirada


def _bolsa(
    fabrica: Callable[[], WeightStrategy],
    *,
    simbolos: tuple[str, ...],
    mantener: bool = False,
    liquidez: str | None = None,
) -> Motor:
    """Como `run_etf_study`: mensual, en tres tramos (comprar y mantener, en uno)."""
    return Motor(
        fabrica=fabrica,
        rebalanceo=MONTH,
        tramos=1 if mantener else TRAMOS_BOLSA,
        costes=ETF_COSTS,
        inicio=INICIO_BOLSA,
        liquidez=liquidez,
        simbolos=simbolos,
    )


def _cripto(
    fabrica: Callable[[], WeightStrategy],
    *,
    simbolos: tuple[str, ...] = (),
    mantener: bool = False,
    banda: float = 0.0,
    universo: UniverseRule | None = None,
) -> Motor:
    """Como `run_study`: semanal, en siete tramos (comprar y mantener, en uno)."""
    return Motor(
        fabrica=fabrica,
        rebalanceo=REBALANCE_EVERY,
        tramos=1 if mantener else TRAMOS_CRIPTO,
        costes=BINANCE_SPOT,
        inicio=INICIO_CRIPTO,
        banda=banda,
        universo=universo,
        simbolos=simbolos,
    )


def _ocho_fondos() -> tuple[str, ...]:
    return tuple(nombre_llano(s) for s in ASSETS)


FICHAS: Final[tuple[Ficha, ...]] = (
    Ficha(
        clave="bolsa-equilibrada",
        nombre="Equilibrada",
        frase="60 % en bolsa de EE.UU. y 40 % en bonos del Tesoro, volviendo a ese reparto cada mes.",
        para_quien=(
            "Para quien quiere que su dinero crezca a largo plazo y prefiere caídas menos "
            "profundas que las de la bolsa sola."
        ),
        mercado="bolsa",
        riesgo=3,
        como_funciona=(
            "Tu dinero va a dos fondos: 60 % a la bolsa de EE.UU. y 40 % a bonos del Tesoro de "
            "EE.UU. a 7-10 años.",
            "Cada mes, al aportar, compras de los dos según ese reparto. Si uno se aleja mucho de "
            "él (pasa muy pocas veces), te diremos que vendas lo que sobra.",
            "Cuando la bolsa cae, los bonos suelen aguantar mejor y amortiguan la caída.",
        ),
        avisos=AVISOS_BOLSA,
        activos=("Bolsa de EE.UU.", "Bonos del Tesoro de EE.UU. a 7-10 años"),
        motor=_bolsa(
            lambda: ConstantMix((("SPY", 0.6), ("IEF", 0.4)), "60/40"), simbolos=("SPY", "IEF")
        ),
    ),
    Ficha(
        clave="bolsa-prudente",
        nombre="Prudente con freno",
        frase=(
            "Reparte entre ocho tipos de fondos según lo que se mueve cada uno, y deja fuera los "
            "que llevan meses bajando."
        ),
        para_quien=(
            "Para quien lo pasa mal viendo caer su dinero y acepta crecer menos a cambio de caer "
            "mucho menos."
        ),
        mercado="bolsa",
        riesgo=2,
        como_funciona=(
            "Reparte entre bolsa, bonos, oro, materias primas e inmobiliario: más dinero a lo que "
            "se mueve menos.",
            "Cada mes mira la tendencia de cada uno: lo que lleva meses bajando sale, y su parte "
            "espera en bonos del Tesoro a corto plazo. Salir es vender: unas cuantas veces al año "
            "te diremos qué vender en tu bróker y qué comprar con ese dinero.",
            "Cada mes aportas según el reparto de ese momento.",
        ),
        avisos=(
            "Cae mucho menos, pero también crece aproximadamente la mitad.",
            "Su freno funciona vendiendo: si solo aportas y no haces las ventas que te pida, no "
            "tienes esa protección y caerá casi como sin freno.",
            *AVISOS_BOLSA,
        ),
        activos=(*_ocho_fondos(), "Bonos del Tesoro de EE.UU. a corto plazo"),
        motor=_bolsa(
            lambda: CashSleeve(RiskParity(ASSETS, vol_lookback=63, trend_lookbacks=TREND), CASH),
            simbolos=(*ASSETS, CASH),
            liquidez=CASH,
        ),
        motivo_fuera=(
            "Lleva meses bajando: tu estrategia sale de él y su parte espera en bonos del Tesoro "
            "a corto plazo"
        ),
    ),
    Ficha(
        clave="bolsa-eeuu",
        nombre="Bolsa de EE.UU.",
        frase="Todo en un fondo de las 500 mayores empresas de EE.UU., sin tocarlo.",
        para_quien=(
            "Para quien no va a necesitar el dinero en muchos años y aguanta ver caídas de la "
            "mitad sin vender."
        ),
        mercado="bolsa",
        riesgo=4,
        como_funciona=(
            "Compras un fondo del S&P 500: las 500 mayores empresas de EE.UU. en un solo producto.",
            "Cada mes aportas al mismo fondo.",
            "No se vende en las caídas: la estrategia es aguantar.",
        ),
        avisos=AVISOS_BOLSA,
        activos=("Bolsa de EE.UU.",),
        motor=_bolsa(lambda: HoldAsset("SPY"), simbolos=("SPY",), mantener=True),
    ),
    Ficha(
        clave="btc-freno",
        nombre="Bitcoin con freno",
        frase="Bitcoin mientras sube; dólares digitales (USDT) cuando lleva un mes bajando.",
        para_quien=(
            "Para quien quiere algo de Bitcoin sin estar dentro en las grandes caídas, y acepta "
            "perderse parte de las subidas."
        ),
        mercado="cripto",
        riesgo=4,
        como_funciona=(
            "Cada semana mira si Bitcoin vale más que hace 30 días.",
            "Si sube, está en Bitcoin; si baja, pasa a dólares digitales (USDT) y espera.",
            "Cambia por tramos, un séptimo cada día de la semana, para no depender de la suerte "
            "del día elegido.",
        ),
        avisos=(
            "Pasa casi la mitad del tiempo fuera, en liquidez: habrá años en que lo haga peor que "
            "tener Bitcoin quieto.",
            *AVISOS_CRIPTO,
        ),
        activos=("Bitcoin", "Dólares digitales (USDT)"),
        motor=_cripto(lambda: TrendAsset("BTCUSDT", 30), simbolos=("BTCUSDT",)),
        prueba_real="btc-trend",
        motivo_dentro="Bitcoin vale más que hace 30 días: tu estrategia dice estar dentro",
        motivo_fuera="Bitcoin vale menos que hace 30 días: tu estrategia dice pasar a USDT",
    ),
    Ficha(
        clave="cripto-cesta-freno",
        nombre="Cesta cripto con freno",
        frase=(
            "Hasta cinco de las criptomonedas más negociadas que están subiendo, y todo a USDT "
            "cuando el mercado cripto baja."
        ),
        para_quien=(
            "Para quien quiere más que Bitcoin y acepta caídas grandes, muchas operaciones y "
            "una historia más bonita que su futuro probable."
        ),
        mercado="cripto",
        riesgo=4,
        como_funciona=(
            "Cada semana elige hasta cinco de las 20 criptomonedas más negociadas que llevan "
            "semanas subiendo.",
            "Pone menos dinero en las que más se mueven, y nunca más del 35 % en una.",
            "Si Bitcoin, que arrastra a todo el mercado, está bajando, lo pasa todo a USDT y "
            "espera.",
        ),
        avisos=(
            "Se diseñó después de ver los primeros resultados: su historia es más bonita de lo "
            "que probablemente será su futuro.",
            "Hace muchas operaciones: los impuestos se comen una parte visible.",
            *AVISOS_CRIPTO,
        ),
        activos=("Hasta cinco de las 20 criptomonedas más negociadas", "Dólares digitales (USDT)"),
        motor=_cripto(
            lambda: MarketFilter(FLAGSHIP), banda=NO_TRADE_BAND, universo=FLAGSHIP_UNIVERSE
        ),
        prueba_real="filtered",
        motivo_dentro="Está entre las elegidas y el mercado cripto sube",
        motivo_fuera="Ya no está entre las elegidas, o el mercado cripto está bajando",
    ),
    Ficha(
        clave="btc-mantener",
        nombre="Bitcoin y olvidarse",
        frase="Comprar Bitcoin y no venderlo.",
        para_quien="Solo para dinero que puedas olvidar durante años.",
        mercado="cripto",
        riesgo=5,
        como_funciona=(
            "Compras Bitcoin con lo que pones al empezar.",
            "Cada mes compras más con tu aportación.",
            "No vendes nunca, ni en las caídas.",
        ),
        avisos=(
            "Ha llegado a perder más del 80 %. Solo con dinero que puedas olvidar.",
            *AVISOS_CRIPTO,
        ),
        activos=("Bitcoin",),
        motor=_cripto(lambda: HoldAsset("BTCUSDT"), simbolos=("BTCUSDT",), mantener=True),
        motivo_dentro="Tu estrategia es tener Bitcoin y no venderlo",
    ),
    # -- Laboratorio --------------------------------------------------------------------------
    Ficha(
        clave="cripto-prerregistrada",
        nombre="Cesta cripto prerregistrada",
        frase="La cesta de impulso que se fijó antes de mirar resultados, sin freno de mercado.",
        para_quien="Para estudiar: es la referencia contra la que se mide la cesta con freno.",
        mercado="cripto",
        riesgo=5,
        como_funciona=(
            "Cada semana elige hasta cinco de las 20 criptomonedas más negociadas que llevan "
            "semanas subiendo.",
            "Pone menos dinero en las que más se mueven, nunca más del 35 % en una, y reduce la "
            "cartera si se mueve demasiado.",
            "No mira el mercado en conjunto: puede seguir dentro mientras todo cae.",
        ),
        avisos=(
            "En el estudio no batió a tener Bitcoin quieto y cayó casi lo mismo.",
            *AVISOS_CRIPTO,
        ),
        activos=("Hasta cinco de las 20 criptomonedas más negociadas", "Dólares digitales (USDT)"),
        motor=_cripto(lambda: FLAGSHIP, universo=FLAGSHIP_UNIVERSE),
        laboratorio=True,
        prueba_real="preregistered",
    ),
    Ficha(
        clave="cripto-rotacion",
        nombre="Rotación cripto (retirada)",
        frase=(
            "Todo en la criptomoneda que más subió en 30 días; liquidez si ninguna sube. Era la "
            "política de antes."
        ),
        para_quien="Para nadie: se conserva para que se vea por qué se retiró.",
        mercado="cripto",
        riesgo=5,
        como_funciona=(
            "Cada semana mira cuál de las 20 criptomonedas más negociadas subió más en 30 días.",
            "Pone todo el dinero en esa.",
            "Si ninguna sube, se queda en USDT.",
        ),
        avisos=(
            "Retirada: sin el sesgo de supervivencia se fue casi a cero. Con cuatro monedas "
            "elegidas sabiendo que iban a ganar parecía brillante; con las que de verdad se "
            "podían elegir cada día, persiguió cada subida hasta su desplome.",
            *AVISOS_CRIPTO,
        ),
        activos=("La criptomoneda que más subió", "Dólares digitales (USDT)"),
        motor=_cripto(lambda: RotationTop1(30, 0.0), universo=FLAGSHIP_UNIVERSE),
        laboratorio=True,
        retirada=True,
    ),
    Ficha(
        clave="bolsa-igual",
        nombre="Ocho fondos a partes iguales",
        frase="Un octavo en cada uno de los ocho tipos de fondos, volviendo al reparto cada mes.",
        para_quien="Para estudiar: la referencia de repartir sin pensar.",
        mercado="bolsa",
        riesgo=3,
        como_funciona=(
            "Reparte a partes iguales entre bolsa, bonos, oro, materias primas e inmobiliario.",
            "Cada mes vuelve a ese reparto.",
            "No mira tendencias ni riesgos.",
        ),
        avisos=AVISOS_BOLSA,
        activos=_ocho_fondos(),
        motor=_bolsa(
            lambda: ConstantMix(tuple((s, 1 / len(ASSETS)) for s in ASSETS), "equal weight"),
            simbolos=ASSETS,
        ),
        laboratorio=True,
    ),
    Ficha(
        clave="bolsa-paridad",
        nombre="Paridad de riesgo sin freno",
        frase="Más dinero a lo que se mueve menos, entre ocho tipos de fondos, sin mirar tendencias.",
        para_quien="Para estudiar: la Prudente sin su freno de tendencia.",
        mercado="bolsa",
        riesgo=2,
        como_funciona=(
            "Mide cuánto se mueve cada uno de los ocho fondos.",
            "Da más peso a los que se mueven menos.",
            "Cada mes vuelve a calcular el reparto.",
        ),
        avisos=AVISOS_BOLSA,
        activos=_ocho_fondos(),
        motor=_bolsa(lambda: RiskParity(ASSETS, vol_lookback=63), simbolos=ASSETS),
        laboratorio=True,
    ),
    Ficha(
        clave="bolsa-impulso",
        nombre="Impulso en fondos",
        frase=(
            "Los cuatro fondos que mejor tendencia llevan, con el riesgo limitado; el resto en "
            "bonos a corto plazo."
        ),
        para_quien="Para estudiar: la idea de la cesta cripto, aplicada a fondos.",
        mercado="bolsa",
        riesgo=2,
        como_funciona=(
            "Cada mes elige los cuatro fondos con mejor tendencia de los ocho.",
            "Reduce la cartera si se mueve más de la cuenta.",
            "Lo que no está invertido espera en bonos del Tesoro a corto plazo.",
        ),
        avisos=AVISOS_BOLSA,
        activos=(*_ocho_fondos(), "Bonos del Tesoro de EE.UU. a corto plazo"),
        motor=_bolsa(
            lambda: CashSleeve(
                MomentumPortfolio(
                    lookbacks=TREND, top_k=4, vol_lookback=63, max_weight=0.35, vol_target=0.12
                ),
                CASH,
            ),
            simbolos=(*ASSETS, CASH),
            liquidez=CASH,
        ),
        laboratorio=True,
    ),
)

POR_CLAVE: Final[dict[str, Ficha]] = {f.clave: f for f in FICHAS}


def ficha(clave: str) -> Ficha | None:
    return POR_CLAVE.get(clave)


def del_mercado(mercado: Mercado) -> tuple[Ficha, ...]:
    return tuple(f for f in FICHAS if f.mercado == mercado)


def principales(mercado: Mercado | None = None) -> tuple[Ficha, ...]:
    """Las del camino principal, en el orden del catálogo."""
    return tuple(f for f in FICHAS if f.principal and (mercado is None or f.mercado == mercado))
