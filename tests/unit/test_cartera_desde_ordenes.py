"""De las órdenes enviadas a la cartera, sin teclear nada dos veces.

Mandas una orden, queda en `ledger/orders.jsonl`… y tu cartera sigue vacía. Copiar a mano lo que
el sistema ya sabe es justo donde se cuelan los errores, y donde las métricas empiezan a mentir.

Este puente lo automatiza, con tres reglas que no son negociables:

1. **Las pruebas no entran en la cartera real.** Los precios de la red de pruebas no son los del
   mercado, así que mezclar su P&L con dinero de verdad corrompería el historial.
2. **Nada se importa dos veces.** Reimportar duplicaría posiciones que nunca existieron.
3. **Lo que no se ejecutó no es una compra.** Rechazadas, parciales sin precio y las de estado
   desconocido se quedan fuera, y se cuentan aparte para que no desaparezcan en silencio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import LedgerEntry
from invest_ll.portfolio.from_orders import (
    MODOS_FICTICIOS,
    actividades_desde_ordenes,
    orden_a_actividad,
)
from invest_ll.portfolio.models import ActivityType

D = Decimal
AHORA = datetime(2026, 7, 26, 18, 41, tzinfo=UTC)


def entrada(
    *,
    modo: str = "REAL",
    estado: OrderStatus = OrderStatus.FILLED,
    lado: Side = Side.BUY,
    cantidad: str = "0.001",
    ejecutada: str | None = None,
    precio: str | None = "64703.52",
    comision: str | None = "0.0647",
    referencia: str = "20684423",
    momento: datetime = AHORA,
) -> LedgerEntry:
    peticion = OrderRequest(
        symbol="BTC/USDT", side=lado, quantity=D(cantidad), requested_at=momento
    )
    return LedgerEntry(
        result=OrderResult(
            request=peticion,
            status=estado,
            filled_quantity=D(ejecutada if ejecutada is not None else cantidad),
            fill_price=D(precio) if precio is not None else None,
            executed_at=momento,
            broker_reference=referencia,
            commission=D(comision) if comision is not None else None,
        ),
        mode_name=modo,
        recorded_at=momento,
    )


class TestUnaOrdenSeConvierteEnMovimiento:
    def test_una_compra_ejecutada_es_una_compra(self) -> None:
        a = orden_a_actividad(entrada())
        assert a is not None
        assert a.type is ActivityType.BUY
        assert a.symbol == "BTC/USDT"
        assert a.quantity == D("0.001")
        assert a.unit_price == D("64703.52")
        assert a.fee == D("0.0647")

    def test_una_venta_es_una_venta(self) -> None:
        a = orden_a_actividad(entrada(lado=Side.SELL))
        assert a is not None
        assert a.type is ActivityType.SELL

    def test_se_registra_lo_ejecutado_no_lo_pedido(self) -> None:
        """Una parcial que anotara la cantidad pedida inventaria una posicion mas grande."""
        a = orden_a_actividad(
            entrada(estado=OrderStatus.PARTIAL, cantidad="0.010", ejecutada="0.004")
        )
        assert a is not None
        assert a.quantity == D("0.004")

    def test_deja_constancia_de_que_viene_del_registro(self) -> None:
        a = orden_a_actividad(entrada())
        assert a is not None
        assert "ledger" in a.source

    def test_sin_comision_conocida_no_se_inventa_un_cero(self) -> None:
        """Un cero inventado se lee como 'no cobraron', y nadie vuelve a mirarlo."""
        assert orden_a_actividad(entrada(comision=None)) is None


class TestLoQueNoEntra:
    def test_una_rechazada_no_es_una_compra(self) -> None:
        assert orden_a_actividad(entrada(estado=OrderStatus.REJECTED, ejecutada="0")) is None

    def test_una_de_estado_desconocido_tampoco(self) -> None:
        """No se sabe si se ejecuto: darla por buena inventaria una posicion."""
        assert orden_a_actividad(entrada(estado=OrderStatus.UNKNOWN, ejecutada="0")) is None

    def test_sin_precio_de_ejecucion_no_hay_movimiento(self) -> None:
        assert orden_a_actividad(entrada(precio=None)) is None

    def test_cantidad_ejecutada_cero_no_es_movimiento(self) -> None:
        assert orden_a_actividad(entrada(ejecutada="0")) is None


class TestLasPruebasNoContaminanLaCarteraReal:
    def test_por_defecto_solo_entra_el_dinero_real(self) -> None:
        resultado = actividades_desde_ordenes([entrada(modo="pruebas"), entrada(modo="REAL")])

        assert len(resultado.activities) == 1
        assert resultado.skipped_by_mode == 1

    def test_se_pueden_pedir_las_de_pruebas_a_proposito(self) -> None:
        resultado = actividades_desde_ordenes(
            [entrada(modo="pruebas")], modos=MODOS_FICTICIOS
        )
        assert len(resultado.activities) == 1

    def test_la_simulacion_nunca_entra_ni_pidiendola(self) -> None:
        """Nunca salio al exterior: no hay nada que registrar."""
        resultado = actividades_desde_ordenes(
            [entrada(modo="simulacion")], modos=MODOS_FICTICIOS
        )
        assert not resultado.activities


class TestNadaSeImportaDosVeces:
    def test_lo_ya_conocido_se_salta(self) -> None:
        una = entrada()
        primera = actividades_desde_ordenes([una])
        conocidos = {a.activity_id for a in primera.activities}

        segunda = actividades_desde_ordenes([una], conocidos=conocidos)

        assert not segunda.activities
        assert segunda.already_known == 1

    def test_dos_ordenes_distintas_del_mismo_activo_entran_las_dos(self) -> None:
        otra = entrada(referencia="20684424", momento=datetime(2026, 7, 26, 19, 0, tzinfo=UTC))
        resultado = actividades_desde_ordenes([entrada(), otra])

        assert len(resultado.activities) == 2

    def test_el_recuento_cuadra_con_lo_que_entro(self) -> None:
        resultado = actividades_desde_ordenes(
            [
                entrada(),
                entrada(modo="pruebas"),
                entrada(estado=OrderStatus.REJECTED, ejecutada="0"),
            ]
        )

        assert len(resultado.activities) == 1
        assert resultado.skipped_by_mode == 1
        assert resultado.not_executed == 1
