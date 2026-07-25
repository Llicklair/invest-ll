"""El ledger de cartera y las posiciones derivadas.

El test que da sentido al módulo es `test_vender_todo_convierte_la_posicion_en_un_hecho`: al
llegar la cantidad a 0, el P&L deja de ser una valoración y pasa a ser un hecho que ya no cambia.
Esa distinción —no realizado vs realizado— es lo que responde "¿qué retiré y cómo salió?".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.portfolio.csv_import import CsvFormatError, parse_broker_csv
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.models import (
    Activity,
    ActivityType,
    LedgerInconsistencyError,
)
from invest_ll.portfolio.store import ActivityStore, DuplicateActivityError

D = Decimal
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def dia(n: int) -> datetime:
    return T0 + timedelta(days=n)


def compra(simbolo: str, cantidad: str, precio: str, *, fee: str = "0", en: int = 0) -> Activity:
    return Activity(
        timestamp=dia(en),
        type=ActivityType.BUY,
        symbol=simbolo,
        quantity=D(cantidad),
        unit_price=D(precio),
        fee=D(fee),
    )


def venta(simbolo: str, cantidad: str, precio: str, *, fee: str = "0", en: int = 0) -> Activity:
    return Activity(
        timestamp=dia(en),
        type=ActivityType.SELL,
        symbol=simbolo,
        quantity=D(cantidad),
        unit_price=D(precio),
        fee=D(fee),
    )


def deposito(importe: str, *, en: int = 0) -> Activity:
    return Activity(
        timestamp=dia(en),
        type=ActivityType.DEPOSIT,
        symbol=None,
        quantity=D(importe),
        unit_price=D(1),
    )


class TestPosicionesAbiertas:
    def test_una_compra_abre_una_posicion(self) -> None:
        cartera = derive_portfolio([deposito("2000"), compra("GLD", "10", "180", fee="2", en=1)])

        assert len(cartera.open_positions) == 1
        p = cartera.open_positions[0]
        assert p.symbol == "GLD"
        assert p.quantity == D(10)
        assert p.cost == D(1802), "el coste incluye la comision: es lo que de verdad pagaste"
        assert p.avg_cost == D("180.2")

    def test_dos_compras_promedian_el_coste(self) -> None:
        cartera = derive_portfolio(
            [compra("GLD", "10", "100", en=1), compra("GLD", "10", "200", en=2)]
        )
        assert cartera.open_positions[0].avg_cost == D(150)

    def test_una_venta_parcial_mantiene_el_coste_medio(self) -> None:
        cartera = derive_portfolio(
            [compra("GLD", "10", "100", en=1), venta("GLD", "4", "120", en=2)]
        )
        p = cartera.open_positions[0]
        assert p.quantity == D(6)
        assert p.avg_cost == D(100), "vender no cambia lo que pagaste por lo que queda"

    def test_el_pnl_no_realizado_es_una_valoracion(self) -> None:
        cartera = derive_portfolio([compra("GLD", "10", "100", en=1)])
        p = cartera.open_positions[0]
        assert p.unrealized_at(D(130)) == D(300)
        assert p.unrealized_at(D(90)) == D(-100)


class TestPosicionesCerradas:
    def test_vender_todo_convierte_la_posicion_en_un_hecho(self) -> None:
        """EL test de este fichero: cantidad a 0 => P&L realizado, que ya no cambia."""
        cartera = derive_portfolio(
            [compra("GLD", "10", "100", fee="5", en=1), venta("GLD", "10", "120", fee="5", en=30)]
        )

        assert cartera.open_positions == ()
        assert len(cartera.closed_trades) == 1
        t = cartera.closed_trades[0]
        assert t.invested_total == D(1005)
        assert t.proceeds_total == D(1195)
        assert t.realized_pnl == D(190), "1200 brutos menos 10 de comisiones"
        assert t.holding_days == 29

    def test_recomprar_despues_abre_un_episodio_nuevo(self) -> None:
        """Cerrar y volver a entrar no resucita la posicion anterior: son dos historias."""
        cartera = derive_portfolio(
            [
                compra("GLD", "10", "100", en=1),
                venta("GLD", "10", "120", en=10),
                compra("GLD", "5", "200", en=20),
            ]
        )
        assert len(cartera.closed_trades) == 1
        assert len(cartera.open_positions) == 1
        p = cartera.open_positions[0]
        assert p.avg_cost == D(200), "el episodio nuevo no hereda costes del cerrado"
        assert p.opened_at == dia(20)

    def test_una_perdida_realizada_sale_negativa(self) -> None:
        cartera = derive_portfolio(
            [compra("XLE", "10", "100", en=1), venta("XLE", "10", "70", en=5)]
        )
        assert cartera.closed_trades[0].realized_pnl == D(-300)
        assert cartera.realized_pnl == D(-300)


class TestElLedgerNoMiente:
    def test_vender_lo_que_no_se_tiene_falla(self) -> None:
        """Una cantidad negativa seria un ledger incompleto con aspecto de cartera valida."""
        with pytest.raises(LedgerInconsistencyError, match="solo registra 10"):
            derive_portfolio([compra("GLD", "10", "100", en=1), venta("GLD", "11", "100", en=2)])

    def test_vender_sin_haber_comprado_falla(self) -> None:
        with pytest.raises(LedgerInconsistencyError, match="solo registra 0"):
            derive_portfolio([venta("GLD", "1", "100", en=1)])

    def test_el_orden_lo_pone_la_fecha_no_la_escritura(self) -> None:
        """Un CSV importado tarde no puede romper la historia: se ordena por cuando ocurrio."""
        cartera = derive_portfolio(
            [venta("GLD", "10", "120", en=10), compra("GLD", "10", "100", en=1)]
        )
        assert len(cartera.closed_trades) == 1


class TestEfectivo:
    def test_el_efectivo_se_deriva_de_los_movimientos(self) -> None:
        cartera = derive_portfolio(
            [
                deposito("5000"),
                compra("GLD", "10", "100", fee="10", en=1),
                venta("GLD", "10", "120", fee="10", en=2),
            ]
        )
        assert cartera.cash == D(5000) - D(1010) + D(1190)
        assert cartera.total_deposited == D(5000)

    def test_comprar_sin_depositos_avisa_pero_no_rompe(self) -> None:
        """Obligar a registrar depositos antes que compras seria ceremonia; avisar es informar."""
        cartera = derive_portfolio([compra("GLD", "10", "100", en=1)])
        assert cartera.cash == D(-1000)
        assert any("depositos" in aviso for aviso in cartera.warnings)
        assert len(cartera.open_positions) == 1, "las posiciones siguen siendo fiables"


class TestValidacionDeActividades:
    def test_efectivo_con_simbolo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="no lleva simbolo"):
            Activity(
                timestamp=T0,
                type=ActivityType.DEPOSIT,
                symbol="GLD",
                quantity=D(100),
                unit_price=D(1),
            )

    def test_compra_sin_simbolo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="necesita simbolo"):
            Activity(
                timestamp=T0, type=ActivityType.BUY, symbol=None, quantity=D(1), unit_price=D(1)
            )

    def test_fecha_sin_zona_horaria_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            Activity(
                timestamp=datetime(2026, 1, 1),
                type=ActivityType.BUY,
                symbol="GLD",
                quantity=D(1),
                unit_price=D(1),
            )

    def test_comision_negativa_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="ingreso disfrazado"):
            compra("GLD", "1", "100", fee="-5")


class TestElAlmacen:
    def test_guarda_y_relee(self, tmp_path: Path) -> None:
        store = ActivityStore(tmp_path)
        store.append(compra("GLD", "10", "180", fee="2", en=1))

        releidas = store.activities()
        assert len(releidas) == 1
        assert releidas[0].quantity == D(10)
        assert releidas[0].fee == D(2)

    def test_un_duplicado_exacto_se_rechaza(self, tmp_path: Path) -> None:
        """Un doble-import duplicaria la posicion sin que nadie lo note."""
        store = ActivityStore(tmp_path)
        store.append(compra("GLD", "10", "180", en=1))
        with pytest.raises(DuplicateActivityError, match="dos veces"):
            store.append(compra("GLD", "10", "180", en=1))

    def test_devuelve_en_orden_temporal(self, tmp_path: Path) -> None:
        store = ActivityStore(tmp_path)
        store.append(compra("GLD", "10", "180", en=5))
        store.append(compra("TLT", "10", "90", en=1))
        assert [a.symbol for a in store.activities()] == ["TLT", "GLD"]


class TestImportCsv:
    def escribir(self, destino: Path, contenido: str) -> Path:
        destino.write_text(contenido, encoding="utf-8")
        return destino

    def test_el_formato_ghostfolio_entra(self, tmp_path: Path) -> None:
        csv_path = self.escribir(
            tmp_path / "movs.csv",
            "Date,Symbol,Type,Quantity,Unit Price,Fee,Currency,Account\n"
            "2026-01-15,gld,buy,10,180.5,1.2,EUR,broker\n"
            "2026-02-01,GLD,sell,10,190,1.2,EUR,broker\n",
        )
        resultado = parse_broker_csv(csv_path)

        assert len(resultado.activities) == 2
        primera = resultado.activities[0]
        assert primera.symbol == "GLD", "el simbolo se normaliza a mayusculas"
        assert primera.unit_price == D("180.5")
        assert primera.source == "csv:movs.csv"

    def test_lo_no_soportado_se_cuenta_no_se_calla(self, tmp_path: Path) -> None:
        """Un dividendo importado a medias inflaria el P&L; descartado en silencio, mentiria."""
        csv_path = self.escribir(
            tmp_path / "movs.csv",
            "Date,Symbol,Type,Quantity,Unit Price,Fee\n"
            "2026-01-15,GLD,buy,10,180,0\n"
            "2026-03-01,GLD,dividend,1,2.5,0\n"
            "2026-04-01,GLD,dividend,1,2.5,0\n",
        )
        resultado = parse_broker_csv(csv_path)

        assert len(resultado.activities) == 1
        assert resultado.skipped_types == {"dividend": 2}
        assert any("dividend" in a for a in resultado.warnings)

    def test_columnas_con_sinonimos(self, tmp_path: Path) -> None:
        csv_path = self.escribir(
            tmp_path / "movs.csv",
            "fecha,ticker,tipo,shares,price\n2026-01-15,GLD,buy,10,180\n",
        )
        assert len(parse_broker_csv(csv_path).activities) == 1

    def test_si_faltan_columnas_dice_cuales(self, tmp_path: Path) -> None:
        csv_path = self.escribir(tmp_path / "movs.csv", "Date,Symbol\n2026-01-15,GLD\n")
        with pytest.raises(CsvFormatError, match="quantity"):
            parse_broker_csv(csv_path)

    def test_una_fila_rota_dice_su_numero(self, tmp_path: Path) -> None:
        csv_path = self.escribir(
            tmp_path / "movs.csv",
            "Date,Symbol,Type,Quantity,Unit Price\n"
            "2026-01-15,GLD,buy,10,180\n"
            "2026-01-16,GLD,buy,diez,180\n",
        )
        with pytest.raises(CsvFormatError, match="fila 3"):
            parse_broker_csv(csv_path)

    def test_varias_divisas_avisan(self, tmp_path: Path) -> None:
        csv_path = self.escribir(
            tmp_path / "movs.csv",
            "Date,Symbol,Type,Quantity,Unit Price,Currency\n"
            "2026-01-15,GLD,buy,10,180,EUR\n"
            "2026-01-16,BTC,buy,1,90000,USD\n",
        )
        assert any("monodivisa" in a for a in parse_broker_csv(csv_path).warnings)

    def test_fechas_europeas_tambien_entran(self, tmp_path: Path) -> None:
        csv_path = self.escribir(
            tmp_path / "movs.csv",
            "Date,Symbol,Type,Quantity,Unit Price\n15/01/2026,GLD,buy,10,180\n",
        )
        actividad = parse_broker_csv(csv_path).activities[0]
        assert actividad.timestamp.date().isoformat() == "2026-01-15"
