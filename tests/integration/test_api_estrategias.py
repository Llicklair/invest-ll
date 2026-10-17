"""La API del panel v2: el catálogo, tus números y la recomendación.

Con paneles sintéticos pequeños en el directorio del test (`tests/fixtures/paneles_v2.py`), leídos
por el mismo camino que los de verdad.
"""

from __future__ import annotations

import pytest

from ..fixtures.paneles_v2 import escribir_paneles
from .api_apoyo import Api

PRINCIPALES = [
    "bolsa-equilibrada",
    "bolsa-prudente",
    "bolsa-eeuu",
    "btc-freno",
    "cripto-cesta-freno",
    "btc-mantener",
]


@pytest.fixture
def con_datos(cliente: Api) -> Api:
    escribir_paneles()
    return cliente


class TestCatalogo:
    def test_sin_datos_no_disponible_y_dice_como_traerlos(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/estrategias").json()

        por_clave = {e["clave"]: e for e in cuerpo["estrategias"]}
        assert [c for c in por_clave if not por_clave[c]["laboratorio"]] == PRINCIPALES
        btc = por_clave["btc-freno"]
        assert btc["disponible"] is False
        assert btc["historico"] is None
        assert "uv run invest-ll-quant download" in btc["motivo"]
        assert "--etf" in por_clave["bolsa-equilibrada"]["motivo"]
        assert "pasado no es una promesa" in cuerpo["nota"]
        assert "10.000 en la moneda de cada estrategia (dólares o USDT)" in cuerpo["nota"]

    def test_con_datos_las_cifras_salen_de_ejecutarlas(self, con_datos: Api) -> None:
        cuerpo = con_datos.get("/api/estrategias").json()

        for e in cuerpo["estrategias"]:
            assert e["disponible"] is True, e["motivo"]
            h = e["historico"]
            assert h["valor_final"] > 0
            assert h["peor_caida"] <= 0
            assert h["desde"] < h["hasta"]
            assert h["cambios_al_anio"] >= 0
        por_clave = {e["clave"]: e for e in cuerpo["estrategias"]}
        equilibrada = por_clave["bolsa-equilibrada"]["historico"]
        assert equilibrada["operaciones_al_anio"] > 0, "el motor reequilibra por deriva"
        assert equilibrada["cambios_al_anio"] == 0, "pero tú no tienes que hacer nada"
        assert por_clave["cripto-rotacion"]["retirada"] is True
        assert por_clave["cripto-rotacion"]["laboratorio"] is True
        assert por_clave["btc-freno"]["ejecucion"] == "binance"
        assert por_clave["bolsa-eeuu"]["riesgo_texto"] == "Movida"
        assert por_clave["bolsa-eeuu"]["activos"] == ["Bolsa de EE.UU."]

    def test_evidencia_de_prueba_real_si_hay_registros(self, con_datos: Api) -> None:
        from pathlib import Path

        Path("paper").mkdir()
        Path("paper/btc-trend.jsonl").write_text(
            '{"data_date": "2026-10-15", "strategy": "BTC trend 30d", "weights": {}, '
            '"closes": {}}\n',
            encoding="utf-8",
        )
        por_clave = {e["clave"]: e for e in con_datos.get("/api/estrategias").json()["estrategias"]}

        assert por_clave["btc-freno"]["evidencia"] == {
            "tipo": "prueba_real",
            "desde": "2026-10-15",
            "texto": "En prueba real desde el 15 oct 2026",
        }
        assert por_clave["bolsa-eeuu"]["evidencia"]["texto"] == "Probada sobre el pasado"


class TestSimular:
    def test_tres_estrategias_con_tus_numeros(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["bolsa-equilibrada", "btc-freno", "btc-mantener"],
            "inicial": "1000",
            "mensual": "100",
            "desde_anio": 2025,
        }
        cuerpo = con_datos.post("/api/estrategias/simular", json=peticion).json()

        assert [r["clave"] for r in cuerpo["resultados"]] == peticion["estrategias"]
        for r in cuerpo["resultados"]:
            assert r["desde"].startswith("2025-01")
            assert r["aportado"] == pytest.approx(1000 + 100 * 22)  # ene-2025 a oct-2026
            assert r["puntos"][0]["aportado"] == pytest.approx(1100)
            assert r["peor_momento_aportado"] > 0
            assert r["aviso"] is None
        assert "aproximación" in cuerpo["nota"]

    def test_si_los_datos_empiezan_despues_avisa(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "inicial": "1000",
            "mensual": "0",
            "desde_anio": 2018,
        }
        (r,) = con_datos.post("/api/estrategias/simular", json=peticion).json()["resultados"]
        assert r["desde"] == "2024-01-01"
        assert "1 ene 2024" in r["aviso"]

    def test_un_anio_sin_datos_422_en_llano(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "inicial": "1",
            "mensual": "1",
            "desde_anio": 2030,
        }
        r = con_datos.post("/api/estrategias/simular", json=peticion)
        assert r.status_code == 422
        assert r.json()["detail"] == (
            "Bitcoin con freno: no hay datos desde 2030; sus datos llegan hasta el 16 oct 2026."
        )

    def test_clave_desconocida_404(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["no-existe"],
            "inicial": "1",
            "mensual": "1",
            "desde_anio": 2020,
        }
        assert con_datos.post("/api/estrategias/simular", json=peticion).status_code == 404

    def test_sin_dinero_422(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "inicial": "0",
            "mensual": "0",
            "desde_anio": 2020,
        }
        r = con_datos.post("/api/estrategias/simular", json=peticion)
        assert r.status_code == 422

    def test_sin_reparto_no_hay_combinado(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "inicial": "1",
            "mensual": "1",
            "desde_anio": 2025,
        }
        assert con_datos.post("/api/estrategias/simular", json=peticion).json()["combinado"] is None

    def test_tu_reparto_entero_como_una_cuenta(self, con_datos: Api) -> None:
        peticion = {
            "estrategias": ["bolsa-equilibrada", "btc-freno"],
            "reparto": [
                {"estrategia": "bolsa-equilibrada", "porcentaje": 90},
                {"estrategia": "btc-freno", "porcentaje": 10},
            ],
            "inicial": "1000",
            "mensual": "100",
            "desde_anio": 2025,
        }
        cuerpo = con_datos.post("/api/estrategias/simular", json=peticion).json()

        equilibrada, freno = cuerpo["resultados"]
        combinado = cuerpo["combinado"]
        assert combinado["clave"] == "reparto"
        assert combinado["nombre"] == "Tu reparto (90 % Equilibrada, 10 % Bitcoin con freno)"
        assert combinado["aportado"] == pytest.approx(equilibrada["aportado"])
        assert combinado["puntos"][0]["aportado"] == pytest.approx(1100)
        # Cada parte en su estrategia: entre lo que habría hecho cada una con todo el dinero.
        menor, mayor = sorted((equilibrada["valor_final"], freno["valor_final"]))
        assert menor <= combinado["valor_final"] <= mayor
        assert combinado["peor_caida"] <= 0
        assert combinado["peor_momento_aportado"] > 0
        # La misma muestra semanal: sus fechas son las de la estrategia de cripto (todos los días).
        fechas = [p["fecha"] for p in combinado["puntos"]]
        assert fechas[:-1] == [p["fecha"] for p in freno["puntos"]][:-1]
        assert combinado["aviso"] is None

    @pytest.mark.parametrize(
        ("reparto", "estado", "texto"),
        [
            ([("bolsa-equilibrada", 90), ("btc-freno", 5)], 422, "suma 95 %"),
            ([("btc-freno", 50), ("btc-freno", 50)], 422, "dos veces"),
            ([("no-existe", 100)], 404, "no-existe"),
        ],
    )
    def test_un_reparto_que_no_vale(
        self, con_datos: Api, reparto: list[tuple[str, int]], estado: int, texto: str
    ) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "reparto": [{"estrategia": e, "porcentaje": p} for e, p in reparto],
            "inicial": "1000",
            "mensual": "0",
            "desde_anio": 2025,
        }
        r = con_datos.post("/api/estrategias/simular", json=peticion)
        assert r.status_code == estado
        assert texto in r.json()["detail"]

    def test_sin_datos_422_con_el_comando(self, cliente: Api) -> None:
        peticion = {
            "estrategias": ["btc-freno"],
            "inicial": "1",
            "mensual": "1",
            "desde_anio": 2020,
        }
        r = cliente.post("/api/estrategias/simular", json=peticion)
        assert r.status_code == 422
        assert "invest-ll-quant download" in r.json()["detail"]


class TestRecomendar:
    def test_laura(self, cliente: Api) -> None:
        perfil = {
            "inicial": "6000",
            "mensual": "200",
            "horizonte": "mas-10",
            "ante_caida": "esperar",
            "cripto": "si",
        }
        cuerpo = cliente.post("/api/estrategias/recomendar", json=perfil).json()

        assert cuerpo["no_invertir"] is False
        assert [(p["estrategia"], p["porcentaje"]) for p in cuerpo["partes"]] == [
            ("bolsa-equilibrada", 90),
            ("btc-freno", 10),
        ]
        assert cuerpo["partes"][0]["inicial"] == "5400.00"
        assert cuerpo["partes"][1]["mensual"] == "20.00"
        assert any("más de 10 años" in f for f in cuerpo["por_que"])

    def test_menos_de_dos_anios(self, cliente: Api) -> None:
        perfil = {
            "inicial": "6000",
            "mensual": "0",
            "horizonte": "menos-2",
            "ante_caida": "comprar",
            "cripto": "si",
        }
        cuerpo = cliente.post("/api/estrategias/recomendar", json=perfil).json()
        assert cuerpo["no_invertir"] is True
        assert [p["estrategia"] for p in cuerpo["partes"]] == ["bolsa-prudente"]
