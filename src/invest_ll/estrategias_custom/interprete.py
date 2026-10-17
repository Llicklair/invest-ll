"""El intérprete de estrategias a medida: lo que conecta el formato con el motor de bots.

El motor de bots lo llama para los bots con plantilla `medida`, igual que llama a `bots.decisiones`
para las plantillas de v3: misma `Situacion` de entrada y misma `Decision` de salida (órdenes con su
porqué en llano). Puro: no toca la red, el disco ni el reloj.

**Solo velas cerradas.** De las velas de la situación solo cuentan las que habían cerrado en
`ahora` (`decisiones.cerradas`), aunque la fuente le pase alguna más; y de esas, las últimas
`velas_necesarias`: cada indicador mira una ventana fija (`formato.Indicador.ventana`). Cambiar
una vela posterior no cambia una decisión pasada (el test anti-futuro lo fija).

**Una posición por moneda, todo o nada.** Sin la moneda, compra cuando se cumple `entrar`; con
ella, la vende entera cuando salta un stop o se cumple `salir`. Los stops se miran con el cierre
de la última vela cerrada: el precio de compra de referencia es el cierre de la vela con que se
decidió comprar, y el más alto desde entonces se apunta en la memoria del bot y se completa con
las velas que tenga delante (por si el panel estuvo cerrado).

La memoria (`Situacion.memoria`) guarda por moneda: `entrada_<coin>` (precio de referencia),
`desde_<coin>` (cuándo compró), `maximo_<coin>` (el cierre más alto desde entonces) y `stop_<coin>`
(cuándo salió por un stop, para la pausa).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Any, Final

from invest_ll import llano
from invest_ll.bots.decisiones import (
    CERO,
    MINIMO_ORDEN,
    Decision,
    Orden,
    cerradas,
    pct_txt,
    precio_txt,
)
from invest_ll.estrategias_custom import indicadores
from invest_ll.estrategias_custom.formato import (
    DURACION,
    PRECIO,
    Alguna,
    CruzaAbajo,
    CruzaArriba,
    Estrategia,
    Mayor,
    MayorIgual,
    Menor,
    MenorIgual,
    Negacion,
    Referencia,
    Todas,
    describir_binaria,
    describir_condicion,
    nombre_de,
    validar,
)
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    from invest_ll.bots.decisiones import Memoria, Situacion
    from invest_ll.estrategias_custom.formato import Binaria, Nodo
    from invest_ll.vivo.fuente import Vela

CENTIMO: Final = Decimal("0.01")


# -- Lo que pide el contrato -----------------------------------------------------------------------


def decidir(definicion: dict[str, Any], situacion: Situacion) -> Decision:
    """Lo que la estrategia `definicion` (ya validada) quiere hacer en esta situación."""
    return decidir_estrategia(validar(definicion), situacion)


def intervalo(definicion: dict[str, Any]) -> str:
    """El intervalo de velas con que decide la estrategia (p. ej. '1h')."""
    return validar(definicion).intervalo


def monedas(definicion: dict[str, Any]) -> list[str]:
    """Las monedas que opera la estrategia."""
    return list(validar(definicion).monedas)


def velas_necesarias(definicion: dict[str, Any] | Estrategia) -> int:
    """Cuántas velas CERRADAS necesita para decidir (la más larga de sus ventanas, más una para
    saber si hubo cruce). El motor pide a la fuente una más: la última puede estar en curso."""
    e = validar(definicion)
    n = 1
    for ind in e.indicadores.values():
        n = max(n, ind.ventana + ind.atras)
    if e.tamano.reparto == "volatilidad" and len(e.monedas) > 1:
        n = max(n, e.tamano.periodo_volatilidad + 1)
    return n + 1


# -- Evaluar ---------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Moneda:
    """Las velas cerradas de una moneda y los valores ya calculados (por nombre y por `hace`)."""

    coin: str
    velas: Sequence[Vela]
    estrategia: Estrategia
    cache: dict[tuple[str, int], float | None] = field(
        default_factory=dict[tuple[str, int], float | None]
    )

    def valor(self, op: float | str | Referencia, hace: int = 0) -> float | None:
        if isinstance(op, float):
            return op
        nombre = nombre_de(op)
        assert nombre is not None
        clave = (nombre, hace)
        if clave not in self.cache:
            if nombre == PRECIO:
                i = len(self.velas) - 1 - hace
                self.cache[clave] = float(self.velas[i].cierre) if i >= 0 else None
            else:
                ind = self.estrategia.indicadores[nombre]
                self.cache[clave] = indicadores.calcular(ind, self.velas, hace)
        base = self.cache[clave]
        if base is None:
            return None
        return base * op.por if isinstance(op, Referencia) else base


def _cumple_binaria(h: Binaria, m: _Moneda) -> bool:
    a, b = h.par
    va, vb = m.valor(a), m.valor(b)
    if va is None or vb is None:
        return False
    if isinstance(h, Mayor):
        return va > vb
    if isinstance(h, Menor):
        return va < vb
    if isinstance(h, MayorIgual):
        return va >= vb
    if isinstance(h, MenorIgual):
        return va <= vb
    antes_a, antes_b = m.valor(a, 1), m.valor(b, 1)
    if antes_a is None or antes_b is None:
        return False
    if isinstance(h, CruzaArriba):
        return antes_a <= antes_b and va > vb
    assert isinstance(h, CruzaAbajo)
    return antes_a >= antes_b and va < vb


def cumple(nodo: Nodo, m: _Moneda) -> bool:
    if isinstance(nodo, Todas):
        return all(cumple(h, m) for h in nodo.y)
    if isinstance(nodo, Alguna):
        return any(cumple(h, m) for h in nodo.o)
    if isinstance(nodo, Negacion):
        return not cumple(nodo.no, m)
    return _cumple_binaria(nodo, m)


def _cifra(op: float | str | Referencia, valor: float | None, e: Estrategia) -> str:
    """La cifra de un lado de la comparación, como se lee: precio, RSI con un decimal, cambio
    en porcentaje."""
    if valor is None:
        return "?"
    nombre = nombre_de(op)
    ind = e.indicadores.get(nombre) if nombre and nombre != PRECIO else None
    if ind is not None and ind.tipo == "rsi":
        return llano.numero(valor, 1)
    if ind is not None and ind.tipo in ("retorno", "volatilidad"):
        return pct_txt(Decimal(str(valor)))
    if ind is not None and ind.de == "volumen":
        return llano.numero(valor, 0)
    return precio_txt(Decimal(str(valor)).quantize(Decimal("1e-8")))


def porque(nodo: Nodo, m: _Moneda) -> str:
    """El porqué de una condición que se cumple: lo que se cumplió, con sus cifras."""
    e = m.estrategia
    if isinstance(nodo, Todas):
        return " y ".join(porque(h, m) for h in nodo.y)
    if isinstance(nodo, Alguna):
        return " y ".join(porque(h, m) for h in nodo.o if cumple(h, m))
    if isinstance(nodo, Negacion):
        return f"no se cumple que {describir_condicion(nodo.no, e.indicadores, dentro=True)}"
    a, b = nodo.par
    cifras = (_cifra(a, m.valor(a), e), _cifra(b, m.valor(b), e))
    cruce = isinstance(nodo, CruzaArriba | CruzaAbajo)
    return describir_binaria(nodo, e.indicadores, pasado=cruce, valores=cifras)


# -- Decidir ---------------------------------------------------------------------------------------


def _memoria_decimal(memoria: Mapping[str, str], clave: str) -> Decimal | None:
    texto = memoria.get(clave, "")
    try:
        return Decimal(texto) if texto else None
    except ArithmeticError:
        return None


def _fecha(memoria: Mapping[str, str], clave: str) -> datetime | None:
    texto = memoria.get(clave, "")
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _maximo_desde(memoria: Mapping[str, str], coin: str, velas: Sequence[Vela]) -> Decimal | None:
    """El cierre más alto desde la compra: lo apuntado y lo que se ve en las velas posteriores."""
    apuntado = _memoria_decimal(memoria, f"maximo_{coin}")
    desde = _fecha(memoria, f"desde_{coin}")
    vistos = [v.cierre for v in velas if desde is not None and v.fin > desde]
    candidatos = [x for x in (apuntado, *vistos) if x is not None]
    return max(candidatos) if candidatos else None


def _stop(
    e: Estrategia, coin: str, velas: Sequence[Vela], memoria: Mapping[str, str]
) -> str | None:
    """El porqué de un stop que salta con el cierre de la última vela cerrada, o None."""
    r = e.riesgo
    entrada = _memoria_decimal(memoria, f"entrada_{coin}")
    if entrada is None or entrada <= 0:
        return None
    precio = velas[-1].cierre
    nombre = nombre_hyperliquid(coin)
    cambio = precio / entrada - 1
    if r.stop_perdida is not None and cambio <= -Decimal(str(r.stop_perdida)):
        return (
            f"stop de pérdida: {nombre} cerró a {precio_txt(precio)}, un {pct_txt(cambio)} "
            f"desde la compra a {precio_txt(entrada)}"
        )
    if r.stop_seguimiento is not None:
        alto = _maximo_desde(memoria, coin, velas)
        if alto is not None and alto > 0:
            caida = precio / alto - 1
            if caida <= -Decimal(str(r.stop_seguimiento)):
                return (
                    f"stop que sigue al precio: {nombre} cerró a {precio_txt(precio)}, un "
                    f"{pct_txt(caida)} desde su cierre más alto tras la compra "
                    f"({precio_txt(alto)})"
                )
    if r.toma_beneficio is not None and cambio >= Decimal(str(r.toma_beneficio)):
        return (
            f"toma de beneficio: {nombre} cerró a {precio_txt(precio)}, un {pct_txt(cambio)} "
            f"desde la compra a {precio_txt(entrada)}"
        )
    return None


def _en_pausa(e: Estrategia, coin: str, ultima: Vela, memoria: Mapping[str, str]) -> bool:
    salida = _fecha(memoria, f"stop_{coin}")
    pausa = e.riesgo.pausa_tras_stop
    if salida is None or pausa == 0:
        return False
    return ultima.fin < salida + DURACION[e.intervalo] * pausa


def _pesos(e: Estrategia, datos: Mapping[str, Sequence[Vela]]) -> dict[str, Decimal]:
    """La parte de cada moneda (suman 1 con todas las monedas). Por volatilidad: en proporción
    inversa; las que aún esperan historia guardan su parte igual."""
    n = len(e.monedas)
    igual = {c: Decimal(1) / n for c in e.monedas}
    if e.tamano.reparto == "igual" or n == 1:
        return igual
    vols = {c: indicadores.volatilidad(v, e.tamano.periodo_volatilidad) for c, v in datos.items()}
    if not vols or any(v is None or v <= 0 for v in vols.values()):
        return igual
    inversas = {c: 1 / v for c, v in vols.items() if v is not None}
    total = sum(inversas.values())
    parte = Decimal(len(inversas)) / n
    pesos = dict(igual)
    for c, inv in inversas.items():
        pesos[c] = parte * Decimal(str(inv / total))
    return pesos


def decidir_estrategia(e: Estrategia, s: Situacion) -> Decision:
    """`decidir` con la estrategia ya validada (la prueba sobre el pasado la llama así)."""
    necesarias = velas_necesarias(e)
    notas: list[str] = []
    datos: dict[str, Sequence[Vela]] = {}
    vistas: dict[str, Sequence[Vela]] = {}
    for coin in e.monedas:
        todas = cerradas(s.velas.get(coin, ()), s.ahora)
        if len(todas) < necesarias:
            notas.append(
                f"Esperando historia de {coin}: necesita {necesarias} velas de {e.intervalo} "
                "cerradas."
            )
            continue
        # Los indicadores, con su ventana fija; lo más alto desde la compra, con todo lo visto.
        datos[coin] = todas[-necesarias:]
        vistas[coin] = todas

    m = s.memoria
    ventas: list[Orden] = []
    compras: list[tuple[str, str, Vela]] = []
    memoria: Memoria = {}
    for coin, velas in datos.items():
        ultima = velas[-1]
        moneda = _Moneda(coin, velas, e)
        if s.posiciones.get(coin, CERO) > 0:
            motivo = _stop(e, coin, vistas[coin], m)
            por_stop = motivo is not None
            if motivo is None and e.salir is not None and cumple(e.salir, moneda):
                motivo = porque(e.salir, moneda)
            if motivo is not None:
                limpia = (
                    (f"entrada_{coin}", ""),
                    (f"desde_{coin}", ""),
                    (f"maximo_{coin}", ""),
                    (f"stop_{coin}", ultima.fin.isoformat() if por_stop else ""),
                )
                ventas.append(Orden(coin, "venta", motivo, memoria=limpia))
                continue
            alto = _maximo_desde(m, coin, vistas[coin])
            if alto is not None and str(alto) != m.get(f"maximo_{coin}"):
                memoria[f"maximo_{coin}"] = str(alto)
            continue
        if _en_pausa(e, coin, ultima, m):
            continue
        if cumple(e.entrar, moneda):
            compras.append((coin, porque(e.entrar, moneda), ultima))

    ordenes: list[Orden] = list(ventas)
    if compras:
        ordenes.extend(_compras(e, s, datos, ventas, compras, notas))
    return Decision(ordenes=tuple(ordenes), memoria=memoria or None, notas=tuple(notas))


def _compras(
    e: Estrategia,
    s: Situacion,
    datos: Mapping[str, Sequence[Vela]],
    ventas: Sequence[Orden],
    compras: Sequence[tuple[str, str, Vela]],
    notas: list[str],
) -> list[Orden]:
    """Cada compra gasta la parte de su moneda (`tamano`) del valor del bot, con lo que haya."""
    cierres = {c: v[-1].cierre for c, v in datos.items()}
    valor = s.efectivo
    for coin, cantidad in s.posiciones.items():
        precio = cierres.get(coin, s.precios.get(coin))
        if precio is not None:
            valor += cantidad * precio
    # Las ventas se ejecutan antes que las compras: lo que cobren paga las de esta misma decisión.
    disponible = s.efectivo + sum(
        (s.posiciones.get(o.coin, CERO) * cierres[o.coin] for o in ventas), CERO
    )
    pesos = _pesos(e, datos)
    tope = valor * Decimal(str(e.tamano.maximo_por_moneda))
    fraccion = Decimal(str(e.tamano.fraccion))
    ordenes: list[Orden] = []
    for coin, motivo, vela in compras:
        parte = min(valor * fraccion * pesos[coin], tope, disponible)
        importe = parte.quantize(CENTIMO, rounding=ROUND_DOWN)
        if importe < MINIMO_ORDEN:
            notas.append(
                f"No compra {coin}: le tocarían {llano.numero(importe)} USDC y el mínimo por "
                f"orden es {llano.numero(MINIMO_ORDEN, 0)} USDC."
            )
            continue
        disponible -= importe
        apunta = (
            (f"entrada_{coin}", str(vela.cierre)),
            (f"desde_{coin}", vela.fin.isoformat()),
            (f"maximo_{coin}", str(vela.cierre)),
            (f"stop_{coin}", ""),
        )
        ordenes.append(Orden(coin, "compra", motivo, importe=importe, memoria=apunta))
    return ordenes
