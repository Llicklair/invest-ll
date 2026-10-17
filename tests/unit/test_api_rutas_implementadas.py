"""Que las rutas del panel estén IMPLEMENTADAS y SERVIDAS, no solo declaradas.

Sustituye al guardián del panel de Streamlit (`test_dashboard_wiring.py`), que nació de un defecto
real: `pestana_seguimiento` se escribió, se commiteó con un mensaje que decía "pestaña añadida al
panel", y **nunca se llamó desde ninguna parte**. La verificación de entonces fue comprobar que el
panel respondía HTTP 200 — cosa que hacía igual, porque una función definida y no usada no rompe
nada.

En la API el mismo fallo tiene dos formas, y aquí se vigilan las dos:

1. **Una ruta que sigue siendo esqueleto.** El contrato se escribió antes que los cuerpos, con
   `raise NotImplementedError`. Una ruta así compila, sale en el OpenAPI y el frontend la llama;
   solo revienta al usarla. Ninguna ruta, ni nada del paquete `api`, puede lanzarlo.
2. **Una pestaña que no se monta.** Un módulo con sus rutas que nadie incluye en `rutas.PESTANAS`
   no sirve nada. Lo que sirve la aplicación tiene que ser exactamente lo que dice el contrato.

**Y la lección del guardián anterior**: su primera versión detectaba las llamadas con una
expresión regular que también encajaba con las definiciones, así que pasaba SIEMPRE. Un test que no
puede fallar es peor que no tener test. Por eso el detector se prueba a sí mismo contra fuentes
construidas a mano, con un esqueleto que tiene que ver y un texto que no debe confundir.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.routing import APIRoute

from invest_ll.api.app import crear_app
from invest_ll.api.contrato import FICHERO
from invest_ll.api.rutas import PESTANAS, router

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

API = Path(__file__).resolve().parents[2] / "src" / "invest_ll" / "api"
PENDIENTE = "pendiente de implementar"


def _rutas() -> list[tuple[str, APIRoute]]:
    """(ruta completa, ruta) de cada pestaña montada en `rutas.PESTANAS`.

    Se leen de los routers de cada pestaña y no de `app.routes`: desde FastAPI 0.14x los routers
    incluidos se montan perezosamente y `app.routes` ya no los enumera. Que la aplicación sirve
    estas mismas lo comprueba `test_lo_servido_es_exactamente_el_contrato` contra su OpenAPI.
    """
    return [
        (router.prefix + r.path, r)
        for pestana in PESTANAS
        for r in pestana.router.routes
        if isinstance(r, APIRoute)
    ]


def _operaciones(esquema: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (metodo.upper(), ruta)
        for ruta, operaciones in esquema["paths"].items()
        for metodo in operaciones
    }


def _lanza_no_implementado(arbol: ast.AST) -> bool:
    """Si en el árbol hay un `raise NotImplementedError` (con o sin argumentos).

    Se mira el nodo `Raise`, no el texto: un docstring o una cadena que mencionen la excepción no
    cuentan, y una ruta que la lanza la cuenta aunque el mensaje cambie.
    """
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Raise) or nodo.exc is None:
            continue
        lanzada = nodo.exc.func if isinstance(nodo.exc, ast.Call) else nodo.exc
        if isinstance(lanzada, ast.Name) and lanzada.id == "NotImplementedError":
            return True
    return False


def _funcion_es_esqueleto(funcion: Callable[..., object]) -> bool:
    return _lanza_no_implementado(ast.parse(textwrap.dedent(inspect.getsource(funcion))))


def test_lo_servido_es_exactamente_el_contrato() -> None:
    """Ni una operación del contrato sin servir (pestaña sin montar) ni una servida de más."""
    prometidas = _operaciones(json.loads(FICHERO.read_text(encoding="utf-8")))
    de_las_pestanas = {(metodo, ruta) for ruta, r in _rutas() for metodo in r.methods or ()}
    servidas = _operaciones(crear_app(frontend=None).openapi())

    assert prometidas, "el contrato no tiene ninguna operacion: el test pasaria por vacio"
    assert prometidas - de_las_pestanas == set(), (
        "operaciones del contrato sin pestana que las sirva"
    )
    assert de_las_pestanas - prometidas == set(), "rutas de las pestanas que el contrato no recoge"
    assert servidas == prometidas, "la aplicacion no monta exactamente las rutas del contrato"


def test_ninguna_ruta_sigue_siendo_esqueleto() -> None:
    rutas = _rutas()
    assert rutas, "no se encontro ninguna ruta: el test pasaria por vacio"
    esqueletos = sorted(
        f"{metodo} {ruta}"
        for ruta, r in rutas
        if _funcion_es_esqueleto(r.endpoint)
        for metodo in r.methods or ()
    )
    assert not esqueletos, (
        f"estas rutas siguen lanzando NotImplementedError: {esqueletos}. El frontend las llama "
        "y revientan al usarlas."
    )


def test_nada_del_paquete_api_lanza_no_implementado() -> None:
    """Cubre lo que el test de arriba no ve: una ruta que delega en un ayudante sin hacer."""
    ficheros = sorted(API.glob("*.py"))
    assert ficheros, f"no se encontro el paquete de la API en {API}"
    culpables = [
        f.name
        for f in ficheros
        if _lanza_no_implementado(ast.parse(f.read_text(encoding="utf-8"), filename=str(f)))
    ]
    assert not culpables, f"NotImplementedError en {culpables}"


def _esqueleto_de_ejemplo() -> None:
    """Como estaban las rutas del contrato antes de implementarlas."""
    raise NotImplementedError(PENDIENTE)


def _implementada_de_ejemplo() -> str:
    """Menciona NotImplementedError en el docstring y en una cadena: no debe contar."""
    return "raise NotImplementedError"


def test_el_detector_distingue_esqueleto_de_implementacion() -> None:
    """Prueba del propio guardián: si no ve un esqueleto construido a mano, es decorativo."""
    assert _funcion_es_esqueleto(_esqueleto_de_ejemplo)
    assert not _funcion_es_esqueleto(_implementada_de_ejemplo)

    sintetico = ast.parse(
        "def con_mensaje():\n"
        "    raise NotImplementedError('pendiente')\n"
        "def sin_mensaje():\n"
        "    raise NotImplementedError\n"
        "def otra_excepcion():\n"
        "    raise ValueError('no')\n"
        "def re_lanza():\n"
        "    try:\n"
        "        pass\n"
        "    except KeyError:\n"
        "        raise\n"
    )
    vistas = {
        f.name: _lanza_no_implementado(f) for f in sintetico.body if isinstance(f, ast.FunctionDef)
    }
    assert vistas == {
        "con_mensaje": True,
        "sin_mensaje": True,
        "otra_excepcion": False,
        "re_lanza": False,
    }
