"""Registro de órdenes (T070, T072).

Lo que se comprueba aquí es que se puede demostrar después qué pasó: con qué modo salió cada
orden, y cuáles no salieron como se pidieron.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import ExecutionLedger

D = Decimal
CUANDO = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def resultado(
    estado: OrderStatus = OrderStatus.FILLED,
    *,
    pedida: str = "0.001",
    ejecutada: str = "0.001",
) -> OrderResult:
    return OrderResult(
        request=OrderRequest(
            symbol="BTC/USDT", side=Side.BUY, quantity=D(pedida), requested_at=CUANDO
        ),
        status=estado,
        filled_quantity=D(ejecutada),
        fill_price=D(50000),
        executed_at=CUANDO,
        broker_reference="ref-1",
    )


class TestRegistro:
    def test_guarda_lo_pedido_y_lo_ejecutado(self, tmp_path: Path) -> None:
        """FR-030."""
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(pedida="0.002", ejecutada="0.001"), mode_name="pruebas")

        entrada = libro.entries()[0]
        assert entrada.result.request.quantity == D("0.002")
        assert entrada.result.filled_quantity == D("0.001")

    def test_guarda_el_modo_en_cada_entrada(self, tmp_path: Path) -> None:
        """No una vez por sesion: asi se puede demostrar como salio ESTA orden."""
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(), mode_name="pruebas")
        libro.record(resultado(), mode_name="REAL")

        modos = [e.mode_name for e in libro.entries()]
        assert modos == ["pruebas", "REAL"]

    def test_distingue_el_dinero_real(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(), mode_name="pruebas")
        libro.record(resultado(), mode_name="REAL")

        assert [e.was_real_money for e in libro.entries()] == [False, True]

    def test_solo_anade(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        for _ in range(3):
            libro.record(resultado(), mode_name="pruebas")
        assert len(libro.entries()) == 3

    def test_sobrevive_al_proceso(self, tmp_path: Path) -> None:
        ExecutionLedger(tmp_path).record(resultado(), mode_name="REAL")
        assert len(ExecutionLedger(tmp_path).entries()) == 1

    def test_no_pierde_precision(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(pedida="0.00012345", ejecutada="0.00012345"), mode_name="pruebas")
        assert libro.entries()[0].result.filled_quantity == D("0.00012345")


class TestLoQuePideAtencion:
    """FR-031: una diferencia se comunica, no se da por buena."""

    def test_una_ejecucion_parcial_pide_atencion(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(
            resultado(OrderStatus.PARTIAL, pedida="0.002", ejecutada="0.001"),
            mode_name="REAL",
        )
        assert len(libro.needing_attention()) == 1

    def test_un_estado_desconocido_pide_atencion(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(OrderStatus.UNKNOWN, ejecutada="0"), mode_name="REAL")
        assert len(libro.needing_attention()) == 1

    def test_lo_que_salio_exacto_no_pide_atencion(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(), mode_name="pruebas")
        assert libro.needing_attention() == []

    def test_la_salida_avisa_de_las_pendientes(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(OrderStatus.UNKNOWN, ejecutada="0"), mode_name="REAL")
        texto = libro.render()
        assert "[!]" in texto
        assert "Revisalas antes de seguir operando" in texto


class TestSalida:
    def test_marca_visiblemente_el_dinero_real(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(), mode_name="REAL")
        assert "[DINERO REAL]" in libro.render()

    def test_un_registro_vacio_lo_dice_sin_alarmar(self, tmp_path: Path) -> None:
        assert "No se ha enviado ninguna orden" in ExecutionLedger(tmp_path).render()

    def test_es_imprimible_en_consola_windows(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        for estado in OrderStatus:
            libro.record(resultado(estado), mode_name="REAL")
        libro.render().encode("cp1252")
