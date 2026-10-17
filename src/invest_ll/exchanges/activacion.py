"""En qué red se usa cada exchange, y los cerrojos para pasar a dinero real (panel v4 §1).

Generaliza a cualquier exchange el camino de Binance en v2 (`live/mode.py`, `live/modo_panel.py`,
§4.6 de `docs/panel-v2.md`). Para que un exchange opere con **dinero real**:

1. **Claves de real distintas de las de pruebas** (`ClavesExchange.mismas_que`).
2. **Evidencia de pruebas**, si el exchange tiene red de pruebas: al menos una orden de pruebas
   **de ese exchange** ejecutada (entera o en parte) en el registro de órdenes. No es una casilla
   que se marca: es algo que pasó y quedó escrito. Los que no tienen red de pruebas (Kraken,
   Coinbase) lo dicen; lo que exigen antes de real es haber probado la estrategia en ficticio,
   y eso lo pide el bot (§3), no la conexión.
3. **La clave no puede retirar**, si el exchange lo dice (todos lo dicen en dinero real: ver
   `fichas`). Si puede, no se activa; si no se pudo comprobar, tampoco.
4. **"DINERO REAL" tecleado** al activar (lo pide la ruta).

Y antes de activar cualquier red se prueba la conexión: se lee el saldo y los permisos, sin enviar
ninguna orden (`exchanges.prueba`).

**Qué se guarda**: `config/exchanges.json` (fuera de git) dice qué red está activa en cada exchange
y la última comprobación buena de cada red: cuándo, qué permisos tenía la clave y una huella de
las claves con que se hizo. La huella es un SHA-256 recortado: sirve para saber que las claves no
han cambiado desde la prueba (si cambian, hay que volver a activar), y no permite recuperarlas.
Las claves no van ahí: están en el almacén de credenciales (`exchanges.credenciales`).

**Binance y el entorno**: como en v2, las variables de entorno mandan sobre lo guardado en el
panel (`INVEST_LL_TESTNET_KEY`/`SECRET`, `INVEST_LL_LIVE_KEY`/`SECRET`), y
`INVEST_LL_TESTNET_VERIFIED` cuenta como haber operado en pruebas.

**Lo seguro es lo que pasa cuando algo falta**: si el exchange estaba activo en una red y ya no se
cumple lo que hacía falta (se borraron las claves, cambiaron), su estado efectivo es "sin
conectar" hasta que se vuelva a activar.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.errors import InvestLLError
from invest_ll.exchanges import credenciales
from invest_ll.exchanges.credenciales import ClavesExchange
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import VAR_TESTNET_HECHA
from invest_ll.live.modo_panel import VARIABLES, ordenes_ejecutadas

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping

    from invest_ll.exchanges.conector import Red
    from invest_ll.exchanges.fichas import Ficha

Activo = Literal["sin_conectar", "pruebas", "real"]
Origen = Literal["panel", "entorno", "ninguno"]
ACTIVOS: Final[tuple[Activo, ...]] = ("sin_conectar", "pruebas", "real")
REDES: Final[tuple[Red, ...]] = ("pruebas", "real")
RAIZ_CONFIG: Final = Path("config")
FICHERO: Final = "exchanges.json"
EN_LLANO: Final[dict[str, str]] = {"pruebas": "la red de pruebas", "real": "dinero real"}
DECLARADA: Final = ("1", "true", "si", "yes")


class ConfigExchangesError(InvestLLError):
    """`config/exchanges.json` existe pero no se puede leer."""


@dataclass(frozen=True, slots=True)
class Comprobacion:
    """Una prueba de conexión que salió bien: con qué claves (su huella) y qué se supo."""

    at: datetime
    huella: str
    puede_operar: bool | None
    puede_retirar: bool | None
    permisos: str


def huella(ficha: Ficha, red: Red, claves: ClavesExchange) -> str:
    """Identifica unas claves sin guardarlas: un SHA-256 recortado de todos sus valores."""
    partes = [ficha.id, red, *(claves.valores.get(c.clave, "") for c in ficha.campos)]
    return hashlib.sha256("\0".join(["invest-ll-huella", *partes]).encode()).hexdigest()[:16]


# -- La configuración ------------------------------------------------------------------------------


class ConfigExchanges:
    """`config/exchanges.json`: la red activa de cada exchange y su última comprobación buena."""

    __slots__ = ("_raiz",)

    def __init__(self, raiz: Path = RAIZ_CONFIG) -> None:
        self._raiz = raiz

    @property
    def path(self) -> Path:
        return self._raiz / FICHERO

    def _leer(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            crudo = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ConfigExchangesError(f"{self.path} no se puede leer ({error})") from error
        if not isinstance(crudo, dict):
            raise ConfigExchangesError(f"{self.path} no tiene el formato esperado")
        return _dict(cast("dict[str, Any]", crudo).get("exchanges"))

    def _exchange(self, exchange: str) -> dict[str, Any]:
        return _dict(self._leer().get(exchange))

    def activo(self, exchange: str) -> Activo | None:
        valor = self._exchange(exchange).get("activo")
        return next((a for a in ACTIVOS if a == valor), None)

    def comprobacion(self, exchange: str, red: Red) -> Comprobacion | None:
        crudo = _dict(_dict(self._exchange(exchange).get("redes")).get(red))
        try:
            return Comprobacion(
                at=datetime.fromisoformat(str(crudo["at"])),
                huella=str(crudo["huella"]),
                puede_operar=_opcional(crudo.get("puede_operar")),
                puede_retirar=_opcional(crudo.get("puede_retirar")),
                permisos=str(crudo.get("permisos", "")),
            )
        except (KeyError, ValueError, TypeError):
            return None

    def guardar_activo(self, exchange: str, activo: Activo, *, at: datetime) -> None:
        def cambio(e: dict[str, Any]) -> None:
            e.update(activo=activo, actualizado=at.isoformat())

        self._cambiar(exchange, cambio)

    def guardar_comprobacion(self, exchange: str, red: Red, comprobacion: Comprobacion) -> None:
        def cambio(e: dict[str, Any]) -> None:
            redes = _dict(e.get("redes"))
            redes[red] = {
                "at": comprobacion.at.isoformat(),
                "huella": comprobacion.huella,
                "puede_operar": comprobacion.puede_operar,
                "puede_retirar": comprobacion.puede_retirar,
                "permisos": comprobacion.permisos,
            }
            e["redes"] = redes

        self._cambiar(exchange, cambio)

    def olvidar(self, exchange: str, red: Red, *, at: datetime) -> None:
        """Las claves de esa red cambiaron o se borraron: su comprobación ya no vale y, si era la
        red activa, el exchange queda sin conectar."""

        def cambio(e: dict[str, Any]) -> None:
            redes = _dict(e.get("redes"))
            redes.pop(red, None)
            e["redes"] = redes
            if e.get("activo") == red:
                e.update(activo="sin_conectar", actualizado=at.isoformat())

        self._cambiar(exchange, cambio)

    def _cambiar(self, exchange: str, cambio: Callable[[dict[str, Any]], None]) -> None:
        try:
            todos = self._leer()
        except ConfigExchangesError:
            todos = {}  # estropeado: se reescribe desde cero (lo seguro: nada activo)
        actual = _dict(todos.get(exchange))
        cambio(actual)
        todos[exchange] = actual
        self._raiz.mkdir(parents=True, exist_ok=True)
        contenido = json.dumps({"exchanges": todos}, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._raiz, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(contenido)
            temporal = Path(tmp.name)
        os.replace(temporal, self.path)  # noqa: PTH105


def _dict(valor: object) -> dict[str, Any]:
    return cast("dict[str, Any]", valor) if isinstance(valor, dict) else {}


def _opcional(valor: object) -> bool | None:
    return valor if isinstance(valor, bool) else None


# -- Lo que decide el estado de un exchange ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Estado:
    """Todo lo que decide el estado de un exchange, leído una vez."""

    ficha: Ficha
    claves: Mapping[Red, ClavesExchange | None]
    origen: Mapping[Red, Origen]
    activo_guardado: Activo | None
    comprobaciones: Mapping[Red, Comprobacion | None]
    ordenes: Mapping[Red, int]
    """Órdenes de ese exchange ejecutadas en cada red, según el registro."""
    declarada_en_entorno: bool = False
    aviso: str | None = None


def _claves_del_entorno(
    entorno: Mapping[str, str], red: Red
) -> tuple[Origen, ClavesExchange | None]:
    """Binance, como en v2: si el entorno pone la clave o el secreto, mandan (las dos o nada)."""
    var_clave, var_secreto = VARIABLES[red]
    clave = entorno.get(var_clave, "").strip()
    secreto = entorno.get(var_secreto, "").strip()
    if not clave and not secreto:
        return "ninguno", None
    if not clave or not secreto:
        return "entorno", None
    return "entorno", ClavesExchange(valores={"apiKey": clave, "secret": secreto})


def leer(
    ficha: Ficha,
    *,
    entorno: Mapping[str, str] | None = None,
    config: ConfigExchanges | None = None,
    registro: ExecutionLedger | None = None,
) -> Estado:
    """Lee el entorno (solo Binance), el almacén de claves, la configuración y el registro."""
    env = dict(os.environ) if entorno is None else entorno
    cfg = config or ConfigExchanges()
    claves: dict[Red, ClavesExchange | None] = {}
    origen: dict[Red, Origen] = {}
    for red in REDES:
        if ficha.id == "binance":
            origen[red], claves[red] = _claves_del_entorno(env, red)
            if origen[red] == "entorno":
                continue
        guardadas = credenciales.leer(ficha, red)
        claves[red] = guardadas
        origen[red] = "panel" if guardadas is not None else "ninguno"
    aviso: str | None = None
    comprobaciones: dict[Red, Comprobacion | None] = dict.fromkeys(REDES)
    try:
        activo = cfg.activo(ficha.id)
        for red in REDES:
            comprobaciones[red] = cfg.comprobacion(ficha.id, red)
    except ConfigExchangesError as error:
        # Un fichero estropeado no tumba el panel: se ignora (nada activo) y se dice.
        activo, comprobaciones = None, dict.fromkeys(REDES)
        aviso = f"{error}: se ignora y {ficha.nombre} queda sin conectar. Vuelve a activarlo."
    entradas = (registro or ExecutionLedger()).entries()
    return Estado(
        ficha=ficha,
        claves=claves,
        origen=origen,
        activo_guardado=activo,
        comprobaciones=comprobaciones,
        ordenes={red: ordenes_ejecutadas(entradas, red, exchange=ficha.id) for red in REDES},
        declarada_en_entorno=(
            ficha.id == "binance" and env.get(VAR_TESTNET_HECHA, "").strip().lower() in DECLARADA
        ),
        aviso=aviso,
    )


def comprobacion_vigente(e: Estado, red: Red) -> Comprobacion | None:
    """La última prueba buena de esa red, si se hizo con las claves de ahora."""
    claves = e.claves.get(red)
    comprobacion = e.comprobaciones.get(red)
    if claves is None or comprobacion is None:
        return None
    return comprobacion if comprobacion.huella == huella(e.ficha, red, claves) else None


def con_evidencia_de_pruebas(e: Estado) -> bool:
    return e.ordenes.get("pruebas", 0) > 0 or e.declarada_en_entorno


def que_falta(e: Estado, red: Red) -> list[str]:
    """Lo que falta para poder activar ese exchange en esa red, en llano. Vacío si se puede (salvo
    probar la conexión y, para real, escribir DINERO REAL, que se hacen al activar)."""
    f = e.ficha
    faltan: list[str] = []
    if red == "pruebas":
        if not f.tiene_pruebas:
            faltan.append(f"{f.nombre} no tiene red de pruebas.")
        elif e.claves.get("pruebas") is None:
            faltan.append(f"Guarda las claves de la red de pruebas ({f.red_de_pruebas}).")
        return faltan
    reales = e.claves.get("real")
    pruebas = e.claves.get("pruebas")
    if reales is None:
        faltan.append("Guarda las claves de dinero real (sin permiso de retirada).")
    elif pruebas is not None and reales.mismas_que(pruebas):
        faltan.append("Las claves de dinero real tienen que ser distintas de las de pruebas.")
    if f.tiene_pruebas and not con_evidencia_de_pruebas(e):
        faltan.append(
            f"Haz al menos una orden en la red de pruebas de {f.nombre} que se ejecute: es la "
            "prueba de que esa etapa está hecha."
        )
    vigente = comprobacion_vigente(e, "real")
    if vigente is not None and vigente.puede_retirar:
        faltan.append(
            "La clave de dinero real puede retirar fondos: crea otra sin ese permiso y guárdala."
        )
    return faltan


def problema_de_permisos(f: Ficha, red: Red, puede_retirar: bool | None) -> str | None:
    """Por qué unos permisos impiden activar esa red, o `None` si no lo impiden."""
    if red != "real":
        return None
    if puede_retirar:
        return (
            "La clave de dinero real puede retirar fondos: crea otra sin ese permiso. Así, si "
            "alguien la consigue, puede operar pero no llevarse tu dinero."
        )
    if puede_retirar is None and f.sabe_si_retira(red):
        return (
            f"No se pudo comprobar que la clave no pueda retirar fondos ({f.nombre} lo dice, pero "
            "no se pudo leer): vuelve a probar."
        )
    return None


def activo_efectivo(e: Estado) -> Activo:
    """La red en la que se usa el exchange de verdad: la guardada, si aún se cumple todo."""
    guardado = e.activo_guardado or "sin_conectar"
    if guardado == "sin_conectar":
        return guardado
    vigente = comprobacion_vigente(e, guardado)
    if que_falta(e, guardado) or vigente is None:
        return "sin_conectar"
    if problema_de_permisos(e.ficha, guardado, vigente.puede_retirar) is not None:
        return "sin_conectar"
    return guardado


def por_que_no(e: Estado, red: Red) -> list[str]:
    """Por qué no se puede dar un conector con claves de esa red. Vacío si se puede.

    Real: el exchange activo en real (con todo lo que eso exige, comprobado otra vez ahora).
    Pruebas: activo en pruebas o en real, y las claves de pruebas probadas.
    """
    f = e.ficha
    activo = activo_efectivo(e)
    if red == "real":
        if activo == "real":
            return []
        return [
            f"{f.nombre} no está activo con dinero real: actívalo en Conexiones.",
            *que_falta(e, "real"),
        ]
    faltan = que_falta(e, "pruebas")
    if faltan:
        return faltan
    if activo == "sin_conectar":
        return [f"{f.nombre} no está conectado: actívalo en Conexiones."]
    if comprobacion_vigente(e, "pruebas") is None:
        return [
            f"Las claves de la red de pruebas de {f.nombre} no se han probado: vuelve a "
            "activar la red de pruebas."
        ]
    return []
