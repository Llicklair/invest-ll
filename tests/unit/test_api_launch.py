"""`invest-ll-panel`: un proceso, siempre el mismo puerto, y la API aunque falte el frontend.

Se sustituyen el servidor y el navegador: lo que se prueba es qué se arranca y dónde, no uvicorn.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from invest_ll.api import datos, launch
from invest_ll.api.schemas_v2 import PasoDatos, TrabajoDatos
from invest_ll.fetch import al_dia

from ..fixtures.paneles_v2 import escribir_paneles

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
def lanzadas(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """La actualización de datos no se lanza de verdad: se apunta (con lo que recibe)."""
    apuntadas: list[object] = []

    def lanzar(al_terminar: object = None) -> None:
        apuntadas.append(al_terminar)

    monkeypatch.setattr(datos, "lanzar", lanzar)
    return apuntadas


@pytest.fixture
def arranque(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lanzadas: list[object]) -> _Arranque:
    # En un directorio vacío: sin datos que mirar, el arranque no actualiza nada.
    monkeypatch.chdir(tmp_path)
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


# -- Al arrancar, los datos viejos se actualizan solos -------------------------------------------


def test_con_datos_viejos_los_actualiza_en_segundo_plano_y_lo_dice(
    arranque: _Arranque,
    lanzadas: list[object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    escribir_paneles()  # hasta el viernes 16 de octubre
    monkeypatch.setattr(al_dia, "hoy_utc", lambda: date(2026, 10, 19))

    assert launch.main(["--no-browser"]) == 0

    assert len(lanzadas) == 1 and lanzadas[0] is not None, "y cuenta en la consola cómo acabó"
    salida = capsys.readouterr().out
    assert "no estan al dia" in salida
    assert "criptomonedas de las estrategias de binance (del 2026-10-16)" in salida
    assert "fondos" not in salida, "un lunes, los fondos del viernes están al día"
    assert "--sin-actualizar" in salida
    assert arranque.servido == [("127.0.0.1", 8601)], "y el panel arranca igualmente"


def test_sin_actualizar_no_lo_hace(
    arranque: _Arranque, lanzadas: list[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    escribir_paneles()
    monkeypatch.setattr(al_dia, "hoy_utc", lambda: date(2026, 10, 19))
    assert launch.main(["--no-browser", "--sin-actualizar"]) == 0
    assert lanzadas == []


def test_al_dia_o_sin_nada_descargado_no_lo_hace(
    arranque: _Arranque, lanzadas: list[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert launch.main(["--no-browser"]) == 0, "la primera descarga la decide quien lo usa"
    escribir_paneles()
    monkeypatch.setattr(al_dia, "hoy_utc", lambda: date(2026, 10, 17))
    assert launch.main(["--no-browser"]) == 0, "un sábado, todo hasta el viernes está al día"
    assert lanzadas == []


def test_lo_que_cuenta_al_terminar(capsys: pytest.CaptureFixture[str]) -> None:
    trabajo = TrabajoDatos(
        en_marcha=False,
        empezado=datetime(2026, 10, 19, 8, tzinfo=UTC),
        terminado=datetime(2026, 10, 19, 8, 5, tzinfo=UTC),
        pasos=[
            PasoDatos(nombre="Fondos", estado="bien", detalle="Al día hasta el 16 oct 2026."),
            PasoDatos(nombre="Criptomonedas", estado="mal", detalle="No se pudo: sin red"),
        ],
    )
    launch.contar_en_la_consola(trabajo)
    assert capsys.readouterr().out.splitlines() == [
        "Actualizacion de datos terminada:",
        "  Fondos: bien. Al día hasta el 16 oct 2026.",
        "  Criptomonedas: NO SE PUDO. No se pudo: sin red",
    ]
