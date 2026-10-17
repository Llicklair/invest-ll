"""La prueba de una estrategia a medida sobre el pasado (docs/panel-v4-real.md §2, paso 2).

Hace correr la estrategia vela a vela sobre velas del exchange, con el MISMO intérprete que los
bots en vivo (`interprete.decidir_estrategia`, con la misma `Situacion`) y la misma cuenta
(`bots.cuenta.Cuenta`: nunca gasta más de lo que tiene, cantidades con 8 decimales, mínimo de
10 USDC por orden), y la compara con "mantener" (el capital repartido a partes iguales entre sus
monedas al empezar, pagando la comisión una vez), como la tarjeta de un bot.

**Lo que no hay en el pasado es el libro de órdenes.** En vivo, una orden se ejecuta contra el
libro del momento; aquí se da por hecha al CIERRE de la vela que la decide, con un deslizamiento en
contra (0,05 % por defecto) y la comisión de tomador del mercado (0,1 % si el exchange no la dice).
El resultado lo dice en sus avisos.

Las velas llegan del exchange por `exchanges.registro.conector_publico` (inyectable: las pruebas
pasan un conector falso). Antes de `desde` se piden las velas que la estrategia necesita para
calcular sus indicadores; las decisiones empiezan en `desde`.

**Cuántas versiones se han probado.** Elegir la mejor de muchas pruebas sobre el pasado se parece a
hacer trampa: lo que sale bien puede ser suerte de ese periodo. La biblioteca cuenta las versiones
distintas (por huella) probadas de cada estrategia y, a partir de `VERSIONES_AVISO`, el resultado
lleva `aviso_sobreajuste`.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from invest_ll import llano
from invest_ll.bots.cuenta import (
    Cuenta,
    Hecha,
    OrdenPequenaError,
    cantidades_mantener,
    usdc,
)
from invest_ll.bots.decisiones import Situacion, precio_txt
from invest_ll.errors import InvestLLError
from invest_ll.estrategias_custom.formato import DURACION, Estrategia, huella
from invest_ll.estrategias_custom.interprete import decidir_estrategia, velas_necesarias
from invest_ll.nombres import nombre_hyperliquid
from invest_ll.vivo.ejecucion import Comisiones
from invest_ll.vivo.fuente import Libro, Nivel

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping, Sequence

    from invest_ll.bots.decisiones import Orden
    from invest_ll.exchanges.conector import Conector, Mercado
    from invest_ll.vivo.fuente import Vela

COMISION_POR_DEFECTO: Final = Decimal("0.001")
"""0,1 %: la de tomador más común en contado, para cuando el exchange no dice la suya."""
DESLIZAMIENTO: Final = Decimal("0.0005")
"""0,05 % en contra en cada orden: lo que se mueve el precio entre el cierre y la ejecución."""
COTIZADAS: Final = ("USDC", "USDT", "USD", "FDUSD")
"""Contra qué moneda se prueba cada una, por orden de preferencia."""
MAX_VELAS: Final = 20_000
"""Por moneda (con las de calentamiento): un año de velas de 30 minutos cabe; más, no."""
POR_PAGINA: Final = 1000
PUNTOS_CURVA: Final = 200
MAX_LISTA: Final = 200
VERSIONES_AVISO: Final = 3
PERIODO_POR_DEFECTO: Final = timedelta(days=365)
_CANTIDAD_LIBRO: Final = Decimal("1e30")


class PruebaError(InvestLLError):
    """No se puede probar (sin velas, sin el par en ese exchange…). El texto, en llano."""


@dataclass(frozen=True, slots=True)
class OperacionPrueba:
    at: datetime
    coin: str
    lado: str
    cantidad: Decimal
    precio: Decimal
    importe: Decimal
    comision: Decimal
    motivo: str


@dataclass(frozen=True, slots=True)
class PuntoPrueba:
    at: datetime
    valor: Decimal


@dataclass(frozen=True, slots=True)
class Resultado:
    """Una prueba sobre el pasado. Los mismos campos que `api.schemas_v4.ResultadoPrueba`, más
    la versión probada (`version`, `huella`) y cuándo se hizo (`at`)."""

    exchange: str
    monedas: tuple[str, ...]
    intervalo: str
    desde: datetime
    hasta: datetime
    capital: Decimal
    valor_final: Decimal
    ganancia_pct: float
    mantener_pct: float
    peor_caida: float
    mantener_peor_caida: float
    operaciones: int
    comisiones: Decimal
    tiempo_dentro: float
    curva: tuple[PuntoPrueba, ...]
    curva_mantener: tuple[PuntoPrueba, ...]
    lista_operaciones: tuple[OperacionPrueba, ...]
    avisos: tuple[str, ...]
    huella: str
    comision: Decimal
    deslizamiento: Decimal
    at: datetime
    version: int = 0
    versiones_probadas: int = 1
    aviso_sobreajuste: str | None = None
    abiertas: tuple[str, ...] = ()
    """Las monedas que tenía compradas al acabar: esa parte del resultado aún no se ha cerrado."""


def aviso_sobreajuste(versiones: int) -> str | None:
    """A partir de `VERSIONES_AVISO` versiones probadas, el aviso en llano."""
    if versiones < VERSIONES_AVISO:
        return None
    return (
        f"Llevas {versiones} versiones de esta estrategia probadas sobre el pasado. Quedarse con "
        "la que mejor sale de muchas pruebas se parece a hacer trampa: el buen resultado puede ser "
        "suerte de este periodo (sobreajuste) y no repetirse. Pruébala en ficticio antes de fiarte."
    )


# -- Las velas -------------------------------------------------------------------------------------


def elegir_mercado(conector: Conector, coin: str) -> Mercado:
    """El par de contado de `coin` contra USDC, USDT… (el primero que tenga el exchange)."""
    candidatos = [m for m in conector.mercados() if m.base.upper() == coin.upper()]
    for cotizada in COTIZADAS:
        for mercado in candidatos:
            if mercado.cotizada.upper() == cotizada:
                return mercado
    raise PruebaError(
        f"{conector.exchange} no tiene par de contado de {coin} frente a "
        f"{', '.join(COTIZADAS[:-1])} o {COTIZADAS[-1]}: elige otra moneda u otro exchange."
    )


def descargar(
    conector: Conector, par: str, intervalo: str, desde: datetime, hasta: datetime
) -> list[Vela]:
    """Las velas CERRADAS de `par` entre `desde` y `hasta`, pidiéndolas por páginas."""
    paso = DURACION[intervalo]
    todas: list[Vela] = []
    cursor = desde
    for _ in range(MAX_VELAS // POR_PAGINA + 2):
        lote = conector.velas(par, intervalo, desde=cursor, limite=POR_PAGINA)
        antes = len(todas)
        for v in sorted(lote, key=lambda v: v.inicio):
            repetida = bool(todas) and v.inicio <= todas[-1].inicio
            if v.cerrada and v.fin <= hasta and v.inicio >= cursor and not repetida:
                todas.append(v)
        if len(todas) == antes:
            break
        if len(todas) >= MAX_VELAS or todas[-1].fin + paso > hasta:
            break
        cursor = todas[-1].inicio + paso
    return todas[:MAX_VELAS]


# -- La simulación ---------------------------------------------------------------------------------


def _libro(coin: str, precio: Decimal, deslizamiento: Decimal, at: datetime) -> Libro:
    """Un libro de mentira con el cierre ± deslizamiento y cantidad de sobra: en el pasado no hay
    libro, y esto es lo que se supone (y se dice)."""
    return Libro(
        coin=coin,
        compras=(Nivel(precio * (1 - deslizamiento), _CANTIDAD_LIBRO),),
        ventas=(Nivel(precio * (1 + deslizamiento), _CANTIDAD_LIBRO),),
        at=at,
    )


def _muestra(puntos: Sequence[PuntoPrueba], n: int = PUNTOS_CURVA) -> tuple[PuntoPrueba, ...]:
    if len(puntos) <= n:
        return tuple(puntos)
    ultimo = len(puntos) - 1
    indices = sorted({round(i * ultimo / (n - 1)) for i in range(n)})
    return tuple(puntos[i] for i in indices)


def _peor_caida(valores: Sequence[Decimal]) -> float:
    alto = None
    peor = 0.0
    for v in valores:
        if alto is None or v > alto:
            alto = v
        if alto > 0:
            peor = min(peor, float(v / alto - 1))
    return peor


@dataclass(slots=True)
class _Estado:
    cuenta: Cuenta
    memoria: dict[str, str] = field(default_factory=dict[str, str])
    operaciones: list[OperacionPrueba] = field(default_factory=list[OperacionPrueba])
    comisiones: Decimal = Decimal(0)
    pequenas: int = 0


def _ejecutar(
    st: _Estado, orden: Orden, precio: Decimal, deslizamiento: Decimal, at: datetime
) -> Hecha | None:
    libro = _libro(orden.coin, precio, deslizamiento, at)
    try:
        if orden.lado == "venta":
            return st.cuenta.vender(libro, orden.cantidad)
        gastar = (
            orden.importe
            if orden.importe is not None
            else st.cuenta.efectivo * (orden.fraccion if orden.fraccion is not None else 1)
        )
        return st.cuenta.comprar(libro, gastar)
    except OrdenPequenaError:
        st.pequenas += 1
        return None


def simular(
    estrategia: Estrategia,
    velas: Mapping[str, Sequence[Vela]],
    *,
    exchange: str,
    capital: Decimal,
    desde: datetime,
    hasta: datetime,
    comision: Decimal = COMISION_POR_DEFECTO,
    deslizamiento: Decimal = DESLIZAMIENTO,
    ahora: datetime | None = None,
    avisos_previos: Sequence[str] = (),
) -> Resultado:
    """La estrategia vela a vela sobre `velas` (por moneda, de la más antigua a la más reciente;
    pueden empezar antes de `desde` para calentar los indicadores). Decide al cierre de cada vela
    con `fin` en (desde, hasta]."""
    e = estrategia
    comisiones = Comisiones(tomador=comision, creador=comision)
    necesarias = velas_necesarias(e)
    series = {c: [v for v in velas.get(c, ()) if v.cerrada] for c in e.monedas}
    fines = {c: [v.fin for v in s] for c, s in series.items()}
    pasos = sorted({v.fin for s in series.values() for v in s if desde < v.fin <= hasta})
    if not pasos:
        raise PruebaError(
            f"No hay velas de {', '.join(e.monedas)} en {exchange} entre el "
            f"{llano.fecha_corta(desde.date())} y el {llano.fecha_corta(hasta.date())}."
        )

    st = _Estado(Cuenta(efectivo=capital, comisiones=comisiones))
    curva: list[PuntoPrueba] = []
    curva_mantener: list[PuntoPrueba] = []
    dentro = 0
    ultimo: dict[str, Decimal] = {}
    parte = capital / len(e.monedas)
    mantener: dict[str, Decimal] = {}
    for t in pasos:
        ventanas: dict[str, Sequence[Vela]] = {}
        for coin, serie in series.items():
            i = bisect_right(fines[coin], t)
            if i == 0:
                continue
            ventanas[coin] = serie[max(0, i - necesarias) : i]
            ultimo[coin] = serie[i - 1].cierre
            if coin not in mantener:
                arranque = {coin: serie[i - 1].cierre * (1 + deslizamiento)}
                cantidades = cantidades_mantener(parte, (coin,), arranque, comisiones)
                assert cantidades is not None
                mantener[coin] = cantidades[coin]
        situacion = Situacion(
            ahora=t,
            capital=capital,
            monedas=e.monedas,
            parametros={},
            efectivo=st.cuenta.efectivo,
            posiciones=st.cuenta.cantidades(),
            precios=dict(ultimo),
            velas=ventanas,
            memoria=dict(st.memoria),
        )
        decision = decidir_estrategia(e, situacion)
        for orden in sorted(decision.ordenes, key=lambda o: o.lado != "venta"):
            precio = ultimo.get(orden.coin)
            if precio is None:  # pragma: no cover - el intérprete solo opera con velas
                continue
            hecha = _ejecutar(st, orden, precio, deslizamiento, t)
            if hecha is None:
                continue
            st.memoria.update(orden.memoria)
            st.comisiones += hecha.comision
            verbo = "Compré" if hecha.lado == "compra" else "Vendí"
            # Diez cifras significativas, como las guarda el motor de bots.
            pagado = hecha.precio.quantize(Decimal(1).scaleb(hecha.precio.adjusted() - 9))
            st.operaciones.append(
                OperacionPrueba(
                    at=t,
                    coin=hecha.coin,
                    lado=hecha.lado,
                    cantidad=hecha.cantidad,
                    precio=pagado,
                    importe=hecha.importe,
                    comision=hecha.comision,
                    motivo=(
                        f"{verbo} {llano.cantidad(hecha.cantidad)} {hecha.coin} a "
                        f"{precio_txt(pagado)}: {orden.porque}"
                    ),
                )
            )
        if decision.memoria:
            st.memoria.update(decision.memoria)
        valor = st.cuenta.valor(ultimo)
        assert valor is not None
        curva.append(PuntoPrueba(t, usdc(valor)))
        # Lo de una moneda que aún no cotizaba espera en efectivo hasta su primera vela.
        valor_mantener = sum((q * ultimo[c] for c, q in mantener.items()), Decimal(0)) + parte * (
            len(e.monedas) - len(mantener)
        )
        curva_mantener.append(PuntoPrueba(t, usdc(valor_mantener)))
        if st.cuenta.posiciones:
            dentro += 1

    final = curva[-1].valor
    final_mantener = curva_mantener[-1].valor
    operaciones = len(st.operaciones)
    resultado = Resultado(
        exchange=exchange,
        monedas=tuple(e.monedas),
        intervalo=e.intervalo,
        desde=pasos[0],
        hasta=pasos[-1],
        capital=capital,
        valor_final=final,
        ganancia_pct=float(final / capital - 1),
        mantener_pct=float(final_mantener / capital - 1),
        peor_caida=_peor_caida([p.valor for p in curva]),
        mantener_peor_caida=_peor_caida([p.valor for p in curva_mantener]),
        operaciones=operaciones,
        comisiones=usdc(st.comisiones),
        tiempo_dentro=dentro / len(pasos),
        curva=_muestra(curva),
        curva_mantener=_muestra(curva_mantener),
        lista_operaciones=tuple(st.operaciones[:MAX_LISTA]),
        avisos=(),
        huella=huella(e),
        comision=comision,
        deslizamiento=deslizamiento,
        at=ahora or datetime.now(UTC),
        abiertas=tuple(sorted(st.cuenta.posiciones)),
    )
    return replace(resultado, avisos=tuple(_avisos(resultado, st, avisos_previos, len(pasos))))


def _avisos(r: Resultado, st: _Estado, previos: Sequence[str], velas: int) -> list[str]:
    avisos = [
        "El pasado no es una promesa: esta prueba sirve para descartar ideas malas, no para "
        "confirmar buenas.",
        f"En el pasado no hay libro de órdenes: cada orden se da por hecha al cierre de la vela "
        f"que la decide, con un {_pct(r.deslizamiento)} de deslizamiento en contra y una comisión "
        f"del {_pct(r.comision)}. En vivo puede salir peor.",
        *previos,
    ]
    if r.operaciones == 0:
        avisos.append(
            "No ha hecho ninguna operación en este periodo: su regla de entrada no se cumplió "
            "nunca. No dice nada de si funciona."
        )
    elif r.operaciones < 10:
        avisos.append(
            f"Solo {r.operaciones} operaciones: con tan pocas, el resultado depende mucho de la "
            "suerte."
        )
    if r.ganancia_pct < r.mantener_pct:
        avisos.append(
            f"Lo ha hecho peor que mantener: {_signo(r.ganancia_pct)} frente a "
            f"{_signo(r.mantener_pct)}."
        )
    if r.peor_caida < -0.3:
        avisos.append(
            f"Llegó a caer un {_pct(Decimal(str(-r.peor_caida)))} desde su máximo: piensa si "
            "aguantarías eso con dinero de verdad."
        )
    if velas < 100:
        avisos.append(f"Solo {velas} velas de prueba: es un periodo corto para sacar conclusiones.")
    if st.pequenas:
        avisos.append(
            f"{st.pequenas} órdenes no se hicieron por no llegar al mínimo de 10 USDC por orden."
        )
    if r.abiertas:
        cuales = ", ".join(nombre_hyperliquid(c) for c in r.abiertas)
        avisos.append(
            f"Al acabar la prueba aún tenía {cuales}: parte del resultado es una ganancia o una "
            "pérdida sin cerrar, valorada al último cierre."
        )
    return avisos


def _pct(fraccion: Decimal) -> str:
    return f"{llano.numero(fraccion * 100, 2 if fraccion * 100 < 1 else 1)} %"


def _signo(fraccion: float) -> str:
    signo = "+" if fraccion >= 0 else "-"
    return f"{signo}{llano.numero(abs(fraccion) * 100, 1)} %"


# -- Con el exchange -------------------------------------------------------------------------------


def _conector_publico(exchange: str) -> Conector:
    from invest_ll.exchanges import registro

    return registro.conector_publico(exchange)


def probar(
    estrategia: Estrategia,
    exchange: str,
    *,
    capital: Decimal = Decimal(1000),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    ahora: datetime | None = None,
    deslizamiento: Decimal = DESLIZAMIENTO,
    conector_publico: Callable[[str], Conector] | None = None,
) -> Resultado:
    """Pide las velas al exchange y simula. Por defecto, el último año."""
    if capital <= 0:
        raise PruebaError("El capital de la prueba tiene que ser mayor que cero.")
    momento = ahora or datetime.now(UTC)
    hasta = min(hasta or momento, momento)
    desde = desde or hasta - PERIODO_POR_DEFECTO
    for fecha in (desde, hasta):
        if fecha.tzinfo is None:
            raise PruebaError("Las fechas de la prueba tienen que llevar su zona horaria.")
    if desde >= hasta:
        raise PruebaError("«desde» tiene que ser anterior a «hasta».")
    conector = (conector_publico or _conector_publico)(exchange)
    paso = DURACION[estrategia.intervalo]
    calentar = paso * (velas_necesarias(estrategia) + 1)
    avisos: list[str] = []
    velas: dict[str, list[Vela]] = {}
    comision = COMISION_POR_DEFECTO
    sabidas: list[Decimal] = []
    for coin in estrategia.monedas:
        mercado = elegir_mercado(conector, coin)
        if mercado.comision_tomador is not None:
            sabidas.append(mercado.comision_tomador)
        else:
            avisos.append(
                f"{exchange} no dice la comisión de {mercado.par}: se ha supuesto un 0,1 %."
            )
        serie = descargar(conector, mercado.par, estrategia.intervalo, desde - calentar, hasta)
        if not serie:
            raise PruebaError(
                f"{exchange} no da velas de {mercado.par} de {estrategia.intervalo} en ese periodo."
            )
        if serie[0].inicio > desde:
            avisos.append(
                f"{exchange} solo tiene velas de {nombre_hyperliquid(coin)} desde el "
                f"{llano.fecha_corta(serie[0].inicio.date())}: lo anterior no se ha probado."
            )
        velas[coin] = serie
    if sabidas:
        comision = max(sabidas)
    return simular(
        estrategia,
        velas,
        exchange=exchange,
        capital=capital,
        desde=desde,
        hasta=hasta,
        comision=comision,
        deslizamiento=deslizamiento,
        ahora=momento,
        avisos_previos=avisos,
    )


# -- A y desde JSON (la biblioteca guarda las pruebas) -----------------------------------------------


def _d(texto: object) -> Decimal:
    return Decimal(str(texto))


def _f(texto: object) -> datetime:
    return datetime.fromisoformat(str(texto))


def resultado_a_json(r: Resultado) -> dict[str, Any]:
    return {
        "exchange": r.exchange,
        "monedas": list(r.monedas),
        "intervalo": r.intervalo,
        "desde": r.desde.isoformat(),
        "hasta": r.hasta.isoformat(),
        "capital": str(r.capital),
        "valor_final": str(r.valor_final),
        "ganancia_pct": r.ganancia_pct,
        "mantener_pct": r.mantener_pct,
        "peor_caida": r.peor_caida,
        "mantener_peor_caida": r.mantener_peor_caida,
        "operaciones": r.operaciones,
        "comisiones": str(r.comisiones),
        "tiempo_dentro": r.tiempo_dentro,
        "curva": [[p.at.isoformat(), str(p.valor)] for p in r.curva],
        "curva_mantener": [[p.at.isoformat(), str(p.valor)] for p in r.curva_mantener],
        "lista_operaciones": [
            {
                "at": o.at.isoformat(),
                "coin": o.coin,
                "lado": o.lado,
                "cantidad": str(o.cantidad),
                "precio": str(o.precio),
                "importe": str(o.importe),
                "comision": str(o.comision),
                "motivo": o.motivo,
            }
            for o in r.lista_operaciones
        ],
        "avisos": list(r.avisos),
        "huella": r.huella,
        "comision": str(r.comision),
        "deslizamiento": str(r.deslizamiento),
        "at": r.at.isoformat(),
        "version": r.version,
        "versiones_probadas": r.versiones_probadas,
        "aviso_sobreajuste": r.aviso_sobreajuste,
        "abiertas": list(r.abiertas),
    }


def resultado_de_json(d: dict[str, Any]) -> Resultado:
    return Resultado(
        exchange=str(d["exchange"]),
        monedas=tuple(str(c) for c in d["monedas"]),
        intervalo=str(d["intervalo"]),
        desde=_f(d["desde"]),
        hasta=_f(d["hasta"]),
        capital=_d(d["capital"]),
        valor_final=_d(d["valor_final"]),
        ganancia_pct=float(d["ganancia_pct"]),
        mantener_pct=float(d["mantener_pct"]),
        peor_caida=float(d["peor_caida"]),
        mantener_peor_caida=float(d["mantener_peor_caida"]),
        operaciones=int(d["operaciones"]),
        comisiones=_d(d["comisiones"]),
        tiempo_dentro=float(d["tiempo_dentro"]),
        curva=tuple(PuntoPrueba(_f(at), _d(v)) for at, v in d["curva"]),
        curva_mantener=tuple(PuntoPrueba(_f(at), _d(v)) for at, v in d["curva_mantener"]),
        lista_operaciones=tuple(
            OperacionPrueba(
                at=_f(o["at"]),
                coin=str(o["coin"]),
                lado=str(o["lado"]),
                cantidad=_d(o["cantidad"]),
                precio=_d(o["precio"]),
                importe=_d(o["importe"]),
                comision=_d(o["comision"]),
                motivo=str(o["motivo"]),
            )
            for o in d["lista_operaciones"]
        ),
        avisos=tuple(str(a) for a in d["avisos"]),
        huella=str(d["huella"]),
        comision=_d(d["comision"]),
        deslizamiento=_d(d["deslizamiento"]),
        at=_f(d["at"]),
        version=int(d.get("version", 0)),
        versiones_probadas=int(d.get("versiones_probadas", 1)),
        aviso_sobreajuste=d.get("aviso_sobreajuste"),
        abiertas=tuple(str(c) for c in d.get("abiertas", [])),
    )
