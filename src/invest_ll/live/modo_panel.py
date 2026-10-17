"""El modo efectivo del panel: el del entorno si lo hay; si no, el elegido en el panel.

**Los cuatro cerrojos de `live/mode.py` no se tocan.** Lo único que cambia es DE DÓNDE salen el
modo y las claves: se construye un entorno (`entorno_efectivo`) y se le pasa a `resolve_mode`, que
decide exactamente igual que para la línea de comandos. Si un cerrojo no se cumple, falla igual.

De dónde sale cada variable, por orden (lo primero manda):

1. El entorno del proceso, como hoy (docs/operar-de-verdad.md). Si `INVEST_LL_MODE` está puesto,
   el modo lo fija el entorno y el panel no puede cambiarlo.
2. El panel: el modo en `config/panel.json` (fuera de git) y las claves en el almacén de
   credenciales del sistema (`credenciales`). Cada par clave/secreto se toma entero de un sitio:
   nunca la clave del entorno con el secreto del almacén.
3. `INVEST_LL_TESTNET_VERIFIED` solo se pone desde el panel si hay **evidencia**: al menos una
   orden de la red de pruebas ejecutada (entera o en parte) en el registro de órdenes. No es una
   casilla que se marca: es algo que pasó y quedó escrito.

Si el modo lo eligió el panel y ya no se puede activar (se borraron las claves, por ejemplo), el
panel vuelve a simulación y lo dice: lo seguro es lo que pasa cuando algo falta. Si lo fija el
entorno, el error sale tal cual, como en la línea de comandos.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.errors import InvestLLError
from invest_ll.live import credenciales
from invest_ll.live.broker import OrderStatus
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import (
    VAR_CLAVE_PRUEBAS,
    VAR_CLAVE_REAL,
    VAR_MODO,
    VAR_SECRETO_PRUEBAS,
    VAR_SECRETO_REAL,
    VAR_TESTNET_HECHA,
    CredentialError,
    ModeError,
    OperatingMode,
    Real,
    Simulation,
    Testnet,
    resolve_mode,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Mapping

    from invest_ll.live.credenciales import Claves, Red
    from invest_ll.live.ledger import LedgerEntry

ModoPanel = Literal["simulacion", "pruebas", "real"]
Origen = Literal["panel", "entorno"]
MODOS: Final[tuple[ModoPanel, ...]] = ("simulacion", "pruebas", "real")

RAIZ_CONFIG: Final = Path("config")
FICHERO_CONFIG: Final = "panel.json"

MODO_EN_EL_ENTORNO: Final[dict[ModoPanel, str]] = {
    "simulacion": "simulation",
    "pruebas": "testnet",
    "real": "real",
}
VARIABLES: Final[dict[Red, tuple[str, str]]] = {
    "pruebas": (VAR_CLAVE_PRUEBAS, VAR_SECRETO_PRUEBAS),
    "real": (VAR_CLAVE_REAL, VAR_SECRETO_REAL),
}
NOMBRE_EN_EL_REGISTRO: Final[dict[Red, str]] = {"pruebas": "pruebas", "real": "REAL"}
EJECUTADAS: Final = frozenset({OrderStatus.FILLED, OrderStatus.PARTIAL})


class ConfigPanelError(InvestLLError):
    """`config/panel.json` existe pero no se puede leer."""


def modo_del_panel(modo: OperatingMode) -> ModoPanel:
    if isinstance(modo, Real):
        return "real"
    if isinstance(modo, Testnet):
        return "pruebas"
    return "simulacion"


# -- La configuración del panel ---------------------------------------------------------------


class ConfigPanel:
    """El modo elegido en el panel, en `config/panel.json`. Nada más: las claves no van aquí."""

    __slots__ = ("_raiz",)

    def __init__(self, raiz: Path = RAIZ_CONFIG) -> None:
        self._raiz = raiz

    @property
    def path(self) -> Path:
        return self._raiz / FICHERO_CONFIG

    def modo(self) -> ModoPanel | None:
        if not self.path.exists():
            return None
        try:
            crudo = cast("dict[str, Any]", json.loads(self.path.read_text(encoding="utf-8")))
            modo = str(crudo["modo"])
        except (ValueError, KeyError, TypeError) as error:
            raise ConfigPanelError(f"{self.path} no se puede leer ({error})") from error
        if modo not in MODOS:
            raise ConfigPanelError(f"{self.path}: modo desconocido {modo!r}")
        return modo

    def guardar_modo(self, modo: ModoPanel) -> None:
        self._raiz.mkdir(parents=True, exist_ok=True)
        contenido = {"modo": modo, "actualizado": datetime.now(UTC).isoformat()}
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._raiz, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n")
            temporal = Path(tmp.name)
        os.replace(temporal, self.path)  # noqa: PTH105


# -- La evidencia del registro de órdenes -------------------------------------------------------


def ordenes_ejecutadas(
    entradas: Iterable[LedgerEntry], red: Red, *, exchange: str = "binance"
) -> int:
    """Órdenes de esa red y ese exchange que se ejecutaron (enteras o en parte), según el registro.

    Desde v4 el registro guarda órdenes de varios exchanges: una orden de pruebas de Bybit no es
    evidencia de haber operado en la red de pruebas de Binance. Las entradas de antes de v4 no
    dicen el exchange y son de Binance (`LedgerEntry.exchange_de`).
    """
    nombre = NOMBRE_EN_EL_REGISTRO[red]
    return sum(
        1
        for e in entradas
        if e.mode_name == nombre
        and e.exchange_de == exchange
        and e.result.status in EJECUTADAS
        and e.result.filled_quantity > 0
    )


# -- El entorno efectivo ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Fuentes:
    """Todo lo que decide el modo, leído una vez. `claves` son las del almacén del panel."""

    entorno: Mapping[str, str]
    modo_panel: ModoPanel | None
    claves: Mapping[Red, Claves | None]
    ordenes_de_pruebas: int
    ordenes_reales: int = 0
    aviso: str | None = None
    """Algo que no se pudo leer (un `config/panel.json` estropeado) y se ignoró diciéndolo."""


def _puesto(entorno: Mapping[str, str], variable: str) -> bool:
    return bool(entorno.get(variable, "").strip())


def origen_del_modo(entorno: Mapping[str, str]) -> Origen:
    return "entorno" if _puesto(entorno, VAR_MODO) else "panel"


def origen_de_las_claves(f: Fuentes, red: Red) -> Literal["panel", "entorno", "ninguno"]:
    clave, secreto = VARIABLES[red]
    if _puesto(f.entorno, clave) or _puesto(f.entorno, secreto):
        return "entorno"
    return "panel" if f.claves.get(red) is not None else "ninguno"


def claves_efectivas(f: Fuentes, red: Red) -> Claves | None:
    """Las claves que se usarían para esa red (entorno primero), o `None` si faltan."""
    var_clave, var_secreto = VARIABLES[red]
    if origen_de_las_claves(f, red) == "entorno":
        clave = f.entorno.get(var_clave, "").strip()
        secreto = f.entorno.get(var_secreto, "").strip()
        if not clave or not secreto:
            return None
        return credenciales.Claves(clave=clave, secreto=secreto)
    return f.claves.get(red)


def entorno_efectivo(f: Fuentes) -> dict[str, str]:
    """El entorno con lo que falta completado desde el panel. Lo del entorno no se pisa nunca."""
    efectivo = dict(f.entorno)
    if not _puesto(efectivo, VAR_MODO) and f.modo_panel is not None:
        efectivo[VAR_MODO] = MODO_EN_EL_ENTORNO[f.modo_panel]
    for red, (var_clave, var_secreto) in VARIABLES.items():
        if origen_de_las_claves(f, red) != "panel":
            continue
        claves = f.claves.get(red)
        if claves is not None:
            efectivo[var_clave] = claves.clave
            efectivo[var_secreto] = claves.secreto
    if not _puesto(efectivo, VAR_TESTNET_HECHA) and f.ordenes_de_pruebas > 0:
        efectivo[VAR_TESTNET_HECHA] = "1"
    return efectivo


@dataclass(frozen=True, slots=True)
class ModoEfectivo:
    modo: OperatingMode
    origen: Origen
    aviso: str | None = None


def resolver(f: Fuentes) -> ModoEfectivo:
    """El modo con el que trabaja el panel. Ver el docstring del módulo."""
    entorno = entorno_efectivo(f)
    if origen_del_modo(f.entorno) == "entorno":
        return ModoEfectivo(resolve_mode(entorno), "entorno")
    try:
        return ModoEfectivo(resolve_mode(entorno), "panel", f.aviso)
    except (ModeError, CredentialError) as error:
        return ModoEfectivo(
            Simulation(),
            "panel",
            f"El modo '{f.modo_panel}' elegido en el panel no se puede activar ({error}). "
            "Sigues en simulación: no se envía nada.",
        )


def fuentes_actuales(
    *,
    entorno: Mapping[str, str] | None = None,
    config: ConfigPanel | None = None,
    registro: ExecutionLedger | None = None,
) -> Fuentes:
    """Lee el entorno del proceso, `config/panel.json`, el almacén de claves y el registro."""
    entradas = (registro or ExecutionLedger()).entries()
    aviso: str | None = None
    try:
        modo_panel = (config or ConfigPanel()).modo()
    except ConfigPanelError as error:
        # Un fichero estropeado no puede dejar el panel sin arrancar: se ignora, se vuelve a lo
        # seguro (simulación) y se dice. Elegir el modo otra vez lo reescribe.
        modo_panel = None
        aviso = f"{error}: se ignora y sigues en simulación. Vuelve a elegir el modo."
    return Fuentes(
        entorno=dict(os.environ) if entorno is None else dict(entorno),
        modo_panel=modo_panel,
        claves={red: credenciales.leer(red) for red in credenciales.REDES},
        ordenes_de_pruebas=ordenes_ejecutadas(entradas, "pruebas"),
        ordenes_reales=ordenes_ejecutadas(entradas, "real"),
        aviso=aviso,
    )
