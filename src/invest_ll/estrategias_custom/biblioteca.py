"""La biblioteca de estrategias a medida, en disco: `medida/` (fuera de git).

Por estrategia, `medida/estrategias/<id>/`:

- `ficha.json`: su estado, sus versiones (cada una con su definición validada, su huella, su autor
  y su nota) y las huellas de las versiones que se han probado sobre el pasado. Se reescribe
  entera, de forma atómica (`fetch.atomic_write`): quien la lea ve la de antes o la de después.
- `pruebas/<n>.json`: cada prueba sobre el pasado, numeradas; se guardan las últimas `MAX_PRUEBAS`.

**Estado** (docs/panel-v4-real.md §2): `borrador` (escrita y validada) → `probada` (su última
versión se probó sobre el pasado) → `ficticio` → `real`. Los dos últimos los marcan los bots al
desplegarla (`marcar_estado`). Una versión nueva que opera distinto vuelve a `borrador`.

Guardar la misma definición otra vez no crea una versión. Cambiar solo el nombre o la explicación
crea una versión con la misma huella, que no cuenta como otra versión probada.

La escriben el panel y el conector MCP (otro proceso, el que lanza `claude`): cada escritura es
atómica, y entre los dos no se pisan porque mientras Claude trabaja el panel espera su respuesta.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import threading
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.errors import InvestLLError
from invest_ll.estrategias_custom.formato import Estrategia, a_json, huella, misma, validar
from invest_ll.estrategias_custom.prueba import (
    aviso_sobreajuste,
    resultado_a_json,
    resultado_de_json,
)
from invest_ll.fetch.atomic_write import replace_atomically

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from invest_ll.estrategias_custom.prueba import Resultado

EstadoEstrategia = Literal["borrador", "probada", "ficticio", "real"]
Autor = Literal["claude", "marcos"]

CARPETA: Final = Path("medida")
"""Relativa al directorio de trabajo, como `bots/` y las demás carpetas de datos del panel."""
ESTRATEGIAS: Final = "estrategias"
FICHA: Final = "ficha.json"
PRUEBAS: Final = "pruebas"
MAX_PRUEBAS: Final = 30
CARPETA_BOTS: Final = Path("bots")
_ORDEN: Final[dict[str, int]] = {"borrador": 0, "probada": 1, "ficticio": 2, "real": 3}
_ID: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_PRUEBA: Final = re.compile(r"^(\d{6})\.json$")


class EstrategiaNoEncontradaError(InvestLLError):
    """No hay ninguna estrategia con ese id."""


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def nuevo_id(nombre: str) -> str:
    """'Cruce de medias en Bitcoin' -> 'cruce-de-medias-en-bitcoin-3f9a1c'."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")[:40].strip("-")
    return f"{base or 'estrategia'}-{secrets.token_hex(3)}"


def id_valido(estrategia_id: str) -> bool:
    """Solo minúsculas, cifras y guiones: un id nunca sale de `medida/`."""
    return bool(_ID.match(estrategia_id))


@dataclass(frozen=True, slots=True)
class Version:
    version: int
    at: datetime
    huella: str
    nota: str
    autor: Autor
    definicion: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Ficha:
    id: str
    estado: EstadoEstrategia
    creada: datetime
    actualizada: datetime
    versiones: tuple[Version, ...]
    probadas: tuple[str, ...]
    """Huellas de las versiones probadas sobre el pasado, en el orden en que se probaron."""

    @property
    def ultima(self) -> Version:
        return self.versiones[-1]

    @property
    def estrategia(self) -> Estrategia:
        return validar(self.ultima.definicion)

    @property
    def autor(self) -> Autor:
        return self.ultima.autor


def _ficha_a_json(f: Ficha) -> dict[str, Any]:
    return {
        "id": f.id,
        "estado": f.estado,
        "creada": f.creada.isoformat(),
        "actualizada": f.actualizada.isoformat(),
        "probadas": list(f.probadas),
        "versiones": [
            {
                "version": v.version,
                "at": v.at.isoformat(),
                "huella": v.huella,
                "nota": v.nota,
                "autor": v.autor,
                "definicion": v.definicion,
            }
            for v in f.versiones
        ],
    }


def _autor(texto: object) -> Autor:
    return "claude" if texto == "claude" else "marcos"


def _estado(texto: object) -> EstadoEstrategia:
    if texto in ("probada", "ficticio", "real"):
        return cast("EstadoEstrategia", texto)
    return "borrador"


def _ficha_de_json(d: dict[str, Any]) -> Ficha:
    versiones = tuple(
        Version(
            version=int(v["version"]),
            at=datetime.fromisoformat(str(v["at"])),
            huella=str(v["huella"]),
            nota=str(v.get("nota", "")),
            autor=_autor(v.get("autor")),
            definicion=cast("dict[str, Any]", v["definicion"]),
        )
        for v in cast("list[dict[str, Any]]", d["versiones"])
    )
    return Ficha(
        id=str(d["id"]),
        estado=_estado(d.get("estado")),
        creada=datetime.fromisoformat(str(d["creada"])),
        actualizada=datetime.fromisoformat(str(d["actualizada"])),
        versiones=versiones,
        probadas=tuple(str(h) for h in cast("list[object]", d.get("probadas", []))),
    )


