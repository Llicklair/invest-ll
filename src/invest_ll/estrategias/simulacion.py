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
    from collections.abc import Sequence

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
    if inicial < 0 or mensual < 0:
        raise ValueError("el inicial y la aportación mensual no pueden ser negativos")
    if inicial == 0 and mensual == 0:
        raise ValueError("pon una cantidad inicial o una aportación mensual: con cero no hay nada")
    fechas = [_fecha(int(d)) for d in dias]
    primero = next((i for i, f in enumerate(fechas) if f >= desde), None)
    if primero is None:
        raise SinDatosDesdeError(f"no hay datos desde el {desde.isoformat()}")

    saldo = 0.0
    aportado = 0.0
    indice = 1.0  # rendimiento acumulado de la estrategia, sin tus aportaciones
    maximo_indice = 1.0
    peor_caida = 0.0
    mes: tuple[int, int] | None = None
    peor: tuple[float, int, float, float] | None = None  # (proporcion, fila, valor, aportado)
    por_mes: dict[tuple[int, int], tuple[float, float]] = {}
    serie: list[tuple[float, float]] = []

    for i in range(primero, len(fechas)):
        if i > primero:
            anterior = float(valor[i - 1])
            factor = float(valor[i]) / anterior if anterior > 0 else 0.0
            saldo *= factor
            indice *= factor
        clave_mes = (fechas[i].year, fechas[i].month)
        if clave_mes != mes:
            entra = mensual + (inicial if i == primero else 0.0)
            saldo += entra
            aportado += entra
            mes = clave_mes
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
    if fechas[primero] - desde > HOLGURA_INICIO:
        cuando = fecha_texto or fechas[primero].isoformat()
        aviso = f"Los datos de esta estrategia empiezan el {cuando}: tus números empiezan ahí."

    return Simulada(
        desde=fechas[primero],
        hasta=fechas[-1],
        puntos=tuple(
            Punto(fecha=fechas[primero + j], valor=serie[j][0], aportado=serie[j][1])
            for j in _semanales(fechas[primero:])
        ),
        aportado=aportado,
        valor_final=saldo,
        ganancia=saldo - aportado,
        peor_momento_fecha=fechas[peor[1]],
        peor_momento_valor=peor[2],
        peor_momento_aportado=peor[3],
        peor_caida=peor_caida,
        meses_por_debajo=sum(1 for s, a in por_mes.values() if s < a - 1e-9),
        aviso=aviso,
    )


def _semanales(fechas: Sequence[date]) -> list[int]:
    """Posiciones del primer día, del último día con datos de cada semana y del último."""
    elegidas: list[int] = [0]
    for j in range(len(fechas)):
        ultimo_de_su_semana = (
            j == len(fechas) - 1 or fechas[j + 1].isocalendar()[:2] != fechas[j].isocalendar()[:2]
        )
        if ultimo_de_su_semana and j != elegidas[-1]:
            elegidas.append(j)
    return elegidas
