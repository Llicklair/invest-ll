"""Triggers de retirada: proponen, nunca disparan.

El test que da sentido al módulo es `test_el_modulo_no_sabe_enviar_ordenes`: la distancia entre
"propone" y "dispara" es exactamente un import, y se vigila por AST. Todo lo demás —que las
reglas midan bien, que la pausa pause— importa menos que eso.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.errors import InvestLLError
from invest_ll.portfolio.models import OpenPosition
from invest_ll.portfolio.triggers import (
    Trigger,
    TriggerRule,
    TriggerStore,
    evaluate_trigger,
    liquidation_commands,
)

D = Decimal
AHORA = datetime(2026, 7, 26, tzinfo=UTC)


def trigger(rule: TriggerRule, umbral: str = "0.15", simbolo: str = "GLD") -> Trigger:
    return Trigger(
        trigger_id="trg-1", symbol=simbolo, rule=rule, threshold=D(umbral), armed_at=AHORA
    )


def posicion(simbolo: str = "GLD", cantidad: str = "10", coste: str = "1000") -> OpenPosition:
    return OpenPosition(
        symbol=simbolo,
        quantity=D(cantidad),
        cost=D(coste),
        opened_at=AHORA,
        invested_total=D(coste),
        proceeds_total=D(0),
    )


class TestPerdidaDesdeEntrada:
    def test_salta_cuando_la_perdida_cruza_el_umbral(self) -> None:
        # Coste 1000, valor ahora 10x80=800: -20% con umbral del 15%.
        disparo = evaluate_trigger(
            trigger(TriggerRule.LOSS_FROM_ENTRY), posicion(), last_price=D(80), peak=None
        )
        assert disparo is not None
        assert disparo.measured == D("-0.2")
        assert disparo.quantity == D(10), "propone salir de TODA la posicion"

    def test_no_salta_por_debajo_del_umbral(self) -> None:
        assert (
            evaluate_trigger(
                trigger(TriggerRule.LOSS_FROM_ENTRY), posicion(), last_price=D(95), peak=None
            )
            is None
        )

    def test_ir_ganando_no_salta_nunca(self) -> None:
        assert (
            evaluate_trigger(
                trigger(TriggerRule.LOSS_FROM_ENTRY), posicion(), last_price=D(200), peak=None
            )
            is None
        )


class TestCaidaDesdeMaximo:
    def test_salta_cuando_el_activo_cae_desde_su_pico(self) -> None:
        disparo = evaluate_trigger(
            trigger(TriggerRule.DROP_FROM_PEAK), posicion(), last_price=D(80), peak=D(100)
        )
        assert disparo is not None
        assert disparo.measured == D("-0.2")

    def test_sin_pico_no_evalua(self) -> None:
        assert (
            evaluate_trigger(
                trigger(TriggerRule.DROP_FROM_PEAK), posicion(), last_price=D(80), peak=None
            )
            is None
        )


class TestSinDatosNoSeInventa:
    def test_sin_posicion_no_salta(self) -> None:
        assert (
            evaluate_trigger(
                trigger(TriggerRule.LOSS_FROM_ENTRY), None, last_price=D(80), peak=None
            )
            is None
        )

    def test_sin_precio_no_salta(self) -> None:
        assert (
            evaluate_trigger(
                trigger(TriggerRule.LOSS_FROM_ENTRY), posicion(), last_price=None, peak=None
            )
            is None
        )


class TestElAlmacen:
    def test_armar_listar_desarmar(self, tmp_path: Path) -> None:
        store = TriggerStore(tmp_path)
        store.arm(trigger(TriggerRule.LOSS_FROM_ENTRY))

        assert len(store.triggers()) == 1
        assert store.disarm("trg-1") is True
        assert store.triggers() == []

    def test_desarmar_lo_inexistente_no_es_un_exito(self, tmp_path: Path) -> None:
        assert TriggerStore(tmp_path).disarm("trg-99") is False

    def test_los_ids_no_se_repiten(self, tmp_path: Path) -> None:
        store = TriggerStore(tmp_path)
        store.arm(trigger(TriggerRule.LOSS_FROM_ENTRY))
        assert store.next_id() == "trg-2"

    def test_un_umbral_imposible_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="fraccion"):
            trigger(TriggerRule.LOSS_FROM_ENTRY, umbral="15")


class TestLaPausa:
    def test_pausar_y_reanudar(self, tmp_path: Path) -> None:
        store = TriggerStore(tmp_path)
        assert store.halted() is None

        store.halt(reason="mercado revuelto, no quiero proponer nada", at=AHORA)
        assert store.halted() is not None
        assert "revuelto" in (store.halted() or "")

        assert store.resume() is True
        assert store.halted() is None
        assert store.resume() is False, "reanudar sin pausa no es un exito"

    def test_la_fecha_de_la_pausa_se_lee_en_castellano(self, tmp_path: Path) -> None:
        """El panel la enseña tal cual: "(desde 2026-10-17)" no es como se escribe una fecha."""
        store = TriggerStore(tmp_path)
        store.halt(reason="pensarlo", at=datetime(2026, 10, 17, 9, 30, tzinfo=UTC))
        assert store.halted() == "pensarlo (desde el 17 oct 2026)"

    def test_una_pausa_sin_motivo_se_rechaza(self, tmp_path: Path) -> None:
        with pytest.raises(InvestLLError, match="motivo"):
            TriggerStore(tmp_path).halt(reason="   ", at=AHORA)


class TestLiquidarloTodo:
    def test_una_orden_por_posicion_con_su_cantidad_exacta(self) -> None:
        comandos = liquidation_commands(
            [posicion("GLD", "10"), posicion("TLT", "3.5", coste="300")]
        )
        assert len(comandos) == 2
        assert "--symbol GLD --side sell --quantity 10" in comandos[0]
        assert "--symbol TLT --side sell --quantity 3.5" in comandos[1]

    def test_todas_pasan_por_execute(self) -> None:
        """La liquidacion propone comandos de invest-ll-execute: no hay otra puerta al dinero."""
        for comando in liquidation_commands([posicion()]):
            assert comando.startswith("uv run invest-ll-execute ")

    def test_sin_posiciones_no_hay_comandos(self) -> None:
        assert liquidation_commands([]) == []


class TestProponerNoEsDisparar:
    def test_el_modulo_no_sabe_enviar_ordenes(self) -> None:
        """EL test de este fichero.

        `triggers.py` no puede importar nada de `live/` (broker, ccxt, modo real): la distancia
        entre "propone la orden" y "la envia" es exactamente un import, y si alguien lo anade,
        esto se pone rojo antes de que ninguna orden salga sola.
        """
        arbol = ast.parse(Path("src/invest_ll/portfolio/triggers.py").read_text(encoding="utf-8"))
        importados: set[str] = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                importados.update(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module)

        prohibidos = [m for m in importados if ".live" in m or m.startswith("ccxt")]
        assert not prohibidos, (
            f"triggers.py importa {prohibidos}: los triggers PROPONEN, nunca ejecutan"
        )

    def test_el_guardian_detecta_un_import_real(self) -> None:
        arbol = ast.parse("from invest_ll.live.broker import Broker\n")
        modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
        assert any(m and ".live" in m for m in modulos)

    def test_lo_propuesto_es_texto_no_una_llamada(self) -> None:
        """El disparo produce un comando PARA LEER, con la confirmacion dentro del mensaje."""
        disparo = evaluate_trigger(
            trigger(TriggerRule.LOSS_FROM_ENTRY), posicion(), last_price=D(80), peak=None
        )
        assert disparo is not None
        texto = disparo.render()
        assert "invest-ll-execute" in texto
        assert "Nada se ha enviado" in texto
