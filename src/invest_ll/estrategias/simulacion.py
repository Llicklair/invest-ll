"""Tus números: lo que habrías tenido con un inicial y una aportación mensual desde un año.

**Es una aproximación, y lo dice.** No se vuelve a ejecutar el motor con tu calendario: se toman
los rendimientos diarios de la estrategia (su ejecución desde 10.000, con sus costes) y se aplican a
tu dinero. Las aportaciones entran el primer día con datos de cada mes —también el del mes de
inicio, junto con el inicial— y no pagan comisión propia; con importes pequeños, eso hace la cifra
un poco mejor que la real.

Tres medidas del peor momento, porque responden a preguntas distintas:

- `peor_momento_*`: el día en que tu dinero valía menos **en proporción a lo que habías puesto**
  ("tus 1.000 € llegaron a valer 350 €"). Es la que se entiende sin saber de inversiones.
- `peor_caida`: lo más que cayó la estrategia desde un máximo anterior, sin que tus aportaciones lo
  disimulen (se mide sobre su rendimiento, no sobre tu saldo).
- `meses_por_debajo`: cuántos meses acabaste valiendo menos de lo que habías puesto.

Pura: recibe la curva y devuelve cifras. Ni disco ni red.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

HOLGURA_INICIO: Final = timedelta(days=7)
"""Si los datos empiezan más de una semana después de lo pedido, se avisa."""


class SinDatosDesdeError(ValueError):
    """No hay ningún día con datos a partir de la fecha pedida."""


@dataclass(frozen=True, slots=True)
class Punto:
    fecha: date
    valor: float
    aportado: float


@dataclass(frozen=True, slots=True)
class Simulada:
    desde: date
    hasta: date
    puntos: tuple[Punto, ...]
    aportado: float
    valor_final: float
    ganancia: float
    peor_momento_fecha: date
    peor_momento_valor: float
    peor_momento_aportado: float
    peor_caida: float
    meses_por_debajo: int
    aviso: str | None


@dataclass(frozen=True, slots=True)
class Curva:
    """La curva de una estrategia (una cifra por día de `dias`) y la parte de tu dinero que va a
    ella (`peso`: 0,9 = el 90 % del inicial y de cada aportación)."""

    dias: Sequence[int]
    valor: Sequence[float]
    peso: float = 1.0


def _fecha(dia: int) -> date:
    return datetime.fromtimestamp(dia * 86_400, UTC).date()


def simular(
    dias: Sequence[int],
    valor: Sequence[float],
    *,
    inicial: float,
    mensual: float,
    desde: date,
    fecha_texto: str | None = None,
) -> Simulada:
    """Aplica los rendimientos de `valor` (una cifra por día de `dias`) a tus aportaciones.

    `fecha_texto` es como se escribe el día de inicio en el aviso ("1 ene 2018"); si no se da, se
    usa la fecha ISO.

    Raises:
        SinDatosDesdeError: si no hay datos a partir de `desde`.
        ValueError: si no se pone nada (inicial y mensual a cero) o las cifras son negativas.
    """
    return simular_reparto(
        [Curva(dias, valor)],
        inicial=inicial,
        mensual=mensual,
        desde=desde,
        escribir_fecha=None if fecha_texto is None else (lambda _: fecha_texto),
    )


def simular_reparto(
    curvas: Sequence[Curva],
    *,
    inicial: float,
    mensual: float,
    desde: date,
    escribir_fecha: Callable[[date], str] | None = None,
    sujeto: str = "esta estrategia",
) -> Simulada:
    """Tu dinero repartido entre varias estrategias, cada parte en la suya, como una sola cuenta.

    Cada parte recibe su `peso` del inicial y de cada aportación y sigue los rendimientos de su
    curva. Las curvas se juntan por fecha: un día sin dato en una (la bolsa en fin de semana)
    vale lo de su último cierre. Empieza el primer día en que todas tienen datos desde `desde`,
    y la muestra semanal, las aportaciones y el peor momento se miden sobre la suma, igual que con
    una sola estrategia. La peor caída es la del reparto entero (su rendimiento ponderado por lo
    que vale cada parte), sin que tus aportaciones la disimulen. Con una sola curva es `simular`.

    `escribir_fecha` da el texto del día de inicio en el aviso (ISO si no se da); `sujeto`, de qué
    se habla en él ("esta estrategia", "tu reparto").

    Raises:
        SinDatosDesdeError: si alguna curva no tiene datos a partir de `desde`.
        ValueError: si no se pone nada (inicial y mensual a cero), las cifras son negativas o no
            hay ninguna curva con peso.
    """
    if inicial < 0 or mensual < 0:
        raise ValueError("el inicial y la aportación mensual no pueden ser negativos")
    if inicial == 0 and mensual == 0:
        raise ValueError("pon una cantidad inicial o una aportación mensual: con cero no hay nada")
    if not curvas or any(c.peso < 0 for c in curvas) or sum(c.peso for c in curvas) <= 0:
        raise ValueError("hace falta al menos una estrategia con una parte de tu dinero")

    fechas_de = [[_fecha(int(d)) for d in c.dias] for c in curvas]
    primeras: list[date] = []
    for fechas_k in fechas_de:
        primera = next((f for f in fechas_k if f >= desde), None)
        if primera is None:
            raise SinDatosDesdeError(f"no hay datos desde el {desde.isoformat()}")
        primeras.append(primera)
    inicio = max(primeras)
    fechas = sorted({f for fechas_k in fechas_de for f in fechas_k if f >= inicio})
    # El valor de cada curva en cada fecha del calendario común: el de su último dato.
    valores = [
        _al_calendario(fechas_k, c.valor, fechas)
        for fechas_k, c in zip(fechas_de, curvas, strict=True)
    ]
    total_pesos = sum(c.peso for c in curvas)

    saldos = [0.0] * len(curvas)
    aportado = 0.0
    indice = 1.0  # rendimiento acumulado del reparto, sin tus aportaciones
    maximo_indice = 1.0
    peor_caida = 0.0
    mes: tuple[int, int] | None = None
    peor: tuple[float, int, float, float] | None = None  # (proporcion, fila, valor, aportado)
    por_mes: dict[tuple[int, int], tuple[float, float]] = {}
    serie: list[tuple[float, float]] = []

    for i in range(len(fechas)):
        if i > 0:
            previo = sum(saldos)
            factor_reparto = 0.0
            for k, curva in enumerate(curvas):
                anterior = valores[k][i - 1]
                factor = valores[k][i] / anterior if anterior > 0 else 0.0
                # Cuánto pesa cada parte en el rendimiento del día: lo que valía al empezarlo.
                # Con una sola curva es exactamente 1 y el índice es el de la estrategia.
                parte = saldos[k] / previo if previo > 0 else curva.peso / total_pesos
                factor_reparto += parte * factor
                saldos[k] *= factor
            indice *= factor_reparto
        clave_mes = (fechas[i].year, fechas[i].month)
        if clave_mes != mes:
            entra = mensual + (inicial if i == 0 else 0.0)
            for k, curva in enumerate(curvas):
                saldos[k] += entra * curva.peso / total_pesos
            aportado += entra
            mes = clave_mes
        saldo = sum(saldos)
        maximo_indice = max(maximo_indice, indice)
        peor_caida = min(peor_caida, indice / maximo_indice - 1.0)
        if aportado > 0:
            proporcion = saldo / aportado
            if peor is None or proporcion < peor[0]:
                peor = (proporcion, i, saldo, aportado)
        por_mes[clave_mes] = (saldo, aportado)
        serie.append((saldo, aportado))

    assert peor is not None  # aportado > 0 desde el primer día: inicial o mensual no son cero
    aviso = None
    if inicio - desde > HOLGURA_INICIO:
        cuando = escribir_fecha(inicio) if escribir_fecha is not None else inicio.isoformat()
        aviso = f"Los datos de {sujeto} empiezan el {cuando}: tus números empiezan ahí."

    saldo_final = serie[-1][0]
    return Simulada(
        desde=inicio,
        hasta=fechas[-1],
        puntos=tuple(
            Punto(fecha=etiqueta, valor=serie[j][0], aportado=serie[j][1])
            for j, etiqueta in _semanales(fechas)
        ),
        aportado=aportado,
        valor_final=saldo_final,
        ganancia=saldo_final - aportado,
        peor_momento_fecha=fechas[peor[1]],
        peor_momento_valor=peor[2],
        peor_momento_aportado=peor[3],
        peor_caida=peor_caida,
        meses_por_debajo=sum(1 for s, a in por_mes.values() if s < a - 1e-9),
        aviso=aviso,
    )


def _al_calendario(
    fechas: Sequence[date], valor: Sequence[float], calendario: Sequence[date]
) -> list[float]:
    """El valor de la curva en cada fecha del calendario: el de su último dato en o antes.

    Cada fecha del calendario es posterior o igual al primer dato de la curva desde el inicio
    pedido (el calendario empieza cuando todas tienen datos), así que siempre hay uno.
    """
    salida: list[float] = []
    j = 0
    for dia in calendario:
        while j + 1 < len(fechas) and fechas[j + 1] <= dia:
            j += 1
        salida.append(float(valor[j]))
    return salida


def _semanales(fechas: Sequence[date]) -> list[tuple[int, date]]:
    """Posición y fecha de cada punto: el primer día, uno por semana y el último día.

    El de cada semana es el último día con datos de esa semana, pero se fecha en su **domingo**:
    la bolsa cierra la semana el viernes y la cripto el domingo, y la gráfica junta las
    estrategias por fecha. Con la fecha de su último día, una de bolsa y una de cripto no
    compartían ninguna y cada línea salía a trozos. El valor es el mismo: lo que valía el domingo
    es lo que valía al último cierre. El primero y el último llevan su fecha real (el último nunca
    se fecha en un domingo que aún no ha llegado).
    """
    elegidas: list[tuple[int, date]] = [(0, fechas[0])]
    ultimo = len(fechas) - 1
    for j in range(len(fechas)):
        if j == elegidas[-1][0]:
            continue
        if j == ultimo:
            elegidas.append((j, fechas[j]))
        elif fechas[j + 1].isocalendar()[:2] != fechas[j].isocalendar()[:2]:
            elegidas.append((j, fechas[j] + timedelta(days=6 - fechas[j].weekday())))
    return elegidas
