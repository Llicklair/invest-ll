"""Qué es una alerta aquí, y qué deliberadamente no lo es.

La FCA midió sobre más de 9.000 personas que las notificaciones aumentan un **11% el número de
operaciones** y un 8% las inversiones arriesgadas, con más efecto en quien menos sabe de
inversión. Con las cifras de este repositorio eso tiene precio: 423 operaciones se fueron 18.151
en comisiones; una sola operación, 87.

Así que las alertas de este módulo se construyen con tres reglas duras:

1. **Informan de un estado, no piden una acción.** "TLT lleva -18% desde que entraste" sí;
   "TLT está cayendo, ¿vendes?" no. La diferencia no es de tono: la segunda es la que se midió.
2. **Solo saltan por riesgo, nunca por ganancias.** Una alerta que dice "GLD subió un 20%" no
   informa de nada que necesites: existe para que abras la aplicación. `test_alerts.py` lo
   comprueba con series que solo suben.
3. **Se consultan, no persiguen.** No hay envío, ni push, ni correo. Tú preguntas cuando quieres.

Ver `docs/research-aplicaciones.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

# Códigos estables: el texto puede cambiar, el código no. Mismo contrato que los avisos de la CLI.
DATOS_OBSOLETOS = "stale_data"
CAIDA_DESDE_MAXIMO = "drawdown_from_peak"
PEOR_DE_LO_SIMULADO = "worse_than_simulated"
PERDIDA_DESDE_TU_ENTRADA = "loss_since_entry"
DESVIACION_DEL_PLAN = "drifted_from_plan"


class Nivel(Enum):
    """Cuánto pide mirar esto.

    Solo hay dos niveles, y ninguno se llama "urgente". La urgencia es precisamente el mecanismo
    que empuja a operar de más; un nivel llamado así invitaría a redactar mensajes para provocarla.
    """

    INFORMA = "informa"
    REVISAR = "revisar"


@dataclass(frozen=True, slots=True)
class Position:
    """Lo que tienes de un activo y a qué precio entraste.

    `entry_price` es el precio **medio** de entrada. Sin él no se puede decir nada honesto sobre
    tu pérdida: el drawdown del activo desde su máximo no es tu pérdida si entraste después.
    """

    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"la cantidad de {self.symbol} tiene que ser positiva")
        if self.entry_price <= 0:
            raise ValueError(f"el precio de entrada de {self.symbol} tiene que ser positivo")

    def value_at(self, price: Decimal) -> Decimal:
        return self.quantity * price

    @property
    def cost(self) -> Decimal:
        return self.quantity * self.entry_price


@dataclass(frozen=True, slots=True)
class Alert:
    """Un hecho medido sobre un activo o sobre la cartera.

    `measured` y `threshold` van separados del mensaje a propósito: quien la consuma desde un
    programa no debería tener que sacar el número de una frase.
    """

    code: str
    message: str
    level: Nivel = Nivel.INFORMA
    symbol: str | None = None
    measured: Decimal | None = None
    threshold: Decimal | None = None

    def render(self) -> str:
        marca = "[!]" if self.level is Nivel.REVISAR else "   "
        donde = f"{self.symbol}: " if self.symbol else ""
        return f"{marca} {donde}{self.message}"

    def __str__(self) -> str:
        return self.render()


@dataclass(frozen=True, slots=True)
class Umbrales:
    """A partir de dónde cada regla considera que hay algo que contar.

    Los valores por defecto son deliberadamente poco sensibles. Una alerta que salta cada día
    deja de leerse, y entonces no protege de nada — que es el modo de fallo real de esto.
    """

    dias_sin_datos: int = 7
    caida_desde_maximo: Decimal = Decimal("0.15")
    perdida_desde_entrada: Decimal = Decimal("0.10")
    desviacion_del_plan: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        if self.dias_sin_datos < 1:
            raise ValueError("dias_sin_datos tiene que ser al menos 1")
        for nombre in ("caida_desde_maximo", "perdida_desde_entrada", "desviacion_del_plan"):
            valor: Decimal = getattr(self, nombre)
            if not (0 < valor < 1):
                raise ValueError(f"{nombre} tiene que estar entre 0 y 1, no {valor}")
