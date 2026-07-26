"""La comisión que cobró el exchange viaja con la orden.

Sin ella, cualquier cosa que se construya encima del registro —una cartera, un P&L, un informe—
empieza a mentir por omisión: el exchange se queda su parte igual, solo que en tus cifras no
aparece. El proveedor la devuelve en cada respuesta; no guardarla era tirarla.

Es opcional a propósito (`None`), y `None` **no significa cero**: significa «no se sabe». Las
órdenes registradas antes de esto se siguen leyendo, y quien las use tiene que poder distinguir
«no cobraron nada» de «no lo apuntamos».
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import ExecutionLedger

D = Decimal
AHORA = datetime(2026, 7, 26, 18, 40, tzinfo=UTC)


def peticion() -> OrderRequest:
    return OrderRequest(
        symbol="BTC/USDT", side=Side.BUY, quantity=D("0.001"), requested_at=AHORA
    )


def resultado(comision: Decimal | None) -> OrderResult:
    return OrderResult(
        request=peticion(),
        status=OrderStatus.FILLED,
        filled_quantity=D("0.001"),
        fill_price=D("64703.52"),
        executed_at=AHORA,
        broker_reference="20684423",
        commission=comision,
    )


class TestLaComisionSobreviveAlDisco:
    def test_se_guarda_y_se_recupera(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(D("0.0647")), mode_name="pruebas")

        recuperada = libro.entries()[0].result.commission
        assert recuperada == D("0.0647")

    def test_sin_comision_se_lee_como_desconocida_no_como_cero(self, tmp_path: Path) -> None:
        libro = ExecutionLedger(tmp_path)
        libro.record(resultado(None), mode_name="pruebas")

        assert libro.entries()[0].result.commission is None

    def test_una_entrada_antigua_sin_el_campo_se_sigue_leyendo(self, tmp_path: Path) -> None:
        """Compatibilidad: el registro solo anade, y lo ya escrito no se reescribe."""
        antigua = (
            '{"recorded_at": "2026-07-26T18:41:04+00:00", "mode": "pruebas", '
            '"symbol": "BTC/USDT", "side": "buy", "requested_quantity": "0.001", '
            '"requested_at": "2026-07-26T18:40:30+00:00", "status": "filled", '
            '"filled_quantity": "0.001", "fill_price": "64703.52", '
            '"executed_at": "2026-07-26T18:41:04+00:00", "broker_reference": "20684423"}'
        )
        (tmp_path / "orders.jsonl").write_text(antigua + "\n", encoding="utf-8")

        entradas = ExecutionLedger(tmp_path).entries()

        assert len(entradas) == 1
        assert entradas[0].result.commission is None
        assert entradas[0].result.fill_price == D("64703.52")

    def test_una_comision_negativa_no_se_acepta(self) -> None:
        """Seria un ingreso disfrazado, igual que en las actividades de cartera."""
        import pytest

        with pytest.raises(ValueError, match="comision"):
            resultado(D("-1"))
