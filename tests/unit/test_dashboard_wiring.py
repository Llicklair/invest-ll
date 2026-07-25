"""Que las piezas del panel estén CONECTADAS, no solo definidas.

Este fichero existe por un defecto real: `pestana_seguimiento` se escribió, se commiteó con un
mensaje que decía "pestaña añadida al panel", y **nunca se llamó desde ninguna parte**. La
verificación de entonces fue comprobar que el panel respondía HTTP 200 — cosa que hacía igual,
porque una función definida y no usada no rompe nada.

Es el mismo patrón que el bug de la traducción de símbolos: una pieza que existe y no se conecta.

**Y hay una segunda lección, del propio fichero.** La primera versión de este guardián usaba una
expresión regular `pestana_\\w+\\(` para detectar llamadas — que encajaba también con
`def pestana_x(`, así que toda función definida contaba como llamada y el test pasaba SIEMPRE. Se
descubrió desconectando una pestaña a propósito y viendo que seguía en verde. Un test que no puede
fallar es peor que no tener test: da la seguridad sin darla.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "src" / "invest_ll" / "dashboard" / "app.py"
PREFIJO = "pestana_"


def _arbol() -> ast.Module:
    return ast.parse(APP.read_text(encoding="utf-8"), filename=str(APP))


def _definidas() -> set[str]:
    return {
        nodo.name
        for nodo in ast.walk(_arbol())
        if isinstance(nodo, ast.FunctionDef) and nodo.name.startswith(PREFIJO)
    }


def _llamadas_en_main() -> set[str]:
    """Las pestañas que `main()` llama de verdad.

    Mirar dentro de `main` y no en todo el fichero es lo que hace significativo el test: una
    llamada desde otra pestaña, o desde código muerto, no la haría visible al operador.
    """
    for funcion in ast.walk(_arbol()):
        if not (isinstance(funcion, ast.FunctionDef) and funcion.name == "main"):
            continue
        return {
            nodo.func.id
            for nodo in ast.walk(funcion)
            if isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Name)
            and nodo.func.id.startswith(PREFIJO)
        }
    raise AssertionError("el panel no tiene funcion main()")


def test_todas_las_pestanas_definidas_se_usan() -> None:
    """Una pestana que nadie llama es trabajo invisible para el operador."""
    huerfanas = _definidas() - _llamadas_en_main()
    assert not huerfanas, (
        f"estas pestanas estan definidas pero main() no las llama: {sorted(huerfanas)}. "
        "El panel arrancaria igual y el operador nunca las veria."
    )


def test_el_detector_distingue_definicion_de_llamada() -> None:
    """Prueba del propio guardian.

    Si el detector contara las definiciones como llamadas —el bug que tuvo la primera version—
    estos dos conjuntos saldrian iguales por construccion incluso con una pestana desconectada, y
    el test de arriba no podria fallar nunca.
    """
    definidas = _definidas()
    llamadas = _llamadas_en_main()

    assert definidas, "no se detecto ninguna pestana definida"
    assert llamadas, "no se detecto ninguna llamada desde main"

    # Se comprueba sobre un fuente sintetico: con una pestana definida y NO llamada, el detector
    # tiene que verlo. Si no, el guardian es decorativo.
    sintetico = ast.parse(
        "def pestana_a() -> None: ...\n"
        "def pestana_huerfana() -> None: ...\n"
        "def main() -> None:\n"
        "    pestana_a()\n"
    )
    definidas_s = {
        n.name
        for n in ast.walk(sintetico)
        if isinstance(n, ast.FunctionDef) and n.name.startswith(PREFIJO)
    }
    llamadas_s = {
        n.func.id
        for f in ast.walk(sintetico)
        if isinstance(f, ast.FunctionDef) and f.name == "main"
        for n in ast.walk(f)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert definidas_s - llamadas_s == {"pestana_huerfana"}, (
        "el detector no ve una pestana huerfana ni en un caso construido a mano"
    )


def test_las_etiquetas_cuadran_con_las_variables() -> None:
    """`st.tabs` debe recibir tantas etiquetas como variables se desempaquetan.

    Un desajuste explota al abrir el panel, no en la suite. Mejor que salte aqui.
    """
    for nodo in ast.walk(_arbol()):
        if not isinstance(nodo, ast.Assign):
            continue
        llamada = nodo.value
        if not (
            isinstance(llamada, ast.Call)
            and isinstance(llamada.func, ast.Attribute)
            and llamada.func.attr == "tabs"
        ):
            continue

        destino = nodo.targets[0]
        variables = len(destino.elts) if isinstance(destino, ast.Tuple) else 1

        assert llamada.args, "st.tabs() sin etiquetas"
        etiquetas = llamada.args[0]
        assert isinstance(etiquetas, ast.List), "las etiquetas deben ser una lista literal"
        assert len(etiquetas.elts) == variables, (
            f"st.tabs recibe {len(etiquetas.elts)} etiquetas pero se desempaqueta en "
            f"{variables} variables"
        )
        return

    raise AssertionError("no se encontro ninguna llamada a st.tabs en el panel")
