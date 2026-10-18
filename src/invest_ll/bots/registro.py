"""Los bots en disco: `bots/<id>/` (fuera de git), para que al reabrir el panel sigan donde estaban.

Por bot:

- `definicion.json`: lo que se eligió al desplegarlo (plantilla, monedas, capital, parámetros).
  No cambia.
- `estado.json`: lo que cambia (en marcha o parado, efectivo, posiciones, memoria de la plantilla,
  precios de arranque, peor caída…). Se reescribe entero, de forma atómica: quien lo lea ve el de
  antes o el de después, nunca uno a medias.
- `operaciones.jsonl`, `eventos.jsonl` y `curva.jsonl`: registros que solo añaden, una línea JSON
  por apunte. La curva lleva como mucho un punto por minuto (lo decide el motor). Si el panel se
  cortara a mitad de una línea, esa línea se ignora al leer.

El dinero y las cantidades van como texto (Decimal); las fechas, en ISO con zona.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.bots.cuenta import Cuenta, Posicion
from invest_ll.errors import InvestLLError
from invest_ll.fetch.atomic_write import replace_atomically

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from invest_ll.bots.decisiones import Lado

EstadoBot = Literal["en_marcha", "parado", "error"]
TipoEvento = Literal[
    "arranque", "parada", "error", "hueco", "info", "limite", "desconocido", "conciliacion", "real"
]
TIPOS_EVENTO: Final = (
    "arranque",
    "parada",
    "error",
    "hueco",
    "info",
    "limite",
    "desconocido",
    "conciliacion",
    "real",
)
ModoBot = Literal["ficticio", "pruebas", "real"]

CARPETA: Final = Path("bots")
"""Relativa al directorio de trabajo, como las demás carpetas de datos del panel."""
DEFINICION: Final = "definicion.json"
ESTADO: Final = "estado.json"
OPERACIONES: Final = "operaciones.jsonl"
EVENTOS: Final = "eventos.jsonl"
CURVA: Final = "curva.jsonl"
EXAMEN: Final = "examen.json"
_ID: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class BotNoEncontradoError(InvestLLError):
    """No hay ningún bot con ese id."""


@dataclass(frozen=True, slots=True)
class Limites:
    """Los de un bot de pruebas o real (docs/panel-v4-real.md §3): se comprueban antes de cada
    orden y, si no cabe, no sale."""

    capital_max: Decimal
    orden_max: Decimal
    perdida_max_pct: float
    vender_al_parar: bool
    operaciones_max_dia: int


@dataclass(frozen=True, slots=True)
class Definicion:
    id: str
    nombre: str
    plantilla: str
    monedas: tuple[str, ...]
    capital: Decimal
    parametros: dict[str, str]
    creado: datetime
    modo: ModoBot = "ficticio"
    exchange: str | None = None
    """En pruebas y real, el exchange donde opera; en ficticio, None (precios de Hyperliquid)."""
    estrategia: str | None = None
    """Con la plantilla `medida`, el id de la estrategia a medida."""
    limites: Limites | None = None
    activado: datetime | None = None
    """Cuándo empezó en su modo de ahora (al activar el dinero real, empieza de cero)."""


@dataclass(frozen=True, slots=True)
class Pausa:
    """Un bot de exchange que se ha parado solo y necesita que lo mires antes de reanudarlo."""

    motivo: str
    """`desconocido` (una orden que no se sabe si salió) o `conciliacion` (no cuadra el saldo)."""
    texto: str
    diferencia: str | None = None
    id_cliente: str | None = None
    """La orden de la que no se sabe nada (para resolverla al reanudar)."""
    at: datetime | None = None
    coin: str | None = None
    """La moneda y el lado de esa orden: con ellos se busca y, si salió, se apunta."""
    lado: Lado | None = None


@dataclass(slots=True)
class Estado:
    estado: EstadoBot
    cuenta: Cuenta
    motivo_error: str | None = None
    memoria: dict[str, str] = field(default_factory=dict[str, str])
    precios_arranque: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    """Los de la primera vez que se conoció el precio de cada moneda: la base de "mantener"."""
    ultimos_precios: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    """Para valorar el bot aunque la fuente no tenga precio en ese momento."""
    ultima_vez: datetime | None = None
    """La última vez que el motor lo atendió en marcha: de aquí sale el hueco al reabrir."""
    maximo: Decimal | None = None
    peor_caida: float | None = None
    operaciones: int = 0
    ultima_operacion: datetime | None = None
    aviso: str | None = None
    """El último hueco ("Panel cerrado de 14:02 a 18:30: no pudo operar"), hasta `aviso_hasta`."""
    aviso_hasta: datetime | None = None
    pausa: Pausa | None = None
    dia: str | None = None
    """El día (en la hora de Marcos) al que se refiere `operaciones_hoy`."""
    operaciones_hoy: int = 0


@dataclass(frozen=True, slots=True)
class Operacion:
    at: datetime
    coin: str
    lado: Lado
    cantidad: Decimal
    precio: Decimal
    importe: Decimal
    comision: Decimal
    motivo: str


@dataclass(frozen=True, slots=True)
class Evento:
    at: datetime
    tipo: TipoEvento
    texto: str


@dataclass(frozen=True, slots=True)
class Punto:
    at: datetime
    valor: Decimal
    mantener: Decimal | None


# -- De y a JSON -----------------------------------------------------------------------------------


def _txt(valor: Decimal) -> str:
    return format(valor, "f")


def _fecha(texto: object) -> datetime | None:
    return datetime.fromisoformat(str(texto)) if texto else None


def _decimales(datos: object) -> dict[str, Decimal]:
    return {str(k): Decimal(str(v)) for k, v in cast("dict[str, object]", datos or {}).items()}


def limites_a_json(lim: Limites | None) -> dict[str, Any] | None:
    if lim is None:
        return None
    return {
        "capital_max": _txt(lim.capital_max),
        "orden_max": _txt(lim.orden_max),
        "perdida_max_pct": lim.perdida_max_pct,
        "vender_al_parar": lim.vender_al_parar,
        "operaciones_max_dia": lim.operaciones_max_dia,
    }


def limites_de_json(datos: object) -> Limites | None:
    if not isinstance(datos, dict):
        return None
    d = cast("dict[str, object]", datos)
    return Limites(
        capital_max=Decimal(str(d["capital_max"])),
        orden_max=Decimal(str(d["orden_max"])),
        perdida_max_pct=float(str(d["perdida_max_pct"])),
        vender_al_parar=bool(d.get("vender_al_parar", False)),
        operaciones_max_dia=int(str(d["operaciones_max_dia"])),
    )


def definicion_a_json(d: Definicion) -> dict[str, Any]:
    return {
        "id": d.id,
        "nombre": d.nombre,
        "plantilla": d.plantilla,
        "monedas": list(d.monedas),
        "capital": _txt(d.capital),
        "parametros": d.parametros,
        "creado": d.creado.isoformat(),
        "modo": d.modo,
        "exchange": d.exchange,
        "estrategia": d.estrategia,
        "limites": limites_a_json(d.limites),
        "activado": d.activado.isoformat() if d.activado else None,
    }


def definicion_de_json(datos: dict[str, Any]) -> Definicion:
    creado = _fecha(datos["creado"])
    assert creado is not None
    return Definicion(
        id=str(datos["id"]),
        nombre=str(datos["nombre"]),
        plantilla=str(datos["plantilla"]),
        monedas=tuple(str(c) for c in datos["monedas"]),
        capital=Decimal(str(datos["capital"])),
        parametros={str(k): str(v) for k, v in dict(datos["parametros"]).items()},
        creado=creado,
        modo=_modo(datos.get("modo")),
        exchange=str(datos["exchange"]) if datos.get("exchange") else None,
        estrategia=str(datos["estrategia"]) if datos.get("estrategia") else None,
        limites=limites_de_json(datos.get("limites")),
        activado=_fecha(datos.get("activado")),
    )


def _modo(valor: object) -> ModoBot:
    """Los bots de antes de v4 no tienen modo: son ficticios."""
    if valor == "pruebas":
        return "pruebas"
    if valor == "real":
        return "real"
    return "ficticio"


def _pausa_a_json(p: Pausa | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {
        "motivo": p.motivo,
        "texto": p.texto,
        "diferencia": p.diferencia,
        "id_cliente": p.id_cliente,
        "at": p.at.isoformat() if p.at else None,
        "coin": p.coin,
        "lado": p.lado,
    }


def _pausa_de_json(datos: object) -> Pausa | None:
    if not isinstance(datos, dict):
        return None
    d = cast("dict[str, object]", datos)
    return Pausa(
        motivo=str(d.get("motivo") or ""),
        texto=str(d.get("texto") or ""),
        diferencia=str(d["diferencia"]) if d.get("diferencia") else None,
        id_cliente=str(d["id_cliente"]) if d.get("id_cliente") else None,
        at=_fecha(d.get("at")),
        coin=str(d["coin"]) if d.get("coin") else None,
        lado="venta" if d.get("lado") == "venta" else "compra" if d.get("lado") else None,
    )


def estado_a_json(e: Estado) -> dict[str, Any]:
    return {
        "estado": e.estado,
        "motivo_error": e.motivo_error,
        "efectivo": _txt(e.cuenta.efectivo),
        "posiciones": {
            c: {"cantidad": _txt(p.cantidad), "coste": _txt(p.coste)}
            for c, p in e.cuenta.posiciones.items()
        },
        "memoria": e.memoria,
        "precios_arranque": {c: _txt(p) for c, p in e.precios_arranque.items()},
        "ultimos_precios": {c: _txt(p) for c, p in e.ultimos_precios.items()},
        "ultima_vez": e.ultima_vez.isoformat() if e.ultima_vez else None,
        "maximo": _txt(e.maximo) if e.maximo is not None else None,
        "peor_caida": e.peor_caida,
        "operaciones": e.operaciones,
        "ultima_operacion": e.ultima_operacion.isoformat() if e.ultima_operacion else None,
        "aviso": e.aviso,
        "aviso_hasta": e.aviso_hasta.isoformat() if e.aviso_hasta else None,
        "pausa": _pausa_a_json(e.pausa),
        "dia": e.dia,
        "operaciones_hoy": e.operaciones_hoy,
    }


def estado_de_json(datos: dict[str, Any]) -> Estado:
    posiciones = {
        str(c): Posicion(Decimal(str(p["cantidad"])), Decimal(str(p["coste"])))
        for c, p in dict(datos.get("posiciones") or {}).items()
    }
    estado = str(datos["estado"])
    assert estado in ("en_marcha", "parado", "error"), estado
    maximo = datos.get("maximo")
    peor = datos.get("peor_caida")
    return Estado(
        estado=estado,
        cuenta=Cuenta(efectivo=Decimal(str(datos["efectivo"])), posiciones=posiciones),
        motivo_error=datos.get("motivo_error"),
        memoria={str(k): str(v) for k, v in dict(datos.get("memoria") or {}).items()},
        precios_arranque=_decimales(datos.get("precios_arranque")),
        ultimos_precios=_decimales(datos.get("ultimos_precios")),
        ultima_vez=_fecha(datos.get("ultima_vez")),
        maximo=Decimal(str(maximo)) if maximo is not None else None,
        peor_caida=float(peor) if peor is not None else None,
        operaciones=int(datos.get("operaciones") or 0),
        ultima_operacion=_fecha(datos.get("ultima_operacion")),
        aviso=datos.get("aviso"),
        aviso_hasta=_fecha(datos.get("aviso_hasta")),
        pausa=_pausa_de_json(datos.get("pausa")),
        dia=str(datos["dia"]) if datos.get("dia") else None,
        operaciones_hoy=int(datos.get("operaciones_hoy") or 0),
    )


def _operacion_de_json(d: dict[str, Any]) -> Operacion:
    at = _fecha(d["at"])
    assert at is not None
    lado = str(d["lado"])
    assert lado in ("compra", "venta"), lado
    return Operacion(
        at=at,
        coin=str(d["coin"]),
        lado=lado,
        cantidad=Decimal(str(d["cantidad"])),
        precio=Decimal(str(d["precio"])),
        importe=Decimal(str(d["importe"])),
        comision=Decimal(str(d["comision"])),
        motivo=str(d["motivo"]),
    )


def _evento_de_json(d: dict[str, Any]) -> Evento:
    at = _fecha(d["at"])
    assert at is not None
    tipo = str(d["tipo"])
    assert tipo in TIPOS_EVENTO, tipo
    return Evento(at=at, tipo=tipo, texto=str(d["texto"]))


def _punto_de_json(d: dict[str, Any]) -> Punto:
    at = _fecha(d["at"])
    assert at is not None
    mantener = d.get("mantener")
    return Punto(
        at=at,
        valor=Decimal(str(d["valor"])),
        mantener=Decimal(str(mantener)) if mantener is not None else None,
    )


# -- El registro -----------------------------------------------------------------------------------


def nuevo_id(nombre: str) -> str:
    """'Tendencia BTC' -> 'tendencia-btc-3f9a1c': legible en la carpeta y único."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")[:40].strip("-") or "bot"
    return f"{base}-{secrets.token_hex(3)}"


