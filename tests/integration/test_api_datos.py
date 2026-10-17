"""`/api/datos`: de cuándo son los datos del panel y una actualización de todo en segundo plano.

Los comandos se sustituyen (`datos.ejecutar`): la suite corre sin red. El falso hace lo que haría
el de verdad con los ficheros —reescribe los paneles con un día más— para que se vea que después
de actualizar todo se lee y se calcula otra vez.
"""

from __future__ import annotations

import sys
import threading
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.api import datos
from invest_ll.fetch import al_dia

from ..fixtures.paneles_v2 import escribir_paneles
from .api_apoyo import guardar, subida

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from .api_apoyo import Api

LUNES = date(2026, 10, 19)
NUEVO = date(2026, 10, 18)
"""El día hasta el que "descargan" los comandos falsos."""


class Comandos:
    """Hace de `invest-ll-fetch` e `invest-ll-quant download`: apunta y reescribe los paneles."""

    def __init__(self) -> None:
        self.lanzados: list[list[str]] = []
        self.falla: set[str] = set()
        self.puerta = threading.Event()
        self.puerta.set()

    def __call__(self, argumentos: list[str], *, timeout: int) -> tuple[bool, str]:
        assert timeout > 0
        self.puerta.wait(10)
        self.lanzados.append(argumentos)
        if "--etf" in argumentos:
            if "fondos" in self.falla:
                return False, "Traceback...\nyfinance: demasiadas peticiones, prueba luego"
            escribir_paneles(cripto=False, hasta=NUEVO)
        elif argumentos[-1] == "download":
            escribir_paneles(bolsa=False, hasta=NUEVO)
        return True, "ok"


@pytest.fixture
def comandos(monkeypatch: pytest.MonkeyPatch) -> Iterator[Comandos]:
    falsos = Comandos()
    monkeypatch.setattr(datos, "ejecutar", falsos)
    monkeypatch.setattr(al_dia, "hoy_utc", lambda: LUNES)
    datos.ACTUAL.trabajo = None
    yield falsos
    falsos.puerta.set()
    datos.esperar(30)
    datos.ACTUAL.trabajo, datos.ACTUAL.hilo = None, None


def _por_clave(cuerpo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["clave"]: f for f in cuerpo["fuentes"]}


class TestDeCuandoSon:
    def test_sin_nada_descargado(self, cliente: Api, comandos: Comandos) -> None:
        cuerpo = cliente.get("/api/datos").json()

        assert [f["clave"] for f in cuerpo["fuentes"]] == ["historicos", "fondos", "cripto"]
        assert all(f["hasta"] is None and f["dias"] is None for f in cuerpo["fuentes"])
        assert cuerpo["al_dia"] is False
        assert "los fondos (faltan)" in cuerpo["aviso"]
        assert cuerpo["trabajo"] is None
        assert comandos.lanzados == [], "mirar no descarga nada"

    def test_un_lunes_el_viernes_de_bolsa_esta_al_dia_y_el_de_cripto_no(
        self, cliente: Api, comandos: Comandos
    ) -> None:
        escribir_paneles()  # hasta el viernes 16
        guardar("GLD", subida(30), hasta=date(2026, 10, 16))

        fuentes = _por_clave(cliente.get("/api/datos").json())

        assert fuentes["fondos"]["hasta"] == "2026-10-16"
        assert fuentes["fondos"]["dias"] == 3
        assert fuentes["fondos"]["al_dia"] is True
        assert fuentes["historicos"]["al_dia"] is True
        assert fuentes["cripto"]["al_dia"] is False, "la cripto cotiza el fin de semana"

    def test_de_los_historicos_manda_el_mas_atrasado(
        self, cliente: Api, comandos: Comandos
    ) -> None:
        guardar("GLD", subida(30), hasta=date(2026, 10, 16))
        guardar("BTC/USDT", subida(30), proveedor="ccxt-binance", hasta=date(2026, 10, 15))

        cuerpo = cliente.get("/api/datos").json()

        historicos = _por_clave(cuerpo)["historicos"]
        assert (historicos["hasta"], historicos["al_dia"]) == ("2026-10-15", False)
        assert "los precios de bolsa y cripto (son del 15 oct 2026)" in cuerpo["aviso"]