def _escribir(destino: Path, datos: dict[str, Any]) -> None:
    texto = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
    destino.parent.mkdir(parents=True, exist_ok=True)
    replace_atomically(destino, lambda tmp: tmp.write_text(texto, encoding="utf-8", newline="\n"))


class Biblioteca:
    """Las estrategias a medida bajo `raiz`."""

    def __init__(self, raiz: Path = CARPETA, *, reloj: Callable[[], datetime] = ahora_utc) -> None:
        self.raiz = raiz
        self._reloj = reloj
        self._cerrojo = threading.RLock()

    def ahora(self) -> datetime:
        return self._reloj()

    # -- Leer --------------------------------------------------------------------------------------

    def carpeta(self, estrategia_id: str) -> Path:
        if not id_valido(estrategia_id):
            raise EstrategiaNoEncontradaError(f"No hay ninguna estrategia «{estrategia_id}».")
        return self.raiz / ESTRATEGIAS / estrategia_id

    def ids(self) -> list[str]:
        base = self.raiz / ESTRATEGIAS
        if not base.is_dir():
            return []
        return sorted(c.name for c in base.iterdir() if id_valido(c.name) and (c / FICHA).is_file())

    def existe(self, estrategia_id: str) -> bool:
        return id_valido(estrategia_id) and (self.carpeta(estrategia_id) / FICHA).is_file()

    def ficha(self, estrategia_id: str) -> Ficha:
        ruta = self.carpeta(estrategia_id) / FICHA
        try:
            texto = ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise EstrategiaNoEncontradaError(
                f"No hay ninguna estrategia «{estrategia_id}»."
            ) from None
        return _ficha_de_json(cast("dict[str, Any]", json.loads(texto)))

    def fichas(self) -> list[Ficha]:
        """Todas, la cambiada más recientemente primero. Una ilegible no impide ver las demás."""
        fichas: list[Ficha] = []
        for estrategia_id in self.ids():
            try:
                fichas.append(self.ficha(estrategia_id))
            except (ValueError, KeyError, TypeError, OSError):
                continue
        return sorted(fichas, key=lambda f: f.actualizada, reverse=True)

    def definicion(self, estrategia_id: str, version: int | None = None) -> dict[str, Any]:
        """La definición (la última versión, o la pedida) para el motor de bots."""
        f = self.ficha(estrategia_id)
        if version is None:
            return f.ultima.definicion
        for v in f.versiones:
            if v.version == version:
                return v.definicion
        raise EstrategiaNoEncontradaError(
            f"La estrategia «{estrategia_id}» no tiene versión {version}."
        )

    def pruebas(self, estrategia_id: str) -> list[Resultado]:
        """Las pruebas guardadas, la más reciente primero."""
        carpeta = self.carpeta(estrategia_id) / PRUEBAS
        if not carpeta.is_dir():
            return []
        resultados: list[Resultado] = []
        for ruta in sorted(self._ficheros_de_pruebas(carpeta), reverse=True):
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                resultados.append(resultado_de_json(cast("dict[str, Any]", datos)))
            except (ValueError, KeyError, TypeError, OSError):
                continue
        return resultados

    def ultima_prueba(self, estrategia_id: str) -> Resultado | None:
        pruebas = self.pruebas(estrategia_id)
        return pruebas[0] if pruebas else None

    # -- Escribir ----------------------------------------------------------------------------------

    def guardar(
        self,
        definicion: object,
        *,
        autor: Autor,
        nota: str = "",
        estrategia_id: str | None = None,
    ) -> Ficha:
        """Valida y guarda: una estrategia nueva o, con `estrategia_id`, una versión nueva de esa.
        `EstrategiaInvalidaError` en llano si no vale. Si es idéntica a la última, no cambia nada."""
        estrategia = validar(definicion)
        ahora = self.ahora()
        nueva = Version(
            version=1,
            at=ahora,
            huella=huella(estrategia),
            nota=nota.strip()[:500],
            autor=autor,
            definicion=a_json(estrategia),
        )
        with self._cerrojo:
            if estrategia_id is None:
                ficha = Ficha(
                    id=nuevo_id(estrategia.nombre),
                    estado="borrador",
                    creada=ahora,
                    actualizada=ahora,
                    versiones=(nueva,),
                    probadas=(),
                )
            else:
                previa = self.ficha(estrategia_id)
                if misma(validar(previa.ultima.definicion), estrategia):
                    return previa
                nueva = replace(nueva, version=previa.ultima.version + 1)
                if nueva.huella == previa.ultima.huella:
                    estado = previa.estado  # solo cambia el nombre o la explicación
                elif nueva.huella in previa.probadas:
                    estado = "probada"
                else:
                    estado = "borrador"
                ficha = replace(
                    previa,
                    estado=estado,
                    actualizada=ahora,
                    versiones=(*previa.versiones, nueva),
                )
            _escribir(self.carpeta(ficha.id) / FICHA, _ficha_a_json(ficha))
            return ficha

    def borrar(self, estrategia_id: str) -> None:
        with self._cerrojo:
            carpeta = self.carpeta(estrategia_id)
            if not (carpeta / FICHA).is_file():
                raise EstrategiaNoEncontradaError(f"No hay ninguna estrategia «{estrategia_id}».")
            shutil.rmtree(carpeta)

    def registrar_prueba(self, estrategia_id: str, resultado: Resultado) -> Resultado:
        """Guarda la prueba y la devuelve con su versión, cuántas versiones distintas de la
        estrategia se han probado ya (contando esta) y el aviso de sobreajuste si toca."""
        with self._cerrojo:
            ficha = self.ficha(estrategia_id)
            version = next(
                (v.version for v in reversed(ficha.versiones) if v.huella == resultado.huella), 0
            )
            probadas = ficha.probadas
            if resultado.huella not in probadas:
                probadas = (*probadas, resultado.huella)
            estado = ficha.estado
            if estado == "borrador" and resultado.huella == ficha.ultima.huella:
                estado = "probada"
            resultado = replace(
                resultado,
                version=version,
                versiones_probadas=len(probadas),
                aviso_sobreajuste=aviso_sobreajuste(len(probadas)),
            )
            carpeta = self.carpeta(estrategia_id) / PRUEBAS
            existentes = sorted(self._ficheros_de_pruebas(carpeta)) if carpeta.is_dir() else []
            hallado = _PRUEBA.match(existentes[-1].name) if existentes else None
            numero = int(hallado.group(1)) + 1 if hallado else 1
            _escribir(carpeta / f"{numero:06d}.json", resultado_a_json(resultado))
            for viejo in existentes[: max(0, len(existentes) + 1 - MAX_PRUEBAS)]:
                viejo.unlink(missing_ok=True)
            ficha = replace(ficha, estado=estado, probadas=probadas, actualizada=self.ahora())
            _escribir(self.carpeta(estrategia_id) / FICHA, _ficha_a_json(ficha))
            return resultado

    def marcar_estado(self, estrategia_id: str, estado: EstadoEstrategia) -> Ficha:
        """Para los bots: `ficticio` al desplegarla en un bot ficticio, `real` al activarla con
        dinero real. Solo sube (una estrategia que llegó a real no vuelve a "en ficticio")."""
        with self._cerrojo:
            ficha = self.ficha(estrategia_id)
            if _ORDEN[estado] <= _ORDEN[ficha.estado]:
                return ficha
            ficha = replace(ficha, estado=estado, actualizada=self.ahora())
            _escribir(self.carpeta(estrategia_id) / FICHA, _ficha_a_json(ficha))
            return ficha

    @staticmethod
    def _ficheros_de_pruebas(carpeta: Path) -> list[Path]:
        return [r for r in carpeta.iterdir() if _PRUEBA.match(r.name)]


