"""El catálogo: lo que se le dice al usuario y que sus cifras salen del motor, no de la mano."""

from __future__ import annotations

import itertools
import threading
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pytest

from invest_ll.estrategias import historico, objetivo
from invest_ll.estrategias.catalogo import FICHAS, ficha, principales
from invest_ll.estrategias.historico import CAPITAL, cifras, ejecutar
from invest_ll.quant.etf_study import load_etf_panel
from invest_ll.quant.panel import load_binance_universe

from ..fixtures.paneles_v2 import BOLSA, CRIPTO, escribir_paneles
from ..quant.builders import panel_from_closes

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.estrategias.catalogo import Ficha
    from invest_ll.quant.panel import Panel


def _ficha(clave: str) -> Ficha:
    encontrada = ficha(clave)
    assert encontrada is not None
    return encontrada


def test_seis_en_el_camino_principal_y_el_resto_en_laboratorio() -> None:
    assert [f.clave for f in principales()] == [
        "bolsa-equilibrada",
        "bolsa-prudente",
        "bolsa-eeuu",
        "btc-freno",
        "cripto-cesta-freno",
        "btc-mantener",
    ]
    laboratorio = {f.clave for f in FICHAS if f.laboratorio}
    assert {
        "cripto-prerregistrada",
        "cripto-rotacion",
        "bolsa-igual",
        "bolsa-paridad",
    } <= laboratorio
    rotacion = _ficha("cripto-rotacion")
    assert rotacion.retirada and rotacion.laboratorio
    assert any("sesgo de supervivencia" in a for a in rotacion.avisos)


@pytest.mark.parametrize(
    ("clave", "riesgo", "ejecucion"),
    [
        ("bolsa-equilibrada", 3, "broker"),
        ("bolsa-prudente", 2, "broker"),
        ("bolsa-eeuu", 4, "broker"),
        ("btc-freno", 4, "binance"),
        ("cripto-cesta-freno", 4, "binance"),
        ("btc-mantener", 5, "binance"),
    ],
)
def test_riesgo_y_quien_lo_hace(clave: str, riesgo: int, ejecucion: str) -> None:
    f = _ficha(clave)
    assert (f.riesgo, f.ejecucion) == (riesgo, ejecucion)
    assert len(f.como_funciona) == 3


def test_avisos_obligatorios() -> None:
    cesta = _ficha("cripto-cesta-freno").avisos
    assert any("después de ver los primeros resultados" in a for a in cesta)
    assert any("impuestos" in a for a in cesta)
    assert any("casi la mitad del tiempo fuera" in a for a in _ficha("btc-freno").avisos)
    assert any("la mitad" in a for a in _ficha("bolsa-prudente").avisos)
    assert any("más del 80 %" in a for a in _ficha("btc-mantener").avisos)
    for f in FICHAS:
        if f.mercado == "bolsa":
            assert any("UCITS" in a for a in f.avisos) and any("euro-dólar" in a for a in f.avisos)
        else:
            assert any("USDT" in a for a in f.avisos)


def test_las_de_dos_partes_se_reconocen_por_mercado() -> None:
    equilibrada = _ficha("bolsa-equilibrada")
    assert equilibrada.posee("SPY") and equilibrada.posee("IEF")
    assert not equilibrada.posee("GLD") and not equilibrada.posee("BTC/USDT")
    assert _ficha("btc-freno").posee("ETH/USDT")
    assert not _ficha("btc-freno").posee("SPY")


# -- Las cifras salen de ejecutar el motor ------------------------------------------------------


@pytest.fixture
def paneles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    escribir_paneles()
    return tmp_path


def test_cada_estrategia_se_ejecuta_sobre_los_datos(paneles: Path) -> None:
    cripto = load_binance_universe(CRIPTO)
    bolsa = load_etf_panel(str(BOLSA))
    for f in FICHAS:
        recorrido = ejecutar(f, cripto if f.mercado == "cripto" else bolsa)
        c = cifras(recorrido)
        assert recorrido.valor[0] == CAPITAL
        assert c.desde == recorrido.desde
        assert c.peor_caida <= 0
        assert 0 <= c.tiempo_invertido <= 1.0 + 1e-9
        assert c.valor_final == pytest.approx(float(recorrido.valor[-1]))


