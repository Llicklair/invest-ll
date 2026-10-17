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
