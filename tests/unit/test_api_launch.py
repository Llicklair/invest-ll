"""`invest-ll-panel`: un proceso, siempre el mismo puerto, y la API aunque falte el frontend.

Se sustituyen el servidor y el navegador: lo que se prueba es qué se arranca y dónde, no uvicorn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from invest_ll.api import launch

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from pathlib import Path

    from fastapi import FastAPI


class _Arranque:
    """Hace de uvicorn: apunta dónde se sirve y "arranca" en el acto."""

    def __init__(self) -> None:
        self.servido: list[tuple[str, int]] = []
        self.navegador: list[str] = []

    def servir(
        self,
        app: FastAPI,
        *,
        host: str,
        puerto: int,
        al_arrancar: Callable[[], None] | None = None,
    ) -> None:
        assert app.title == "INVEST LL"
        self.servido.append((host, puerto))
        if al_arrancar is not None:
            al_arrancar()


@pytest.fixture
def arranque(monkeypatch: pytest.MonkeyPatch) -> _Arranque:
    falso = _Arranque()
    monkeypatch.setattr(launch, "servir", falso.servir)
    monkeypatch.setattr(launch, "abrir_navegador", falso.navegador.append)
    return falso


def _con_frontend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compilado = tmp_path / "out"
    compilado.mkdir()
    (compilado / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(launch, "FRONTEND", compilado)


def test_por_defecto_8601_en_local_y_abre_el_navegador(
    arranque: _Arranque, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _con_frontend(tmp_path, monkeypatch)
    assert launch.main([]) == 0
    assert arranque.servido == [("127.0.0.1", 8601)]
    assert arranque.navegador == ["http://127.0.0.1:8601"]


def test_no_browser_no_abre_nada(
    arranque: _Arranque, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _con_frontend(tmp_path, monkeypatch)
    assert launch.main(["--no-browser", "--puerto", "8611"]) == 0
    assert arranque.servido == [("127.0.0.1", 8611)]
    assert arranque.navegador == []


def test_sin_frontend_avisa_y_arranca_la_api_igualmente(
    arranque: _Arranque,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(launch, "FRONTEND", tmp_path / "no-compilado")

    assert launch.main([]) == 0

    assert arranque.servido == [("127.0.0.1", 8601)]
    assert arranque.navegador == ["http://127.0.0.1:8601/docs"]
    assert "npm --prefix web ci && npm --prefix web run build" in capsys.readouterr().err


class _Servidor:
    def __init__(self, started: bool) -> None:
        self.started = started


def test_el_navegador_solo_se_abre_si_el_servidor_arranca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con el puerto ocupado uvicorn no arranca: no se abre una pestaña contra la nada."""
    monkeypatch.setattr(launch, "ESPERA_MAXIMA", 0.3)
    abiertas: list[str] = []

    launch.cuando_arranque(_Servidor(started=False), lambda: abiertas.append("no"))
    launch.cuando_arranque(_Servidor(started=True), lambda: abiertas.append("si"))

    assert abiertas == ["si"]
