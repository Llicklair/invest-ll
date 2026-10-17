"""Todos los errores del panel tienen una sola forma: `{"detail": "texto en llano"}`.

El frontend enseña `detail` tal cual. Antes, los de validación de FastAPI llegaban como una lista
técnica en inglés ("Input should be 'compra', 'venta'..."), una ruta inexistente como "Not Found",
y un host ajeno como texto plano: tres formas que el frontend no sabía pintar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.api import inicio as rutas_inicio
from invest_ll.api.contrato import openapi
from invest_ll.api.errores import explicar_validacion

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from .api_apoyo import Api

INGLES = ("Field required", "Input should", "Not Found", "Method Not Allowed", "Invalid host")


def _detalle(r: httpx.Response) -> str:
    cuerpo = r.json()
    assert set(cuerpo) == {"detail"}, f"otra forma de error: {cuerpo}"
    detalle = cuerpo["detail"]
    assert isinstance(detalle, str)
    assert not any(palabra in detalle for palabra in INGLES), detalle
    return detalle


class TestValidacionEnLlano:
    def test_que_campo_y_que_le_pasa(self, cliente: Api) -> None:
        r = cliente.post(
            "/api/cartera/movimientos",
            json={"tipo": "deposito", "fecha": "ayer", "cantidad": "mucho"},
        )
        assert r.status_code == 422
        assert _detalle(r) == (
            "Revisa los datos: «tipo» tiene que ser uno de estos: 'compra', 'venta', 'ingreso' o "
            "'retirada'; «fecha» tiene que ser una fecha (AAAA-MM-DD); «cantidad» tiene que ser "
            "un número."
        )

    def test_lo_que_falta(self, cliente: Api) -> None:
        r = cliente.post("/api/plan/hoy/x/hecho", json={"precio": "1", "fecha": "2026-10-17"})
        assert r.status_code == 422
        assert _detalle(r) == "Revisa los datos: falta «cantidad»."

    def test_un_limite(self, cliente: Api) -> None:
        r = cliente.post(
            "/api/plan/hoy/x/hecho", json={"cantidad": "0", "precio": "1", "fecha": "2026-10-17"}
        )
        assert _detalle(r) == "Revisa los datos: «cantidad» tiene que ser mayor que 0."

    def test_dentro_de_una_lista(self, cliente: Api) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "reparto": [{"estrategia": "btc-freno", "porcentaje": 0}],
            "inicial": "1",
            "mensual": "1",
            "desde_anio": 2020,
        }
        r = cliente.post("/api/estrategias/simular", json=peticion)
        assert r.status_code == 422
        assert _detalle(r) == (
            "Revisa los datos: «porcentaje» del elemento 1 de «reparto» tiene que ser 1 o más."
        )

    def test_una_lista_vacia(self, cliente: Api) -> None:
        peticion: dict[str, object] = {
            "estrategias": [],
            "inicial": "1",
            "mensual": "1",
            "desde_anio": 2020,
        }
        r = cliente.post("/api/estrategias/simular", json=peticion)
        assert _detalle(r) == "Revisa los datos: «estrategias» necesita al menos 1 elemento."

    def test_un_parametro_de_la_direccion(self, cliente: Api) -> None:
        r = cliente.get("/api/mercado/serie", params={"symbol": "GLD", "tramo": "10a"})
        assert r.status_code == 422
        assert _detalle(r).startswith(
            "Revisa los datos: el parámetro «tramo» tiene que ser uno de estos: '3m', '1a'"
        )

    def test_un_json_roto(self, cliente: Api) -> None:
        r = cliente.post_crudo("/api/cartera/movimientos", '{"tipo": "compra",')
        assert r.status_code == 422
        assert _detalle(r) == "Revisa los datos: el cuerpo de la petición no es un JSON válido."


class TestLoDemasTambien:
    def test_una_direccion_que_no_existe(self, cliente: Api) -> None:
        r = cliente.get("/api/no-existe")
        assert r.status_code == 404
        assert _detalle(r) == "No existe esa dirección en el panel."

    def test_una_operacion_que_la_direccion_no_admite(self, cliente: Api) -> None:
        r = cliente.delete("/api/inicio")
        assert r.status_code == 405
        assert _detalle(r) == "Esa dirección del panel no admite esta operación."
        assert r.headers["allow"] == "GET"

    def test_los_del_dominio_siguen_igual(self, cliente: Api) -> None:
        r = cliente.delete("/api/plan")
        assert r.status_code == 404
        assert _detalle(r) == "no hay ningún plan guardado"

    def test_un_host_ajeno(self, cliente: Api) -> None:
        r = cliente.post("/api/ordenes", json={}, headers={"host": "atacante.example"})
        assert r.status_code == 400
        assert "solo atiende a este mismo equipo" in _detalle(r)

    def test_un_fallo_del_programa_es_un_500_con_la_misma_forma(
        self, cliente_como_el_navegador: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def revienta() -> None:
            raise RuntimeError("un fallo cualquiera")

        monkeypatch.setattr(rutas_inicio, "modo_efectivo", revienta)
        r = cliente_como_el_navegador.get("/api/inicio")
        assert r.status_code == 500
        assert _detalle(r).startswith("Algo ha fallado dentro del panel (RuntimeError).")


def test_el_contrato_declara_los_errores_con_su_forma() -> None:
    esquema = openapi()
    assert "HTTPValidationError" not in esquema["components"]["schemas"], (
        "la lista técnica de FastAPI ya no sale por ninguna ruta"
    )
    actualizar = esquema["paths"]["/api/datos/actualizar"]["post"]["responses"]
    assert "202" in actualizar and "409" in actualizar, "una actualización ya en marcha"
    operaciones: list[dict[str, Any]] = [
        operacion for ruta in esquema["paths"].values() for operacion in ruta.values()
    ]
    assert operaciones
    for operacion in operaciones:
        for codigo in ("403", "404", "409", "422"):
            respuesta = operacion["responses"][codigo]
            assert respuesta["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/Error"
            }, (operacion["operationId"], codigo)


def test_un_error_de_un_validador_propio_y_uno_desconocido() -> None:
    assert (
        explicar_validacion(
            [
                {"type": "value_error", "loc": ("body", "x"), "msg": "Value error, no cuadra"},
                {"type": "algo_nuevo", "loc": ("body", "y"), "msg": "?"},
                {"type": "algo_nuevo", "loc": ("body", "y"), "msg": "?"},
            ]
        )
        == "Revisa los datos: «x»: no cuadra; «y» no es válido."
    )
