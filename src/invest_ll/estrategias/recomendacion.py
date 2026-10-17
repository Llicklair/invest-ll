"""De tus respuestas a un reparto, con reglas fijas y a la vista (docs/panel-v2.md, sección 6).

No predice nada ni optimiza nada: son cinco reglas que cualquiera puede leer y comprobar, y el
"por qué" cita tus respuestas para que se vea qué regla saltó.

1. Horizonte de menos de 2 años: no es dinero para esto (`no_invertir`) y, si aun así quieres
   seguir, Prudente con freno al 100 %, sin cripto.
2. Bolsa según qué harías si lo invertido cae a la mitad: vender → Prudente; esperar → Equilibrada;
   poner más → Bolsa de EE.UU. si el horizonte pasa de 5 años (si no, Equilibrada).
3. Cripto, nunca más del 15 % (5 % como mucho si venderías en una caída): no → 0; un poco → 5 % en
   Bitcoin con freno; sí → 10 % (15 % si pondrías más y el horizonte pasa de 5 años).
4. El reparto se aplica al inicial y a la aportación mensual. Alternativas: las otras estrategias
   del mismo mercado.
5. Avisos siempre: que son reglas y no predicciones, y por qué la cripto va limitada.

Pura: sin disco ni red. Las cifras de caída que citan los textos llegan calculadas del catálogo
(`CaidasDelCatalogo`); si no hay datos, se usan las del estudio del 2026-10-16.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

from invest_ll.estrategias.catalogo import Ficha, ficha, principales

Horizonte = Literal["menos-2", "2-5", "5-10", "mas-10"]
AnteCaida = Literal["vender", "esperar", "comprar"]
QuiereCripto = Literal["no", "poco", "si"]

BOLSA_SEGUN_CAIDA: Final[dict[AnteCaida, str]] = {
    "vender": "bolsa-prudente",
    "esperar": "bolsa-equilibrada",
    "comprar": "bolsa-eeuu",
}
CRIPTO: Final = "btc-freno"
TOPE_CRIPTO: Final = 15
TOPE_CRIPTO_SI_VENDERIA: Final = 5
CENTIMO: Final = Decimal("0.01")

HORIZONTE_TEXTO: Final[dict[Horizonte, str]] = {
    "menos-2": "en menos de 2 años",
    "2-5": "en entre 2 y 5 años",
    "5-10": "en entre 5 y 10 años",
    "mas-10": "en más de 10 años",
}
CAIDA_TEXTO: Final[dict[AnteCaida, str]] = {
    "vender": "venderías para no perder más",
    "esperar": "esperarías a que se recupere",
    "comprar": "aprovecharías para poner más",
}

AVISO_REGLAS: Final = (
    "Esto sale de reglas fijas aplicadas a tus respuestas, no de predecir el mercado."
)


@dataclass(frozen=True, slots=True)
class CaidasDelCatalogo:
    """Peores caídas (fracciones negativas) que citan los textos. Por defecto, las del estudio."""

    menor: float = -0.10
    mayor: float = -0.81
    cripto: float = -0.65


@dataclass(frozen=True, slots=True)
class Respuestas:
    inicial: Decimal
    mensual: Decimal
    horizonte: Horizonte
    ante_caida: AnteCaida
    cripto: QuiereCripto


@dataclass(frozen=True, slots=True)
class ParteRecomendada:
    estrategia: str
    nombre: str
    porcentaje: int
    inicial: Decimal
    mensual: Decimal


@dataclass(frozen=True, slots=True)
class Reparto:
    no_invertir: bool
    partes: tuple[ParteRecomendada, ...]
    por_que: tuple[str, ...]
    avisos: tuple[str, ...]
    alternativas: tuple[str, ...]


def _pct(fraccion: float) -> str:
    return f"{round(abs(fraccion) * 100)} %"


def _mas_de_cinco(horizonte: Horizonte) -> bool:
    return horizonte in ("5-10", "mas-10")


def porcentaje_cripto(r: Respuestas) -> int:
    """La regla 3, con sus topes."""
    if r.horizonte == "menos-2" or r.cripto == "no":
        return 0
    if r.cripto == "poco":
        pedido = 5
    elif r.ante_caida == "comprar" and _mas_de_cinco(r.horizonte):
        pedido = 15
    else:
        pedido = 10
    tope = TOPE_CRIPTO_SI_VENDERIA if r.ante_caida == "vender" else TOPE_CRIPTO
    return min(pedido, tope)


def estrategia_de_bolsa(r: Respuestas) -> str:
    """Las reglas 1 y 2."""
    if r.horizonte == "menos-2":
        return "bolsa-prudente"
    elegida = BOLSA_SEGUN_CAIDA[r.ante_caida]
    if elegida == "bolsa-eeuu" and not _mas_de_cinco(r.horizonte):
        return "bolsa-equilibrada"
    return elegida


def _repartir(total: Decimal, porcentaje_cripto: int) -> tuple[Decimal, Decimal]:
    """(bolsa, cripto) al céntimo, sumando exactamente `total`."""
    cripto = (total * porcentaje_cripto / 100).quantize(CENTIMO, rounding=ROUND_HALF_UP)
    return total - cripto, cripto


def _ficha(clave: str) -> Ficha:
    encontrada = ficha(clave)
    if encontrada is None:  # pragma: no cover - las claves de arriba son del catalogo
        raise KeyError(clave)
    return encontrada


def recomendar(r: Respuestas, caidas: CaidasDelCatalogo | None = None) -> Reparto:
    """Aplica las reglas a tus respuestas."""
    c = caidas or CaidasDelCatalogo()
    bolsa = _ficha(estrategia_de_bolsa(r))
    pct_cripto = porcentaje_cripto(r)
    bolsa_inicial, cripto_inicial = _repartir(r.inicial, pct_cripto)
    bolsa_mensual, cripto_mensual = _repartir(r.mensual, pct_cripto)

    partes = [
        ParteRecomendada(
            estrategia=bolsa.clave,
            nombre=bolsa.nombre,
            porcentaje=100 - pct_cripto,
            inicial=bolsa_inicial,
            mensual=bolsa_mensual,
        )
    ]
    if pct_cripto:
        cripto = _ficha(CRIPTO)
        partes.append(
            ParteRecomendada(
                estrategia=cripto.clave,
                nombre=cripto.nombre,
                porcentaje=pct_cripto,
                inicial=cripto_inicial,
                mensual=cripto_mensual,
            )
        )

    avisos = [AVISO_REGLAS]
    if pct_cripto:
        avisos.append(
            f"Limitamos la cripto porque, incluso con freno, ha llegado a caer un {_pct(c.cripto)}."
        )
    elegidas = {p.estrategia for p in partes}
    mercados = {_ficha(p.estrategia).mercado for p in partes}
    alternativas = tuple(
        f.clave for f in principales() if f.mercado in mercados and f.clave not in elegidas
    )
    return Reparto(
        no_invertir=r.horizonte == "menos-2",
        partes=tuple(partes),
        por_que=tuple(_por_que(r, bolsa, pct_cripto, c)),
        avisos=tuple(avisos),
        alternativas=alternativas,
    )


def _por_que(r: Respuestas, bolsa: Ficha, pct_cripto: int, c: CaidasDelCatalogo) -> list[str]:
    cuando = HORIZONTE_TEXTO[r.horizonte]
    reaccion = CAIDA_TEXTO[r.ante_caida]
    frases: list[str] = []
    if r.horizonte == "menos-2":
        frases.append(
            f"Porque necesitarás este dinero {cuando}: para eso ninguna de estas estrategias es "
            f"buena idea, porque en su peor momento cayeron entre un {_pct(c.menor)} y un "
            f"{_pct(c.mayor)}. Una cuenta remunerada o un depósito encajan mejor."
        )
        frases.append(
            f"Si aun así quieres seguir, {bolsa.nombre} es la que menos ha llegado a caer, y "
            "sin cripto."
        )
        return frases

    if bolsa.clave == "bolsa-prudente":
        frases.append(
            f"Porque dijiste que {reaccion}: {bolsa.nombre} es la que menos cae, para que una "
            "caída no te empuje a vender en el peor momento."
        )
    elif bolsa.clave == "bolsa-eeuu":
        frases.append(
            f"Porque lo necesitarás {cuando} y dijiste que {reaccion}: con tiempo y sin miedo a "
            f"las caídas, {bolsa.nombre} es la que más ha crecido a largo plazo."
        )
    elif r.ante_caida == "comprar":
        frases.append(
            f"Porque dijiste que {reaccion}, pero lo necesitarás {cuando}: para menos de 5 años, "
            f"{bolsa.nombre} cae bastante menos que la bolsa sola."
        )
    else:
        frases.append(
            f"Porque lo necesitarás {cuando} y dijiste que {reaccion}: {bolsa.nombre} crece a "
            "largo plazo con caídas menos profundas que la bolsa sola."
        )

    if r.cripto == "no":
        frases.append("Sin cripto, porque dijiste que no quieres.")
    elif pct_cripto:
        detalle = f"un {pct_cripto} % en Bitcoin con freno"
        if r.ante_caida == "vender" and r.cripto == "si":
            frases.append(
                f"Querías cripto, pero dijiste que {reaccion}: por eso solo {detalle}, el mínimo."
            )
        elif r.cripto == "poco":
            frases.append(f"Pediste un poco de cripto: {detalle}.")
        else:
            frases.append(f"Pediste cripto: {detalle}, que sale de mercado cuando Bitcoin baja.")
    return frases
