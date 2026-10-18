"""Las copias de seguridad (`invest_ll.copias`): qué entra, qué no, cuántas se guardan, cuándo toca
la siguiente y que extraer una nunca escriba fuera de su carpeta."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from invest_ll import copias

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

AHORA = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    raiz = tmp_path / "proyecto"
    (raiz / "ledger").mkdir(parents=True)
    (raiz / "ledger" / "ordenes.jsonl").write_text('{"orden": 1}\n', encoding="utf-8")
    (raiz / "bots" / "rejilla-1").mkdir(parents=True)
    (raiz / "bots" / "rejilla-1" / "estado.json").write_text("{}", encoding="utf-8")
    (raiz / "bots" / ".motor.lock").write_text("", encoding="utf-8")
    (raiz / "bots" / "motor.log").write_text("ruido", encoding="utf-8")
    (raiz / "config").mkdir()
    (raiz / "config" / "motor.json").write_text("{}", encoding="utf-8")
    (raiz / "data").mkdir()
    (raiz / "data" / "enorme.csv").write_text("x", encoding="utf-8")
    return raiz


def test_copia_lo_que_no_esta_en_git_y_nada_mas(proyecto: Path, tmp_path: Path) -> None:
    hecha = copias.hacer(proyecto, tmp_path / "copias", ahora=AHORA)
    assert hecha.ruta.name == "invest-ll-20261018-120000.zip"
    with zipfile.ZipFile(hecha.ruta) as z:
        assert sorted(z.namelist()) == [
            "bots/rejilla-1/estado.json",
            "config/motor.json",
            "ledger/ordenes.jsonl",
        ]
        assert json.loads(z.read("ledger/ordenes.jsonl")) == {"orden": 1}
    assert not list((tmp_path / "copias").glob("*.tmp")), "no queda ninguna a medias"


def test_guarda_las_mas_recientes(proyecto: Path, tmp_path: Path) -> None:
    destino = tmp_path / "copias"
    for dia in range(copias.GUARDAR + 3):
        copias.hacer(proyecto, destino, ahora=AHORA + timedelta(days=dia))
    hechas = copias.copias(destino)
    assert len(hechas) == copias.GUARDAR
    assert hechas[0].at == AHORA + timedelta(days=copias.GUARDAR + 2)


def test_toca_una_al_dia(proyecto: Path, tmp_path: Path) -> None:
    destino = tmp_path / "copias"
    assert copias.toca(destino, ahora=AHORA)
    copias.hacer(proyecto, destino, ahora=AHORA)
    assert not copias.toca(destino, ahora=AHORA + timedelta(hours=23))
    assert copias.toca(destino, ahora=AHORA + timedelta(hours=24))


def test_extraer_va_a_una_carpeta_nueva_sin_pisar_nada(proyecto: Path, tmp_path: Path) -> None:
    hecha = copias.hacer(proyecto, tmp_path / "copias", ahora=AHORA)
    carpeta = copias.extraer(hecha.ruta)
    assert (carpeta / "ledger" / "ordenes.jsonl").is_file()
    with pytest.raises(FileExistsError):
        copias.extraer(hecha.ruta)


def test_un_zip_con_rutas_hacia_fuera_no_se_extrae(tmp_path: Path) -> None:
    malo = tmp_path / "copias" / "invest-ll-20261018-120000.zip"
    malo.parent.mkdir()
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("../../fuera.txt", "x")
    with pytest.raises(ValueError, match="fuera de su carpeta"):
        copias.extraer(malo)
    assert not (tmp_path / "fuera.txt").exists()


def test_la_terminal_hace_y_lista(
    proyecto: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(proyecto)
    monkeypatch.setenv("INVEST_LL_COPIAS", str(tmp_path / "copias"))
    assert copias.main([]) == 0
    assert "Copia hecha:" in capsys.readouterr().out
    assert copias.main(["--lista", "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert len(datos["data"]["copias"]) == 1
