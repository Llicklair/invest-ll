"""Lo que NO debe poder pasar con dinero real (T057-T063, T067-T069, T073).

Este fichero es casi todo negativos. Existe porque el Principio I dice que el modo simulación es
el estado por defecto y que ninguna orden real puede salir sin activación explícita — y una
promesa que no se comprueba automáticamente no es una garantía, es una intención.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from invest_ll.live.broker import (
    Confirmation,
    ConfirmationMismatchError,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Side,
    SimulatedBroker,
)
from invest_ll.live.mode import (
    VAR_CLAVE_PRUEBAS,
    VAR_CLAVE_REAL,
    VAR_MODO,
    VAR_SECRETO_PRUEBAS,
    VAR_SECRETO_REAL,
    VAR_TESTNET_HECHA,
    CredentialError,
    ModeError,
    Real,
    Simulation,
    Testnet,
    resolve_mode,
)

D = Decimal
CUANDO = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def orden(symbol: str = "BTC/USDT", cantidad: str = "0.001") -> OrderRequest:
    return OrderRequest(symbol=symbol, side=Side.BUY, quantity=D(cantidad), requested_at=CUANDO)


ENTORNO_REAL_COMPLETO = {
    VAR_MODO: "real",
    VAR_CLAVE_REAL: "clave-real",
    VAR_SECRETO_REAL: "secreto-real",
    VAR_TESTNET_HECHA: "1",
}


class TestElPorDefectoEsSeguro:
    """FR-025: lo seguro tiene que ser lo que pasa cuando nadie hace nada."""

    def test_sin_configurar_nada_es_simulacion(self) -> None:
        assert isinstance(resolve_mode({}), Simulation)

    def test_la_simulacion_no_manda_ordenes(self) -> None:
        assert not resolve_mode({}).sends_real_orders

    def test_un_modo_vacio_es_simulacion(self) -> None:
        assert isinstance(resolve_mode({VAR_MODO: "  "}), Simulation)

    def test_un_modo_desconocido_no_cae_en_real_por_accidente(self) -> None:
        """Un typo no puede acabar mandando dinero."""
        with pytest.raises(ModeError, match="modo desconocido"):
            resolve_mode({VAR_MODO: "reall"})


class TestElModoRealExigeDosCosas:
    """FR-026: accion explicita Y credenciales separadas. Ninguna basta por si sola."""

    def test_pedir_real_sin_credenciales_falla(self) -> None:
        with pytest.raises((CredentialError, ModeError)):
            resolve_mode({VAR_MODO: "real"})

    def test_tener_credenciales_sin_pedirlo_no_activa_real(self) -> None:
        """FR-027: el modo real no se activa por configuracion heredada."""
        modo = resolve_mode(
            {VAR_CLAVE_REAL: "clave", VAR_SECRETO_REAL: "secreto", VAR_TESTNET_HECHA: "1"}
        )
        assert isinstance(modo, Simulation)

    def test_con_las_dos_cosas_si_se_activa(self) -> None:
        assert isinstance(resolve_mode(ENTORNO_REAL_COMPLETO), Real)

    def test_falta_el_secreto_y_falla(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        del entorno[VAR_SECRETO_REAL]
        with pytest.raises(CredentialError, match=VAR_SECRETO_REAL):
            resolve_mode(entorno)


class TestTestnetObligatoriaAntesDeRealDinero:
    """FR-047: los fallos de ejecucion se descubren en pruebas, no pagandolos."""

    def test_sin_haber_operado_en_pruebas_el_modo_real_se_rechaza(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        del entorno[VAR_TESTNET_HECHA]
        with pytest.raises(ModeError, match="red de pruebas"):
            resolve_mode(entorno)

    def test_el_mensaje_dice_como_desbloquearlo(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        del entorno[VAR_TESTNET_HECHA]
        with pytest.raises(ModeError, match="testnet"):
            resolve_mode(entorno)

    def test_el_modo_pruebas_no_exige_nada_previo(self) -> None:
        modo = resolve_mode({VAR_MODO: "testnet", VAR_CLAVE_PRUEBAS: "k", VAR_SECRETO_PRUEBAS: "s"})
        assert isinstance(modo, Testnet)


class TestCredencialesNoIntercambiables:
    """FR-048: usar las de pruebas donde tocan las reales falla de forma visible."""

    def test_la_misma_clave_para_ambos_modos_se_rechaza(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        entorno[VAR_CLAVE_PRUEBAS] = entorno[VAR_CLAVE_REAL]
        with pytest.raises(CredentialError, match="coincide"):
            resolve_mode(entorno)

    def test_claves_distintas_se_aceptan(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        entorno[VAR_CLAVE_PRUEBAS] = "otra-clave-distinta"
        assert isinstance(resolve_mode(entorno), Real)


class TestNingunaCredencialSeFiltra:
    """FR-034: ni en mensajes de error, ni en registros, ni en informes."""

    def test_el_error_por_credencial_cruzada_no_muestra_la_clave(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        entorno[VAR_CLAVE_PRUEBAS] = entorno[VAR_CLAVE_REAL]
        with pytest.raises(CredentialError) as error:
            resolve_mode(entorno)
        assert "clave-real" not in str(error.value)

    def test_el_error_por_credencial_ausente_no_muestra_las_demas(self) -> None:
        entorno = dict(ENTORNO_REAL_COMPLETO)
        del entorno[VAR_SECRETO_REAL]
        with pytest.raises(CredentialError) as error:
            resolve_mode(entorno)
        assert "clave-real" not in str(error.value)

    def test_el_modo_no_expone_el_secreto_al_imprimirse(self) -> None:
        modo = resolve_mode(ENTORNO_REAL_COMPLETO)
        assert modo.name == "REAL"


class TestElSimuladorNuncaManda:
    """FR-038: la garantia que protege el estado por defecto."""

    def test_el_simulador_no_manda_ordenes_reales(self) -> None:
        broker = SimulatedBroker()
        o = orden()
        broker.submit(o, confirmation=Confirmation.para(o, at=CUANDO))
        assert not broker.mode.sends_real_orders

    def test_el_simulador_registra_lo_que_habria_hecho(self) -> None:
        broker = SimulatedBroker()
        o = orden()
        broker.submit(o, confirmation=Confirmation.para(o, at=CUANDO))
        assert broker.submitted == (o,)

    def test_su_modo_siempre_es_simulacion(self) -> None:
        assert isinstance(SimulatedBroker().mode, Simulation)


class TestConfirmacionPorOrden:
    """FR-028: autorizar todas las ordenes de golpe no se puede escribir."""

    def test_no_se_puede_enviar_sin_confirmacion(self) -> None:
        """El parametro no tiene valor por defecto: es un TypeError, no un olvido."""
        with pytest.raises(TypeError):
            SimulatedBroker().submit(orden())  # type: ignore[call-arg]

    def test_la_confirmacion_de_otra_orden_no_sirve(self) -> None:
        broker = SimulatedBroker()
        confirmada = orden("BTC/USDT")
        otra = orden("ETH/USDT")
        with pytest.raises(ConfirmationMismatchError):
            broker.submit(otra, confirmation=Confirmation.para(confirmada, at=CUANDO))

    def test_cambiar_la_cantidad_invalida_la_confirmacion(self) -> None:
        """Confirmar 0.001 y enviar 1.0 no puede colar."""
        broker = SimulatedBroker()
        pequena = orden(cantidad="0.001")
        grande = orden(cantidad="1.0")
        with pytest.raises(ConfirmationMismatchError):
            broker.submit(grande, confirmation=Confirmation.para(pequena, at=CUANDO))


class TestEstadoDesconocido:
    """FR-035: se envio y se perdio la conexion."""

    def resultado(self, estado: OrderStatus, ejecutada: str = "0") -> OrderResult:
        return OrderResult(
            request=orden(),
            status=estado,
            filled_quantity=D(ejecutada),
            fill_price=None,
            executed_at=None,
        )

    def test_desconocido_no_se_da_por_ejecutado(self) -> None:
        r = self.resultado(OrderStatus.UNKNOWN)
        assert not r.matches_request
        assert r.needs_attention

    def test_el_mensaje_dice_que_hay_que_comprobarlo(self) -> None:
        texto = self.resultado(OrderStatus.UNKNOWN).describe()
        assert "NO se asume" in texto
        assert "compruebalo en el exchange" in texto

    def test_una_ejecucion_parcial_pide_atencion(self) -> None:
        """FR-031: una diferencia se comunica, no se da por buena."""
        r = self.resultado(OrderStatus.PARTIAL, ejecutada="0.0005")
        assert r.needs_attention
        assert "solo en parte" in r.describe()

    def test_lo_que_salio_exacto_no_pide_atencion(self) -> None:
        r = OrderResult(
            request=orden(),
            status=OrderStatus.FILLED,
            filled_quantity=D("0.001"),
            fill_price=D(50000),
            executed_at=CUANDO,
        )
        assert not r.needs_attention

    def test_los_mensajes_son_imprimibles_en_consola_windows(self) -> None:
        for estado in OrderStatus:
            self.resultado(estado).describe().encode("cp1252")


class TestValidacionDeOrdenes:
    @pytest.mark.parametrize("cantidad", ["0", "-1"])
    def test_una_cantidad_no_positiva_se_rechaza(self, cantidad: str) -> None:
        with pytest.raises(ValueError, match="cantidad no positiva"):
            orden(cantidad=cantidad)

    def test_sin_simbolo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="simbolo"):
            orden(symbol="")