def test_mantener_bitcoin_es_lo_que_hizo_bitcoin(paneles: Path) -> None:
    cripto = load_binance_universe(CRIPTO)
    recorrido = ejecutar(_ficha("btc-mantener"), cripto)
    btc = cripto.close[:, cripto.column("BTCUSDT")]
    # Compra al abrir el segundo día, con comisión y deslizamiento: casi lo mismo que BTC.
    esperado = CAPITAL * btc[-1] / btc[1]
    assert float(recorrido.valor[-1]) == pytest.approx(esperado, rel=0.01)
    assert cifras(recorrido).tiempo_invertido > 0.99


def test_la_liquidez_en_shy_no_cuenta_como_tiempo_invertido(paneles: Path) -> None:
    bolsa = load_etf_panel(str(BOLSA))
    prudente = ejecutar(_ficha("bolsa-prudente"), bolsa)
    assert float(np.max(prudente.invertido)) <= 1.0 + 1e-9
    equilibrada = cifras(ejecutar(_ficha("bolsa-equilibrada"), bolsa))
    assert equilibrada.tiempo_invertido > 0.95


def test_se_calcula_una_vez_por_version_de_los_datos(
    paneles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[str] = []
    original = historico.ejecutar

    def contar(f: Ficha, panel: Panel) -> historico.Recorrido:
        llamadas.append(f.clave)
        return original(f, panel)

    monkeypatch.setattr(historico, "ejecutar", contar)
    historico.MEMORIA.olvidar()

    historico.ejecuciones("bolsa")
    historico.ejecuciones("bolsa")
    assert sorted(llamadas) == sorted(f.clave for f in FICHAS if f.mercado == "bolsa")

    escribir_paneles(cripto=False, hasta=date(2026, 10, 15))  # datos nuevos: otra huella
    historico.ejecuciones("bolsa")
    assert len(llamadas) == 2 * sum(1 for f in FICHAS if f.mercado == "bolsa")


def test_lo_calculado_no_hace_cola_tras_otra_que_se_esta_calculando(paneles: Path) -> None:
    """Mientras la cesta de Laboratorio se calcula (el cerrojo de cripto cogido), lo que ya está
    en memoria se sirve sin esperar: si no, simular Bitcoin con freno tardaba lo que la cesta."""
    historico.MEMORIA.olvidar()
    mantener = _ficha("btc-mantener")
    historico.ejecucion(mantener)
    servido: list[historico.Ejecucion] = []

    cerrojo = historico.MEMORIA._cerrojos["cripto"]  # pyright: ignore[reportPrivateUsage]
    with cerrojo:
        hilo = threading.Thread(target=lambda: servido.append(historico.ejecucion(mantener)))
        hilo.start()
        hilo.join(timeout=5)
        a_tiempo = list(servido)  # antes de soltar el cerrojo
    hilo.join()

    assert a_tiempo, "se quedó esperando al cerrojo"
    assert a_tiempo[0].recorrido is not None


def test_sin_datos_no_disponible_con_el_comando(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    ejecuciones = historico.ejecuciones("cripto")
    assert all(e.recorrido is None for e in ejecuciones.values())
    assert all("uv run invest-ll-quant download" in (e.motivo or "") for e in ejecuciones.values())


def test_objetivo_de_hoy(paneles: Path) -> None:
    cripto = load_binance_universe(CRIPTO)
    bolsa = load_etf_panel(str(BOLSA))

    btc = objetivo.pesos_de_hoy(_ficha("btc-freno"), cripto)
    assert btc.pesos == {"BTC": pytest.approx(1.0)}, "BTC sube siempre en el panel sintético"
    assert btc.fecha == date(2026, 10, 16)

    mantener = objetivo.pesos_de_hoy(_ficha("btc-mantener"), cripto)
    otra_vez = objetivo.pesos_de_hoy(_ficha("btc-mantener"), cripto)
    assert mantener.pesos == otra_vez.pesos == {"BTC": 1.0}, "instancia nueva en cada pregunta"

    equilibrada = objetivo.pesos_de_hoy(_ficha("bolsa-equilibrada"), bolsa)
    assert equilibrada.pesos == {"SPY": pytest.approx(0.6), "IEF": pytest.approx(0.4)}

    cesta = objetivo.pesos_de_hoy(_ficha("cripto-cesta-freno"), cripto)
    assert "USDC" not in cesta.pesos, "las monedas estables no entran en el universo"
    assert sum(cesta.pesos.values()) <= 1.0 + 1e-9


def test_si_btc_cae_un_mes_el_freno_sale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    escribir_paneles(bolsa=False, btc="baja")
    cripto = load_binance_universe(CRIPTO)
    assert objetivo.pesos_de_hoy(_ficha("btc-freno"), cripto).pesos == {}


# -- Cuántas veces al año te toca hacer algo además de aportar ---------------------------------


def test_movido_cuenta_la_liquidez() -> None:
    assert historico.movido(np.array([1.0]), np.array([0.0])) == pytest.approx(1.0)
    assert historico.movido(np.array([0.5, 0.5, 0.0]), np.array([0.3, 0.5, 0.2])) == (
        pytest.approx(0.2)
    )
    assert historico.movido(np.array([0.6, 0.4]), np.array([0.6, 0.4])) == 0.0


def test_la_primera_decision_es_invertir_y_no_cuenta() -> None:
    cambios = historico.Cambios(tramos=2)
    for tramo in (0, 1):
        cambios(tramo, 0, np.array([1.0]))
    assert cambios.por_tramo == 0.0
    cambios(0, 7, np.array([0.95]))  # un retoque del 5 %: no es algo que hacer
    cambios(0, 14, np.array([0.0]))  # salir: sí
    cambios(1, 15, np.array([0.0]))
    cambios(1, 22, np.array([1.0]))  # y volver a entrar
    assert cambios.por_tramo == pytest.approx(1.5)


def test_un_reparto_fijo_no_te_pide_nada_aunque_el_motor_reequilibre(paneles: Path) -> None:
    bolsa = load_etf_panel(str(BOLSA))
    equilibrada = cifras(ejecutar(_ficha("bolsa-equilibrada"), bolsa))
    assert equilibrada.operaciones_al_anio > 0
    assert equilibrada.cambios_al_anio == 0.0
    cripto = load_binance_universe(CRIPTO)
    assert cifras(ejecutar(_ficha("btc-mantener"), cripto)).cambios_al_anio == 0.0


def _bitcoin_en_dientes_de_sierra(dias: int, fase: int) -> list[float]:
    """Sube `fase` días y baja otros tantos, una y otra vez: la tendencia de 30 días se da la
    vuelta un número de veces que se puede contar a mano."""
    precios = [100.0]
    for t in range(1, dias):
        sube = (t // fase) % 2 == 0
        precios.append(precios[-1] * (1.01 if sube else 0.99))
    return precios


def test_bitcoin_con_freno_cuenta_sus_entradas_y_salidas() -> None:
    dias = 900
    precios = _bitcoin_en_dientes_de_sierra(dias, fase=75)
    panel = panel_from_closes({"BTCUSDT": precios, "ETHUSDT": [10.0] * dias})
    recorrido = ejecutar(_ficha("btc-freno"), panel)
    c = cifras(recorrido)
    anios = (len(recorrido.valor) - 1) / recorrido.periodos_al_anio

    # Las entradas y salidas de la señal, día a día: Bitcoin vale más (o menos) que hace 30 días.
    dentro = [precios[t] / precios[t - 30] - 1 > 0 for t in range(30, dias - 1)]
    vueltas = sum(1 for a, b in itertools.pairwise(dentro) if a != b)

    assert vueltas >= 8, "el diente de sierra tiene que dar varias vueltas"
    assert c.cambios_al_anio * anios == pytest.approx(vueltas, abs=1)
    assert c.operaciones_al_anio > 3 * c.cambios_al_anio, "el motor lo hace en siete tramos"
