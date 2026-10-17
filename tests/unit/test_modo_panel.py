"""El modo efectivo: entorno primero, panel después, y los cuatro cerrojos de siempre.

Lo que se comprueba es que el panel solo cambia DE DÓNDE salen el modo y las claves: quien decide
sigue siendo `resolve_mode`, y la marca de "ya operé en pruebas" solo la pone una orden de pruebas
ejecutada de verdad en el registro.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import keyring
import pytest

from invest_ll.live import credenciales
from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import ExecutionLedger, LedgerEntry
from invest_ll.live.mode import (
    VAR_CLAVE_PRUEBAS,
    VAR_MODO,
    VAR_SECRETO_PRUEBAS,
    VAR_TESTNET_HECHA,
    CredentialError,
    ModeError,
    Real,
    Simulation,
    Testnet,
)
from invest_ll.live.modo_panel import (
    ConfigPanel,
    ConfigPanelError,
    Fuentes,
    ModoPanel,
    entorno_efectivo,
    fuentes_actuales,
    ordenes_ejecutadas,
    resolver,
)

from ..almacen_en_memoria import AlmacenEnMemoria

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.live.credenciales import Red

PRUEBAS = credenciales.Claves(clave="clave-pruebas", secreto="secreto-pruebas")
REALES = credenciales.Claves(clave="clave-real-1", secreto="secreto-real-1")


def _fuentes(
    *,
    entorno: dict[str, str] | None = None,
    modo: ModoPanel | None = None,
    pruebas: credenciales.Claves | None = None,
    reales: credenciales.Claves | None = None,
    ordenes: int = 0,
) -> Fuentes:
    claves: dict[Red, credenciales.Claves | None] = {"pruebas": pruebas, "real": reales}
    return Fuentes(
        entorno=entorno or {},
        modo_panel=modo,
        claves=claves,
        ordenes_de_pruebas=ordenes,
    )


def _entrada(modo: str, estado: OrderStatus, ejecutada: str) -> LedgerEntry:
    peticion = OrderRequest(
        symbol="BTC/USDT",
        side=Side.BUY,
        quantity=Decimal("0.001"),
        requested_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    return LedgerEntry(
        result=OrderResult(
            request=peticion,
            status=estado,
            filled_quantity=Decimal(ejecutada),
            fill_price=Decimal(90000) if Decimal(ejecutada) > 0 else None,
            executed_at=peticion.requested_at,
        ),
        mode_name=modo,
        recorded_at=peticion.requested_at,
    )


# -- La evidencia -----------------------------------------------------------------------------


def test_solo_cuentan_las_ordenes_de_pruebas_ejecutadas() -> None:
    entradas = [
        _entrada("pruebas", OrderStatus.REJECTED, "0"),
        _entrada("pruebas", OrderStatus.UNKNOWN, "0"),
        _entrada("simulacion", OrderStatus.FILLED, "0.001"),
        _entrada("REAL", OrderStatus.FILLED, "0.001"),
    ]
    assert ordenes_ejecutadas(entradas, "pruebas") == 0
    assert (
        ordenes_ejecutadas(
            [*entradas, _entrada("pruebas", OrderStatus.PARTIAL, "0.0005")], "pruebas"
        )
        == 1
    )
    assert ordenes_ejecutadas(entradas, "real") == 1


def test_la_marca_de_pruebas_solo_con_evidencia() -> None:
    sin = entorno_efectivo(_fuentes(modo="real", reales=REALES, ordenes=0))
    con = entorno_efectivo(_fuentes(modo="real", reales=REALES, ordenes=1))
    assert VAR_TESTNET_HECHA not in sin
    assert con[VAR_TESTNET_HECHA] == "1"


# -- De dónde sale cada cosa ------------------------------------------------------------------


def test_sin_nada_simulacion() -> None:
    efectivo = resolver(_fuentes())
    assert isinstance(efectivo.modo, Simulation)
    assert efectivo.origen == "panel"
    assert efectivo.aviso is None


def test_el_modo_y_las_claves_del_panel() -> None:
    efectivo = resolver(_fuentes(modo="pruebas", pruebas=PRUEBAS))
    assert efectivo.modo == Testnet(key="clave-pruebas", secret="secreto-pruebas")


def test_el_entorno_manda_sobre_el_panel() -> None:
    entorno = {
        VAR_MODO: "testnet",
        VAR_CLAVE_PRUEBAS: "del-entorno",
        VAR_SECRETO_PRUEBAS: "secreto-entorno",
    }
    efectivo = resolver(_fuentes(entorno=entorno, modo="simulacion", pruebas=PRUEBAS))
    assert efectivo.origen == "entorno"
    assert efectivo.modo == Testnet(key="del-entorno", secret="secreto-entorno")


def test_un_par_de_claves_no_se_mezcla_entre_entorno_y_panel() -> None:
    """Con la clave en el entorno y sin secreto, falla: no se completa con el del almacén."""
    entorno = {VAR_MODO: "testnet", VAR_CLAVE_PRUEBAS: "del-entorno"}
    with pytest.raises(CredentialError, match=VAR_SECRETO_PRUEBAS):
        resolver(_fuentes(entorno=entorno, pruebas=PRUEBAS))


def test_dinero_real_sin_haber_operado_en_pruebas_no_se_activa() -> None:
    efectivo = resolver(_fuentes(modo="real", pruebas=PRUEBAS, reales=REALES, ordenes=0))
    assert isinstance(efectivo.modo, Simulation), "el panel vuelve a simulación"
    assert efectivo.aviso is not None
    assert "red de pruebas" in efectivo.aviso


def test_dinero_real_con_evidencia_y_claves_distintas() -> None:
    efectivo = resolver(_fuentes(modo="real", pruebas=PRUEBAS, reales=REALES, ordenes=1))
    assert efectivo.modo == Real(key="clave-real-1", secret="secreto-real-1")


def test_dinero_real_con_las_claves_de_pruebas_no_se_activa() -> None:
    misma = credenciales.Claves(clave="clave-pruebas", secreto="otro-secreto")
    efectivo = resolver(_fuentes(modo="real", pruebas=PRUEBAS, reales=misma, ordenes=1))
    assert isinstance(efectivo.modo, Simulation)
    assert efectivo.aviso is not None and "coincide" in efectivo.aviso


def test_si_lo_pide_el_entorno_el_error_sale_tal_cual() -> None:
    with pytest.raises(ModeError, match="red de pruebas"):
        resolver(_fuentes(entorno={VAR_MODO: "real"}, reales=REALES))


def test_el_entorno_puede_declarar_la_etapa_de_pruebas() -> None:
    entorno = {VAR_MODO: "real", VAR_TESTNET_HECHA: "1"}
    efectivo = resolver(_fuentes(entorno=entorno, reales=REALES))
    assert isinstance(efectivo.modo, Real)


# -- Los ficheros ------------------------------------------------------------------------------


def test_config_del_panel(tmp_path: Path) -> None:
    config = ConfigPanel(tmp_path / "config")
    assert config.modo() is None
    config.guardar_modo("pruebas")
    assert config.modo() == "pruebas"
    assert "clave" not in config.path.read_text(encoding="utf-8")


def test_config_ilegible(tmp_path: Path) -> None:
    config = ConfigPanel(tmp_path)
    config.path.write_text('{"modo": "turbo"}', encoding="utf-8")
    with pytest.raises(ConfigPanelError, match="turbo"):
        config.modo()


def test_una_config_estropeada_no_deja_el_panel_sin_arrancar(tmp_path: Path) -> None:
    config = ConfigPanel(tmp_path)
    config.path.write_text("{roto", encoding="utf-8")

    f = fuentes_actuales(entorno={}, config=config, registro=ExecutionLedger(tmp_path))
    efectivo = resolver(f)

    assert isinstance(efectivo.modo, Simulation)
    assert efectivo.aviso is not None
    assert "no se puede leer" in efectivo.aviso


def test_fuentes_actuales_leen_el_almacen_del_test(tmp_path: Path) -> None:
    """El almacén de claves de la suite es el de memoria, nunca el del sistema."""
    assert isinstance(keyring.get_keyring(), AlmacenEnMemoria)
    credenciales.guardar("pruebas", PRUEBAS)
    registro = ExecutionLedger(tmp_path / "ledger")
    registro.record(_entrada("pruebas", OrderStatus.FILLED, "0.001").result, mode_name="pruebas")

    f = fuentes_actuales(entorno={}, config=ConfigPanel(tmp_path / "config"), registro=registro)

    assert f.claves["pruebas"] == PRUEBAS
    assert f.claves["real"] is None
    assert f.ordenes_de_pruebas == 1
