"""La puerta del panel al dinero exige lo mismo que la del terminal.

Poner un botón para enviar órdenes es cómodo y por eso es peligroso: un clic distraído no debería
mover dinero. Este módulo fija que el botón del panel **no relaja ninguna de las garantías** que ya
tenía la línea de comandos:

- En simulación no se envía nada, con o sin confirmación.
- Hay que escribir la cantidad exacta. No vale «sí», ni el botón solo.
- La confirmación vale para ESA orden; cambiar la cantidad la invalida.
- Todo lo enviado queda en el registro, con el modo dentro.

Si mañana alguien añade un atajo «enviar sin confirmar», estos tests fallan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.dashboard.ordenes import (
    EnvioBloqueadoError,
    enviar_orden,
    motivo_para_no_enviar,
    puede_enviar,
)
from invest_ll.live.broker import (
    Confirmation,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Side,
    SimulatedBroker,
)
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import OperatingMode, Real, Simulation, Testnet

D = Decimal
AHORA = datetime(2026, 7, 26, 18, 40, tzinfo=UTC)
PRUEBAS = Testnet(key="k", secret="s")


class TestCuandoSePuedeEnviar:
    def test_en_simulacion_nunca(self) -> None:
        assert not puede_enviar(Simulation(), cantidad=D("0.001"), escrito="0.001")

    @pytest.mark.parametrize("modo", [PRUEBAS, Real(key="kr", secret="sr")])
    def test_hace_falta_escribir_la_cantidad(self, modo: OperatingMode) -> None:
        assert not puede_enviar(modo, cantidad=D("0.001"), escrito="")
        assert not puede_enviar(modo, cantidad=D("0.001"), escrito="si")
        assert not puede_enviar(modo, cantidad=D("0.001"), escrito="0.01")
        assert puede_enviar(modo, cantidad=D("0.001"), escrito="0.001")

    def test_los_espacios_alrededor_no_estorban(self) -> None:
        assert puede_enviar(PRUEBAS, cantidad=D("0.001"), escrito="  0.001  ")

    def test_la_misma_cantidad_escrita_de_otra_forma_vale(self) -> None:
        """0.0010 y 0.001 son el mismo numero; exigir la cadena exacta seria un acertijo."""
        assert puede_enviar(PRUEBAS, cantidad=D("0.001"), escrito="0.0010")

    def test_algo_que_no_es_un_numero_no_cuela(self) -> None:
        assert not puede_enviar(PRUEBAS, cantidad=D("0.001"), escrito="cero coma cero cero uno")

    def test_una_cantidad_no_positiva_nunca_se_puede_enviar(self) -> None:
        assert not puede_enviar(PRUEBAS, cantidad=D(0), escrito="0")
        assert not puede_enviar(PRUEBAS, cantidad=D("-1"), escrito="-1")


class TestElMotivoSeExplica:
    def test_en_simulacion_dice_que_no_sale_nada(self) -> None:
        motivo = motivo_para_no_enviar(Simulation(), cantidad=D("0.001"), escrito="0.001")
        assert motivo is not None
        assert "simulacion" in motivo.lower()

    def test_sin_escribir_dice_que_hay_que_escribir_la_cantidad(self) -> None:
        motivo = motivo_para_no_enviar(PRUEBAS, cantidad=D("0.001"), escrito="")
        assert motivo is not None
        assert "0.001" in motivo

    def test_cuando_se_puede_no_hay_motivo(self) -> None:
        assert motivo_para_no_enviar(PRUEBAS, cantidad=D("0.001"), escrito="0.001") is None

    def test_ningun_motivo_muestra_la_credencial(self) -> None:
        modo = Testnet(key="CLAVE_SECRETA_DE_PRUEBAS", secret="SECRETO_QUE_NO_DEBE_SALIR")
        for escrito in ("", "no", "0.01", "0.001"):
            motivo = motivo_para_no_enviar(modo, cantidad=D("0.001"), escrito=escrito) or ""
            assert modo.key not in motivo
            assert modo.secret not in motivo


class TestEnviarDeVerdad:
    def test_en_simulacion_se_niega_en_vez_de_fingir(self, tmp_path: Path) -> None:
        """Devolver un resultado falso seria peor que fallar: parece que opero."""
        with pytest.raises(EnvioBloqueadoError):
            enviar_orden(
                SimulatedBroker(),
                symbol="BTC/USDT",
                side=Side.BUY,
                cantidad=D("0.001"),
                escrito="0.001",
                ahora=AHORA,
                ledger=ExecutionLedger(tmp_path),
            )

    def test_sin_la_cantidad_escrita_no_se_envia(self, tmp_path: Path) -> None:
        broker = _BrokerDePruebas()
        with pytest.raises(EnvioBloqueadoError):
            enviar_orden(
                broker,
                symbol="BTC/USDT",
                side=Side.BUY,
                cantidad=D("0.001"),
                escrito="",
                ahora=AHORA,
                ledger=ExecutionLedger(tmp_path),
            )
        assert broker.enviadas == 0, "se envio una orden sin confirmar"

    def test_con_todo_en_regla_se_envia_y_queda_registrada(self, tmp_path: Path) -> None:
        broker = _BrokerDePruebas()
        ledger = ExecutionLedger(tmp_path)

        resultado = enviar_orden(
            broker,
            symbol="BTC/USDT",
            side=Side.BUY,
            cantidad=D("0.001"),
            escrito="0.001",
            ahora=AHORA,
            ledger=ledger,
        )

        assert broker.enviadas == 1
        assert resultado.status is OrderStatus.FILLED
        entradas = ledger.entries()
        assert len(entradas) == 1
        assert entradas[0].mode_name == "pruebas"
        assert not entradas[0].was_real_money

    def test_la_confirmacion_es_de_esa_orden_y_no_de_otra(self, tmp_path: Path) -> None:
        """El broker rechaza una confirmacion que no corresponde; aqui se comprueba que la que
        construye el panel SI corresponde, que es la otra mitad de la garantia."""
        broker = _BrokerDePruebas()
        enviar_orden(
            broker,
            symbol="BTC/USDT",
            side=Side.BUY,
            cantidad=D("0.001"),
            escrito="0.001",
            ahora=AHORA,
            ledger=ExecutionLedger(tmp_path),
        )
        peticion, confirmacion = broker.ultima
        assert peticion is not None and confirmacion is not None
        assert confirmacion.authorises(peticion)
        assert peticion.quantity == D("0.001")
        assert peticion.requested_at == AHORA


class _BrokerDePruebas:
    """Doble que cuenta lo enviado. La suite corre sin red: nada sale de aqui."""

    def __init__(self) -> None:
        self.enviadas = 0
        self.ultima: tuple[OrderRequest | None, Confirmation | None] = (None, None)
        self._mode = PRUEBAS

    @property
    def mode(self) -> Testnet:
        return self._mode

    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult:
        assert confirmation.authorises(request)
        self.enviadas += 1
        self.ultima = (request, confirmation)
        return OrderResult(
            request=request,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            fill_price=D("64703.52"),
            executed_at=AHORA,
            broker_reference="20684423",
        )

    def balance(self) -> dict[str, Decimal]:
        return {"USDT": D(10_000)}
