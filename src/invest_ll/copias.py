"""Copias de seguridad de lo que no está en git: el registro de órdenes, los bots, las carteras, las
estrategias a medida y los ajustes.

Todo eso vive solo en este equipo (`.gitignore`), y el registro de órdenes (`ledger/`) es la prueba
de cada operación para Hacienda. Una copia es un ZIP con esas carpetas, fuera del repositorio (por
defecto en `~/INVEST LL/copias`, la carpeta del usuario; la variable `INVEST_LL_COPIAS` lo cambia):
si se borra la carpeta del proyecto, las copias siguen.

No van en Documentos a propósito: con el «acceso controlado a carpetas» de Windows Defender (la
protección contra ransomware), Python no puede escribir allí, y Windows lo dice como «no se
encuentra la ruta».

El motor de los bots hace una al arrancar si la última tiene más de un día, y otra cada día que siga
en marcha (`bots.servicio`); se guardan las `GUARDAR` más recientes. A mano:

    invest-ll-copia              # hace una ahora
    invest-ll-copia --lista      # las que hay
    invest-ll-copia --extraer RUTA_DEL_ZIP   # la saca a una carpeta nueva al lado, sin pisar nada

**Las claves no van en las copias**: viven en el Administrador de credenciales de Windows, nunca en
ficheros. Los históricos de mercado (`data/`) tampoco: se vuelven a descargar.
"""

from __future__ import annotations

import argparse
import os
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

CARPETAS: Final = (
    "ledger",
    "bots",
    "config",
    "medida",
    "portfolio",
    "portfolio-pruebas",
    "plan",
    "practica",
    "decisions",
    "attempts",
    "forecasts",
)
"""Las carpetas de datos del proyecto que no están en git (y no se pueden volver a descargar)."""
SIN_COPIAR: Final = (".lock", ".tmp", ".log")
"""Lo que es de un momento: cerrojos, ficheros a medio escribir, registros del motor."""
GUARDAR: Final = 30
CADA: Final = timedelta(days=1)
PREFIJO: Final = "invest-ll-"
FORMATO: Final = "%Y%m%d-%H%M%S"


def carpeta_de_copias() -> Path:
    elegida = os.environ.get("INVEST_LL_COPIAS")
    if elegida:
        return Path(elegida)
    return Path.home() / "INVEST LL" / "copias"


@dataclass(frozen=True, slots=True)
class Copia:
    ruta: Path
    at: datetime
    bytes: int


def copias(destino: Path | None = None) -> list[Copia]:
    """Las que hay, de la más reciente a la más antigua."""
    carpeta = destino or carpeta_de_copias()
    if not carpeta.is_dir():
        return []
    halladas: list[Copia] = []
    for ruta in carpeta.glob(f"{PREFIJO}*.zip"):
        try:
            at = datetime.strptime(ruta.stem.removeprefix(PREFIJO), FORMATO).replace(tzinfo=UTC)
        except ValueError:
            continue
        halladas.append(Copia(ruta, at, ruta.stat().st_size))
    return sorted(halladas, key=lambda c: c.at, reverse=True)


def toca(destino: Path | None = None, *, ahora: datetime | None = None) -> bool:
    """Si la última copia tiene más de `CADA` (o no hay ninguna)."""
    hechas = copias(destino)
    momento = ahora or datetime.now(UTC)
    return not hechas or momento - hechas[0].at >= CADA


def hacer(
    raiz: Path | None = None, destino: Path | None = None, *, ahora: datetime | None = None
) -> Copia:
    """Una copia ahora. Se escribe con otro nombre y se renombra al final: una copia a medias
    nunca parece buena."""
    origen = raiz or Path.cwd()
    carpeta = destino or carpeta_de_copias()
    carpeta.mkdir(parents=True, exist_ok=True)
    momento = ahora or datetime.now(UTC)
    final = carpeta / f"{PREFIJO}{momento.strftime(FORMATO)}.zip"
    temporal = final.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nombre in CARPETAS:
            base = origen / nombre
            if not base.is_dir():
                continue
            for fichero in sorted(base.rglob("*")):
                if not fichero.is_file() or fichero.name.endswith(SIN_COPIAR):
                    continue
                try:
                    z.write(fichero, fichero.relative_to(origen).as_posix())
                except OSError:
                    continue  # en uso y bloqueado (Windows): mejor una copia sin él que ninguna
    temporal.replace(final)
    podar(carpeta)
    return Copia(final, momento, final.stat().st_size)


def podar(destino: Path | None = None, guardar: int = GUARDAR) -> list[Path]:
    """Borra las más antiguas, dejando las `guardar` más recientes."""
    borradas: list[Path] = []
    for vieja in copias(destino)[guardar:]:
        vieja.ruta.unlink(missing_ok=True)
        borradas.append(vieja.ruta)
    return borradas


def extraer(zip_: Path) -> Path:
    """La saca a una carpeta nueva al lado del ZIP, sin pisar nada: para mirarla y copiar a mano lo
    que haga falta (restaurar a ciegas podría pisar datos más nuevos)."""
    destino = zip_.with_suffix("")
    if destino.exists():
        raise FileExistsError(f"Ya existe {destino}: bórrala o muévela antes.")
    with zipfile.ZipFile(zip_) as z:
        for miembro in z.namelist():
            # Nada fuera de la carpeta de destino (un ZIP manipulado con «../»).
            if not (destino / miembro).resolve().is_relative_to(destino.resolve()):
                raise ValueError(f"El ZIP tiene una ruta fuera de su carpeta: {miembro}")
        z.extractall(destino)
    return destino


def main(argv: Sequence[str] | None = None) -> int:
    from invest_ll import llano
    from invest_ll.cli.emit import add_json_flag, salida_de

    parser = argparse.ArgumentParser(
        prog="invest-ll-copia",
        description="Copias de seguridad de lo que no está en git (ledger, bots, ajustes…).",
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--lista", action="store_true", help="las copias que hay")
    grupo.add_argument("--extraer", metavar="ZIP", help="saca una copia a una carpeta nueva")
    add_json_flag(parser)
    args = parser.parse_args(argv)
    salida = salida_de(args, "copia")
    if args.lista:
        hechas = copias()
        salida.dato(
            carpeta=str(carpeta_de_copias()),
            copias=[
                {"ruta": str(c.ruta), "at": c.at.isoformat(), "bytes": c.bytes} for c in hechas
            ],
        )
        if not hechas:
            salida.linea(f"No hay copias en {carpeta_de_copias()}.")
        for c in hechas:
            cuando = c.at.astimezone().strftime("%d/%m/%Y %H:%M")
            salida.linea(f"{cuando}  {llano.numero(c.bytes / 1024, 0)} KB  {c.ruta}")
        return salida.cerrar(0)
    if args.extraer:
        try:
            carpeta = extraer(Path(args.extraer))
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            return salida.error(f"No se pudo extraer: {error}", 1)
        salida.dato(carpeta=str(carpeta))
        salida.linea(f"Extraída en {carpeta} (no se ha pisado nada del proyecto).")
        return salida.cerrar(0)
    hecha = hacer()
    salida.dato(ruta=str(hecha.ruta), bytes=hecha.bytes)
    salida.linea(f"Copia hecha: {hecha.ruta} ({llano.numero(hecha.bytes / 1024, 0)} KB).")
    return salida.cerrar(0)
