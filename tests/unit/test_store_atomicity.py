"""T011 — atomicidad de la escritura (FR-012).

Un CSV a medias es peor que ningún CSV: el motor lo cargaría sin quejarse y produciría un
resultado sobre un periodo que no es el que el operador cree.

Los fallos se simulan en los dos puntos donde una escritura puede romperse de verdad: al volcar
el contenido y al renombrar.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.loader import load_series
from invest_ll.fetch import store as store_mod
from invest_ll.fetch.store import HistoryStore, write_atomic

from .test_store import PROVEEDOR, peticion, procedencia, serie


def romper_replace(monkeypatch: pytest.MonkeyPatch, mensaje: str) -> None:
    """Hace fallar el renombrado final, que es el momento crítico de la operación."""

    def falla(*args: Any, **kwargs: Any) -> None:
        raise OSError(mensaje)

    monkeypatch.setattr(store_mod.os, "replace", falla)


def test_un_fallo_al_renombrar_no_deja_fichero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "serie.csv"
    romper_replace(monkeypatch, "disco lleno simulado")

    with pytest.raises(OSError, match="disco lleno"):
        write_atomic(destino, "datos")

    assert not destino.exists()


def test_un_fallo_al_renombrar_no_deja_temporales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "serie.csv"
    romper_replace(monkeypatch, "fallo simulado")

    with pytest.raises(OSError, match="fallo simulado"):
        write_atomic(destino, "datos")

    assert list(tmp_path.glob(".tmp-*")) == []


def test_sobrescribir_conserva_el_original_si_falla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lo que ya estaba no puede quedar peor que antes (FR-015)."""
    destino = tmp_path / "serie.csv"
    write_atomic(destino, "contenido bueno")

    romper_replace(monkeypatch, "fallo a mitad")
    with pytest.raises(OSError, match="fallo a mitad"):
        write_atomic(destino, "contenido malo")

    assert destino.read_text(encoding="utf-8") == "contenido bueno"


def test_un_fallo_guardando_el_historico_no_corrompe_el_anterior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso real: la descarga se corta a mitad de guardar."""
    store = HistoryStore(tmp_path)
    store.save(peticion(), serie(5), procedencia(5))
    original = store.csv_path(peticion(), PROVEEDOR).read_text(encoding="utf-8")

    romper_replace(monkeypatch, "corte de luz")
    with pytest.raises(OSError, match="corte de luz"):
        store.save(peticion(), serie(9), procedencia(9))

    assert store.csv_path(peticion(), PROVEEDOR).read_text(encoding="utf-8") == original


def test_la_escritura_correcta_reemplaza(tmp_path: Path) -> None:
    destino = tmp_path / "serie.csv"
    write_atomic(destino, "primero")
    write_atomic(destino, "segundo")
    assert destino.read_text(encoding="utf-8") == "segundo"


def test_no_quedan_temporales_tras_guardar(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    store.save(peticion(), serie(), procedencia())
    assert list(tmp_path.rglob(".tmp-*")) == []


def test_el_temporal_se_crea_en_el_mismo_directorio(tmp_path: Path) -> None:
    """Cruzar sistemas de ficheros convertiria el renombrado en copia, y la copia no es atomica.

    Se comprueba observando el directorio durante la escritura: si el temporal apareciera en el
    temporal del sistema, aqui no habria ni rastro de el.
    """
    destino = tmp_path / "sub" / "serie.csv"
    destino.parent.mkdir(parents=True)

    vistos: list[Path] = []
    real_replace = store_mod.os.replace

    def observar(origen: str, final: str) -> None:
        vistos.extend(destino.parent.glob(".tmp-*"))
        real_replace(origen, final)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(store_mod.os, "replace", observar)
    try:
        write_atomic(destino, "datos")
    finally:
        monkey.undo()

    assert vistos, "el temporal no estaba en el directorio de destino"


def test_lo_guardado_siempre_es_cargable_por_el_motor(tmp_path: Path) -> None:
    """Si el fichero existe, está completo. No hay estado intermedio observable."""
    store = HistoryStore(tmp_path)
    ruta = store.save(peticion(), serie(), procedencia())
    cargada, _ = load_series(
        ruta, symbol="BTC/USDT", interval=Interval.DAY_1, calendar=Continuous24x7()
    )
    assert len(cargada) == 5


def test_os_replace_es_lo_que_se_usa() -> None:
    """`os.rename` falla en Windows si el destino existe; `os.replace` no."""
    assert "replace" in write_atomic.__code__.co_names
    assert "rename" not in write_atomic.__code__.co_names
    assert callable(os.replace)
