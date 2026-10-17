"""El guardián de la raíz (`tests/conftest.py`) ve lo que tiene que ver.

Un test que no puede fallar es peor que no tener test: se prueba la foto que usa contra un
directorio construido a mano, con lo que debe ver (algo nuevo, algo escrito en una carpeta que ya
estaba) y lo que no (las cachés de las herramientas).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..conftest import foto_de_la_raiz

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path


def test_ve_lo_nuevo_y_lo_escrito_en_una_carpeta_que_ya_estaba(tmp_path: Path) -> None:
    (tmp_path / "attempts").mkdir()
    (tmp_path / "README.md").write_text("hola", encoding="utf-8")
    # De una pasada anterior: si la carpeta se acaba de crear, crear algo dentro en el mismo
    # instante de reloj (NTFS cuenta de ~15 ms en ~15 ms) no le cambia la fecha.
    os.utime(tmp_path / "attempts", ns=(0, 1_000_000_000_000_000_000))
    antes = foto_de_la_raiz(tmp_path)

    (tmp_path / "attempts" / "attempts.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ledger").mkdir()
    (tmp_path / ".pytest_cache").mkdir()
    despues = foto_de_la_raiz(tmp_path)

    tocado = {n for n in despues.keys() | antes.keys() if despues.get(n) != antes.get(n)}
    assert tocado == {"attempts", "ledger"}


def test_un_fichero_sobrescrito_solo_se_ve_mirando_dentro(tmp_path: Path) -> None:
    """Sobrescribir no crea nada: la carpeta no cambia de fecha, el fichero sí."""
    fichero = tmp_path / "attempts" / "attempts.json"
    fichero.parent.mkdir()
    fichero.write_text("{}", encoding="utf-8")
    por_fuera = foto_de_la_raiz(tmp_path)
    por_dentro = foto_de_la_raiz(tmp_path, con_su_contenido=True)

    os.utime(fichero, ns=(0, fichero.stat().st_mtime_ns + 10_000_000_000))

    assert foto_de_la_raiz(tmp_path) == por_fuera
    assert foto_de_la_raiz(tmp_path, con_su_contenido=True) != por_dentro


def test_sin_cambios_la_foto_es_la_misma(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.csv").write_text("1", encoding="utf-8")
    assert foto_de_la_raiz(tmp_path) == foto_de_la_raiz(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["data"]