# -- Para el motor de bots -------------------------------------------------------------------------


def marcar_estado(estrategia_id: str, estado: EstadoEstrategia, raiz: Path = CARPETA) -> None:
    """Lo llaman los bots: `ficticio` al desplegar un bot ficticio con esta estrategia, `real` al
    activarlo con dinero real."""
    Biblioteca(raiz).marcar_estado(estrategia_id, estado)


def definicion(
    estrategia_id: str, version: int | None = None, raiz: Path = CARPETA
) -> dict[str, Any]:
    """La definición validada que el motor de bots pasa a `interprete.decidir`."""
    return Biblioteca(raiz).definicion(estrategia_id, version)


def bots_que_usan(estrategia_id: str, raiz_bots: Path = CARPETA_BOTS) -> list[str]:
    """Los ids de los bots cuya definición (`bots/<id>/definicion.json`) nombra esta estrategia,
    en `estrategia` o en `parametros.estrategia`. Se lee el JSON tal cual: no depende de cómo
    cargue sus definiciones el motor de bots."""
    if not raiz_bots.is_dir():
        return []
    usan: list[str] = []
    for carpeta in sorted(raiz_bots.iterdir()):
        ruta = carpeta / "definicion.json"
        if not ruta.is_file():
            continue
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(datos, dict):
            continue
        d = cast("dict[str, Any]", datos)
        parametros = d.get("parametros")
        en_parametros = (
            isinstance(parametros, dict)
            and cast("dict[str, Any]", parametros).get("estrategia") == estrategia_id
        )
        if d.get("estrategia") == estrategia_id or en_parametros:
            usan.append(str(d.get("id", carpeta.name)))
    return usan
