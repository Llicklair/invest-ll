"""Que solo el propio equipo pueda hablar con el panel.

El panel escucha en 127.0.0.1, pero eso no basta: con DNS rebinding, una web abierta en el
navegador hace que su dominio resuelva a 127.0.0.1 y llama a la API como si fuera el mismo
origen. En modo real, `POST /api/ordenes` mueve dinero. La defensa es comprobar la cabecera
Host: el navegador manda el dominio del atacante, no "localhost".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .api_apoyo import Api

ORDEN = {"par": "BTC/USDT", "lado": "buy", "cantidad": "0.001", "escrito": "0.001"}


def test_un_host_ajeno_no_llega_a_ninguna_ruta(cliente: Api) -> None:
    respuesta = cliente.post("/api/ordenes", json=ORDEN, headers={"host": "atacante.example"})
    assert respuesta.status_code == 400


def test_localhost_si_llega(cliente: Api) -> None:
    """Prueba del guardián: la misma petición por su nombre local pasa el filtro de host.

    En simulación la ruta responde 403 (no hay a dónde enviar), que demuestra que se llegó a
    ella. Si el filtro rechazara también lo legítimo, el test de arriba pasaría por la razón
    equivocada.
    """
    respuesta = cliente.post("/api/ordenes", json=ORDEN, headers={"host": "localhost:8601"})
    assert respuesta.status_code == 403


# -- CSRF: otra web abierta en el navegador no puede cambiar nada ---------------------------------
# Comprobar el Host no basta: una página cualquiera puede mandar un POST «simple» (sin cuerpo, sin
# preflight) a http://localhost:8601 con el Host bueno. Lo que la delata es Origin/Sec-Fetch-Site.

PARAR_TODO = "/api/bots-real/parar-todo"


def test_otra_web_no_puede_quitar_parar_todo(cliente: Api) -> None:
    for ruta in (PARAR_TODO, "/api/bots-real/reanudar-todo", "/api/motor/arrancar"):
        r = cliente.post(ruta, headers={"origin": "https://malo.example"})
        assert r.status_code == 403, ruta
        assert r.json()["detail"].startswith("El panel solo acepta cambios hechos desde el propio")


def test_sin_origin_pero_de_otro_sitio_tampoco(cliente: Api) -> None:
    r = cliente.post(PARAR_TODO, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403


def test_el_propio_panel_la_terminal_y_el_desarrollo_si(cliente: Api) -> None:
    """Prueba del guardián: lo legítimo pasa (si no, los 403 de arriba no demostrarían nada)."""
    for cabeceras in (
        {"origin": "http://testserver", "sec-fetch-site": "same-origin"},
        {"origin": "http://localhost:3000", "sec-fetch-site": "same-site"},
        {"sec-fetch-site": "none"},
        {},
    ):
        assert cliente.post(PARAR_TODO, headers=cabeceras).status_code == 200, cabeceras


def test_leer_desde_otra_web_no_se_corta_aqui(cliente: Api) -> None:
    """Leer no cambia nada; que otra web no pueda leer la respuesta lo decide el CORS del
    navegador."""
    assert (
        cliente.get("/api/bots-real", headers={"origin": "https://malo.example"}).status_code == 200
    )


def test_cada_respuesta_lleva_las_cabeceras_de_seguridad(cliente: Api) -> None:
    for r in (
        cliente.get("/api/bots-real"),
        cliente.get("/api/no-existe"),
        cliente.post(PARAR_TODO, headers={"origin": "https://malo.example"}),
    ):
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["content-security-policy"] == "frame-ancestors 'none'"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cross-origin-resource-policy"] == "same-origin"
