"""Las rutas del panel: una sección por pestaña, en el orden en que se usan.

Cada pestaña vive en su módulo (`estado`, `mercado`, `cartera`, `simular`, `vigilar`,
`seguimiento`, `investigacion`, `chat`) y aquí solo se juntan bajo `/api`. Las rutas, sus métodos,
sus parámetros y sus modelos de respuesta son el contrato con el frontend, que genera sus tipos
desde el OpenAPI (`web/openapi.json`); `tests/unit/test_api_contrato.py` comprueba que no se
desvían, y `tests/unit/test_api_rutas_implementadas.py` que ninguna se quedó en esqueleto. Toda la
lógica vive en el motor, la cartera, las alertas, etc.; las rutas solo traducen.

Reglas que vienen del panel de Streamlit y no se pierden al cambiar de tecnología:
- **Nada de aquí envía órdenes salvo `POST /api/ordenes`**, y esa exige la cantidad tecleada
  (`escrito`) y un modo que lo permita, con la misma comprobación que `invest-ll-execute`.
- Registrar en el ledger es contabilidad, no una orden, y se dice en la respuesta.
- Los errores del dominio (`InvestLLError`, `ValueError`) salen como 422 con su texto; la pausa
  de entradas como 409; enviar sin modo que lo permita como 403; lo que no existe como 404.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api import (
    cartera,
    chat,
    conexion,
    estado,
    estrategias,
    inicio,
    investigacion,
    mercado,
    plan,
    seguimiento,
    simular,
    vigilar,
)

PESTANAS = (
    estado,
    inicio,
    estrategias,
    plan,
    conexion,
    mercado,
    cartera,
    simular,
    vigilar,
    seguimiento,
    investigacion,
    chat,
)
"""En el orden del panel: mirar -> tener -> ensayar -> vigilar -> comprobar -> investigar ->
preguntar."""

router = APIRouter(prefix="/api")
for _pestana in PESTANAS:
    router.include_router(_pestana.router)
