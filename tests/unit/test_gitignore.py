"""Que ninguna regla de `.gitignore` se trague código del proyecto.

Este fichero existe por un defecto real: la regla `portfolio/` —pensada para la carpeta de DATOS
de la raíz— no estaba anclada, así que también ignoraba `src/invest_ll/portfolio/`. El paquete
entero (ledger, triggers, reconciliación) vivió solo en un disco, ningún commit lo llevó, y un
clon limpio no arrancaba. Se perdió y hubo que reconstruirlo desde los tests.

Nada en la suite podía verlo: en el equipo donde se escribió el paquete existía, y los tests
pasaban. Solo falla en un checkout limpio, que es justo donde nadie mira.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _git(cwd: Path, *argumentos: str) -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("sin git no hay .gitignore que vigilar")
    resultado = subprocess.run(
        [git, *argumentos], cwd=cwd, capture_output=True, text=True, check=False
    )
    return resultado.stdout


def _codigo_ignorado(repo: Path) -> list[str]:
    ignorados = _git(repo, "ls-files", "--others", "--ignored", "--exclude-standard", "src")
    return [
        linea
        for linea in ignorados.splitlines()
        if linea.endswith(".py") and "__pycache__" not in linea
    ]


def test_ningun_fichero_de_codigo_esta_ignorado() -> None:
    if not (RAIZ / ".git").exists():
        pytest.skip("fuera de un repositorio git")
    codigo = _codigo_ignorado(RAIZ)
    assert not codigo, (
        f"estos ficheros de codigo los ignora git y nunca se commitearan: {codigo[:10]}. "
        "Ancla la regla culpable de .gitignore a la raiz con '/'."
    )


@pytest.mark.parametrize(
    "ruta",
    [
        "plan/plan.json",
        "config/panel.json",
        "portfolio-pruebas/activities.jsonl",
        "portfolio/activities.jsonl",
    ],
)
def test_los_datos_del_panel_no_llegan_a_git(ruta: str) -> None:
    """El plan, el modo elegido y la cartera de pruebas son datos tuyos, no código."""
    if not (RAIZ / ".git").exists():
        pytest.skip("fuera de un repositorio git")
    assert _git(RAIZ, "check-ignore", "--no-index", ruta).strip() == ruta


@pytest.mark.parametrize("ruta", ["src/invest_ll/plan/hoy.py", "src/invest_ll/plan/__init__.py"])
def test_el_paquete_plan_si_llega_a_git(ruta: str) -> None:
    """`/plan/` está anclado: no se traga `src/invest_ll/plan/`, como pasó con portfolio."""
    if not (RAIZ / ".git").exists():
        pytest.skip("fuera de un repositorio git")
    assert _git(RAIZ, "check-ignore", "--no-index", ruta).strip() == ""


@pytest.mark.parametrize(("regla", "lo_ve"), [("portfolio/", True), ("/portfolio/", False)])
def test_el_guardian_ve_la_regla_sin_anclar(tmp_path: Path, regla: str, lo_ve: bool) -> None:
    """Prueba del propio guardián, con el caso exacto que costó el paquete.

    Si el detector no viera la regla vieja, el test de arriba pasaría siempre y daría una
    seguridad que no da.
    """
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(f"{regla}\n", encoding="utf-8")
    paquete = tmp_path / "src" / "pkg" / "portfolio"
    paquete.mkdir(parents=True)
    (paquete / "models.py").write_text("X = 1\n", encoding="utf-8")

    assert bool(_codigo_ignorado(tmp_path)) is lo_ve