def id_valido(bot_id: str) -> bool:
    """Solo minúsculas, cifras y guiones: un id nunca sale de `bots/`."""
    return bool(_ID.match(bot_id))


class Registro:
    """Las carpetas de los bots bajo `raiz`."""

    __slots__ = ("raiz",)

    def __init__(self, raiz: Path = CARPETA) -> None:
        self.raiz = raiz

    def carpeta(self, bot_id: str) -> Path:
        if not id_valido(bot_id):
            raise BotNoEncontradoError(f"No hay ningún bot «{bot_id}».")
        return self.raiz / bot_id

    def ids(self) -> list[str]:
        if not self.raiz.is_dir():
            return []
        return sorted(
            c.name for c in self.raiz.iterdir() if id_valido(c.name) and (c / DEFINICION).is_file()
        )

    def existe(self, bot_id: str) -> bool:
        return id_valido(bot_id) and (self.raiz / bot_id / DEFINICION).is_file()

    def crear(self, definicion: Definicion, estado: Estado) -> None:
        carpeta = self.carpeta(definicion.id)
        carpeta.mkdir(parents=True, exist_ok=False)
        self._escribir(carpeta / DEFINICION, definicion_a_json(definicion))
        self.guardar_estado(definicion.id, estado)

    def definicion(self, bot_id: str) -> Definicion:
        return definicion_de_json(self._leer(bot_id, DEFINICION))

    def estado(self, bot_id: str) -> Estado:
        return estado_de_json(self._leer(bot_id, ESTADO))

    def guardar_estado(self, bot_id: str, estado: Estado) -> None:
        self._escribir(self.carpeta(bot_id) / ESTADO, estado_a_json(estado))

    def guardar_examen(self, bot_id: str, datos: dict[str, Any]) -> None:
        """El último examen sobre el pasado (`bots.examen`), tal cual."""
        self._escribir(self.carpeta(bot_id) / EXAMEN, datos)

    def examen(self, bot_id: str) -> dict[str, Any] | None:
        ruta = self.carpeta(bot_id) / EXAMEN
        if not ruta.is_file():
            return None
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return cast("dict[str, Any]", datos) if isinstance(datos, dict) else None

    def guardar_definicion(self, definicion: Definicion) -> None:
        """Al cambiar de modo (activar el dinero real) o de límites."""
        self._escribir(self.carpeta(definicion.id) / DEFINICION, definicion_a_json(definicion))

    def archivar_historia(self, bot_id: str, etiqueta: str) -> None:
        """Al empezar de cero en otro modo: su curva y sus operaciones de antes se guardan aparte
        (`curva-<etiqueta>.jsonl`, `operaciones-<etiqueta>.jsonl`) y no se mezclan con las nuevas."""
        carpeta = self.carpeta(bot_id)
        for fichero in (CURVA, OPERACIONES):
            ruta = carpeta / fichero
            if ruta.is_file():
                ruta.replace(carpeta / fichero.replace(".jsonl", f"-{etiqueta}.jsonl"))

    def operacion(self, bot_id: str, o: Operacion) -> None:
        self._anadir(
            bot_id,
            OPERACIONES,
            {
                "at": o.at.isoformat(),
                "coin": o.coin,
                "lado": o.lado,
                "cantidad": _txt(o.cantidad),
                "precio": _txt(o.precio),
                "importe": _txt(o.importe),
                "comision": _txt(o.comision),
                "motivo": o.motivo,
            },
        )

    def evento(self, bot_id: str, e: Evento) -> None:
        self._anadir(bot_id, EVENTOS, {"at": e.at.isoformat(), "tipo": e.tipo, "texto": e.texto})

    def punto(self, bot_id: str, p: Punto) -> None:
        self._anadir(
            bot_id,
            CURVA,
            {
                "at": p.at.isoformat(),
                "valor": _txt(p.valor),
                "mantener": _txt(p.mantener) if p.mantener is not None else None,
            },
        )

    def operaciones(self, bot_id: str) -> list[Operacion]:
        return [_operacion_de_json(d) for d in self._lineas(bot_id, OPERACIONES)]

    def eventos(self, bot_id: str) -> list[Evento]:
        return [_evento_de_json(d) for d in self._lineas(bot_id, EVENTOS)]

    def curva(self, bot_id: str) -> list[Punto]:
        return [_punto_de_json(d) for d in self._lineas(bot_id, CURVA)]

    def borrar(self, bot_id: str) -> None:
        carpeta = self.carpeta(bot_id)
        if not (carpeta / DEFINICION).is_file():
            raise BotNoEncontradoError(f"No hay ningún bot «{bot_id}».")
        shutil.rmtree(carpeta)

    # -- Por dentro --

    def _leer(self, bot_id: str, fichero: str) -> dict[str, Any]:
        ruta = self.carpeta(bot_id) / fichero
        try:
            texto = ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise BotNoEncontradoError(f"No hay ningún bot «{bot_id}».") from None
        return cast("dict[str, Any]", json.loads(texto))

    @staticmethod
    def _escribir(destino: Path, datos: dict[str, Any]) -> None:
        texto = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
        replace_atomically(
            destino, lambda tmp: tmp.write_text(texto, encoding="utf-8", newline="\n")
        )

    def _anadir(self, bot_id: str, fichero: str, datos: dict[str, Any]) -> None:
        linea = json.dumps(datos, ensure_ascii=False) + "\n"
        with (self.carpeta(bot_id) / fichero).open("a", encoding="utf-8", newline="\n") as f:
            f.write(linea)

    def _lineas(self, bot_id: str, fichero: str) -> Iterator[dict[str, Any]]:
        ruta = self.carpeta(bot_id) / fichero
        if not ruta.is_file():
            return
        with ruta.open(encoding="utf-8") as f:
            for linea in f:
                if not linea.strip():
                    continue
                try:
                    datos = json.loads(linea)
                except json.JSONDecodeError:
                    continue  # una línea cortada a medias por un cierre brusco
                if isinstance(datos, dict):
                    yield cast("dict[str, Any]", datos)