class TestActualizar:
    def test_todo_paso_a_paso_y_con_el_python_que_ya_corre(
        self, cliente: Api, comandos: Comandos
    ) -> None:
        escribir_paneles()
        guardar("GLD", subida(30), hasta=date(2026, 10, 16))
        guardar("TLT", subida(30), hasta=date(2026, 10, 16), procedencia=False)
        comandos.puerta.clear()

        r = cliente.post("/api/datos/actualizar")

        assert r.status_code == 202
        trabajo = r.json()["trabajo"]
        assert trabajo["en_marcha"] is True and trabajo["terminado"] is None
        assert [p["nombre"] for p in trabajo["pasos"]] == [
            "Precios de bolsa y cripto",
            "Fondos de las estrategias de bolsa",
            "Criptomonedas de las estrategias de Binance",
        ]
        assert "Se están actualizando ahora" in r.json()["aviso"]

        otra = cliente.post("/api/datos/actualizar")
        assert otra.status_code == 409
        assert otra.json() == {
            "detail": "Ya se están actualizando los datos: espera a que termine (aquí mismo se "
            "ve cómo va)."
        }
        assert cliente.post("/api/mercado/actualizar").status_code == 409, "ni la de Laboratorio"

        comandos.puerta.set()
        datos.esperar(30)

        cuerpo = cliente.get("/api/datos").json()
        assert cuerpo["trabajo"]["en_marcha"] is False
        assert cuerpo["trabajo"]["terminado"] is not None
        historicos, fondos, cripto = cuerpo["trabajo"]["pasos"]
        assert historicos["estado"] == "bien"
        assert historicos["detalle"].startswith("1 de 1 actualizados.")
        assert "TLT" in historicos["detalle"], "sin procedencia no se adivina, y se dice"
        # La bolsa no tiene sábado ni domingo: el último día de los fondos sigue siendo el viernes.
        assert (fondos["estado"], fondos["detalle"]) == ("bien", "Al día hasta el 16 oct 2026.")
        assert (cripto["estado"], cripto["detalle"]) == ("bien", "Al día hasta el 18 oct 2026.")
        assert _por_clave(cuerpo)["cripto"]["al_dia"] is True

        fetch, etf, binance = comandos.lanzados
        assert fetch[:3] == [sys.executable, "-m", "invest_ll.cli_fetch"]
        assert fetch[3] == "GLD" and fetch[fetch.index("--start") + 1] < "2026-10-16"
        assert etf == [sys.executable, "-m", "invest_ll.cli.quant", "download", "--etf"]
        assert binance == [sys.executable, "-m", "invest_ll.cli.quant", "download"]
        assert not any("uv" in parte for c in comandos.lanzados for parte in c)

    def test_un_paso_que_falla_no_para_los_demas(self, cliente: Api, comandos: Comandos) -> None:
        escribir_paneles()
        comandos.falla.add("fondos")

        cliente.post("/api/datos/actualizar")
        datos.esperar(30)

        pasos = cliente.get("/api/datos").json()["trabajo"]["pasos"]
        assert [p["estado"] for p in pasos] == ["bien", "mal", "bien"]
        assert pasos[0]["detalle"] == "No hay precios sueltos descargados: nada que actualizar."
        assert pasos[1]["detalle"] == (
            "No se pudo: Traceback... yfinance: demasiadas peticiones, prueba luego"
        )

    def test_al_terminar_el_catalogo_se_recalcula_con_los_datos_nuevos(
        self, cliente: Api, comandos: Comandos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        escribir_paneles()
        antes = {e["clave"]: e for e in cliente.get("/api/estrategias").json()["estrategias"]}
        assert antes["btc-freno"]["historico"]["hasta"] == "2026-10-16"
        invalidadas: list[bool] = []
        original = datos.invalidar_caches

        def invalidar() -> None:
            invalidadas.append(True)
            original()

        monkeypatch.setattr(datos, "invalidar_caches", invalidar)

        cliente.post("/api/datos/actualizar")
        datos.esperar(60)

        assert invalidadas == [True]
        despues = {e["clave"]: e for e in cliente.get("/api/estrategias").json()["estrategias"]}
        assert despues["btc-freno"]["historico"]["hasta"] == "2026-10-18"
        assert despues["bolsa-equilibrada"]["historico"]["hasta"] == "2026-10-16", (
            "el 17 y el 18 de octubre de 2026 son fin de semana: la bolsa no tiene más"
        )
