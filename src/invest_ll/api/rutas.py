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
  de entradas como 409; enviar sin modo que lo permita como 403; lo que no existe como 404. Todos
  con la misma forma, `{"detail": "texto en llano"}`, y declarados así en el OpenAPI
  (`errores.RESPUESTAS_DE_ERROR`).
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api import (
    bots,
    cartera,
    chat,
    claude,
    conexion,
    conexiones,
    datos,
    estado,
    estrategias,
    inicio,
    investigacion,
    medida,
    mercado,
    motor,
    operar_real,
    plan,
    practica,
    seguimiento,
    simular,
    vigilar,
    vivo,
    wallets,
)
from invest_ll.api.errores import RESPUESTAS_DE_ERROR

PESTANAS = (
    estado,
    inicio,
    estrategias,
    plan,
    conexion,
    datos,
    mercado,
    cartera,
    simular,
    vigilar,
    seguimiento,
    investigacion,
    chat,
    vivo,
    practica,
    bots,
    conexiones,
    medida,
    claude,
    operar_real,
    wallets,
    motor,
)
"""En el orden del panel: mirar -> tener -> ensayar -> vigilar -> comprobar -> investigar ->
preguntar."""

router = APIRouter(prefix="/api", responses=RESPUESTAS_DE_ERROR)
for _pestana in PESTANAS:
    router.include_router(_pestana.router)
