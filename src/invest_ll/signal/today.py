"""La señal de hoy: en qué deberías estar, según la política, con los datos más recientes.

El sistema sabía medir el pasado y sabía enviar órdenes, pero no unía las dos cosas. Faltaba la
pregunta que se hace de verdad cada semana: *¿en qué estoy y en qué debería estar?*

**Esto no es un backtest.** Un backtest recorre la historia; esto mira el último periodo
disponible y aplica la misma regla que se validó. Por eso la fecha de los datos viaja con la
respuesta: una señal calculada con precios de hace tres semanas no es una señal, es arqueología, y
sin ese aviso parecería igual de fiable que una de hoy.

Ojo con la reserva de datos: recorta las series por diseño para que un backtest no toque el tramo
reservado. Para la señal actual eso sería letal —calcularía con precios viejos—, así que quien la
pide tiene que cargar las series con `use_reserved=True`. Esta función solo ve el universo que le
den; el aviso de retraso es lo que delata el error si alguien se equivoca.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from invest_ll.engine.universe_view import UniverseView
from invest_ll.strategy.rotation import RelativeMomentum

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.universe import Universe

# A partir de aquí los datos dejan de describir el mercado de hoy. Con velas diarias, tres días
# suelen ser un fin de semana largo; más que eso es que falta una descarga.
DIAS_ANTES_DE_AVISAR = 3


@dataclass(frozen=True, slots=True)
class Senal:
    """Lo que la política dice hoy, y cómo de fresco es el dato en el que se apoya."""

    elegido: str | None
    tienes: str | None
    datos_hasta: datetime | None
    dias_de_retraso: int
    motivo: str = ""

    @property
    def en_mercado(self) -> bool:
        return self.elegido is not None

    @property
    def datos_viejos(self) -> bool:
        return self.dias_de_retraso > DIAS_ANTES_DE_AVISAR

    @property
    def hay_que_mover(self) -> bool:
        return self.elegido != self.tienes

    @property
    def vender(self) -> str | None:
        return self.tienes if self.hay_que_mover else None

    @property
    def comprar(self) -> str | None:
        return self.elegido if self.hay_que_mover else None

    def describe(self) -> str:
        partes: list[str] = []

        if self.motivo:
            partes.append(self.motivo)
        elif not self.en_mercado:
            partes.append(
                "FUERA DEL MERCADO: ningun activo del universo sube en la ventana mirada. "
                "Quedarse en 'el que menos cae' pierde igual, solo que mas despacio."
            )
        elif not self.hay_que_mover:
            partes.append(f"Ya estas en {self.elegido}: no hay nada que hacer.")
        else:
            movimiento = f"comprar {self.comprar}" if self.comprar else "salir del mercado"
            if self.vender:
                movimiento = f"vender {self.vender} y {movimiento}"
            partes.append(f"Toca {movimiento}.")

        if self.datos_hasta is not None:
            partes.append(f"Datos hasta {self.datos_hasta.date()}.")
        if self.datos_viejos:
            partes.append(
                f"[!] Llevan {self.dias_de_retraso} dia(s) de retraso: descarga antes de operar, "
                "o estaras decidiendo con el mercado de la semana pasada."
            )

        partes.append(
            "Esto no predice nada: es la regla aplicada al ultimo dato. Nada garantiza que "
            "lo que funciono en el pasado siga funcionando."
        )
        return " ".join(partes)


def senal_de_hoy(
    universe: Universe,
    *,
    lookback: int = 30,
    min_return: float | None = 0.0,
    tienes: str | None = None,
    ahora: datetime | None = None,
) -> Senal:
    """Aplica la política al último periodo disponible del universo.

    `min_return=0.0` es el filtro que sobrevivió a la validación fuera de muestra: sin él, la
    rotación se queda siempre dentro del mercado, también cuando todo cae.
    """
    momento = ahora or datetime.now(UTC)
    ultimo = universe.timestamps[-1] if len(universe) else None
    retraso = (momento - ultimo).days if ultimo is not None else 0

    if len(universe) <= lookback:
        return Senal(
            elegido=None,
            tienes=tienes,
            datos_hasta=ultimo,
            dias_de_retraso=max(retraso, 0),
            motivo=(
                f"Sin historia suficiente: hacen falta mas de {lookback} periodos y hay "
                f"{len(universe)}. Descarga mas historico antes de decidir nada."
            ),
        )

    elegido = RelativeMomentum(lookback=lookback, min_return=min_return).choose(
        UniverseView(universe, len(universe) - 1)
    )
    return Senal(
        elegido=elegido,
        tienes=tienes,
        datos_hasta=ultimo,
        dias_de_retraso=max(retraso, 0),
    )
