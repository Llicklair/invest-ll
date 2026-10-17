"""El conector genérico sobre ccxt, sin red: con un exchange de ccxt de mentira (`exchanges_apoyo`).

Lo que se comprueba es lo que protege el dinero de un bot real: que un reintento no duplica, que un
corte se dice como estado desconocido (nunca se adivina), que se redondea a los pasos del mercado y
se avisa en llano antes de enviar algo por debajo del mínimo, que la comisión es la que cobró el
exchange, y que ninguna clave aparece en ningún mensaje.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from invest_ll.exchanges.ccxt_conector import (
    FORMATOS_ID,
    comision_de,
    es_incierto,
    estado_de,
    fin_de_vela,
    id_en_el_exchange,
    limpiar,
    permisos_binance,
    permisos_bybit,
    permisos_coinbase,
    permisos_hyperliquid,
    permisos_kraken,
    permisos_okx,
)
from invest_ll.exchanges.conector import EstadoDesconocidoError, ExchangeError
from invest_ll.exchanges.fichas import (
    BINANCE,
    BYBIT,
    COINBASE,
    FICHAS,
    HYPERLIQUID,
    KRAKEN,
    OKX,
    Ficha,
)

from .exchanges_apoyo import AHORA_MS, Ccxt, CcxtFalso, conector, mercado_ccxt

D = Decimal
SECRETO = "SECRETO-DE-VERDAD-1"


# -- El id de cliente --------------------------------------------------------------------------


class TestIdDeCliente:
    @pytest.mark.parametrize("ficha", FICHAS, ids=[f.id for f in FICHAS])
    def test_siempre_valido_y_siempre_el_mismo(self, ficha: Ficha) -> None:
        for id_cliente in ("bot-rebote-eth-20261017-0001", "a b c/ñ", "x" * 200, "ok1"):
            derivado = id_en_el_exchange(ficha.formato_id, id_cliente)
            assert FORMATOS_ID[ficha.formato_id].fullmatch(derivado), (ficha.id, derivado)
            assert derivado == id_en_el_exchange(ficha.formato_id, id_cliente)

    def test_si_ya_vale_se_usa_tal_cual(self) -> None:
        assert id_en_el_exchange("texto36", "bot-1_2") == "bot-1_2"
        assert id_en_el_exchange("alnum32", "bot12") == "bot12"

    def test_ids_distintos_dan_ids_distintos(self) -> None:
        ids = {id_en_el_exchange("hex128", f"bot-{i}") for i in range(500)}
        assert len(ids) == 500

    def test_formatos_de_cada_exchange(self) -> None:
        assert re.fullmatch(r"0x[0-9a-f]{32}", id_en_el_exchange("hex128", "bot-1"))
        assert len(id_en_el_exchange("alnum32", "bot-1")) <= 32
        assert "-" not in id_en_el_exchange("alnum32", "bot-1")
        assert re.fullmatch(r"[0-9a-f]{32}", id_en_el_exchange("kraken", "bot-con-id-muy-largo-1"))

    def test_sin_id_no_se_envia(self) -> None:
        with pytest.raises(ExchangeError, match="id de cliente"):
            id_en_el_exchange("texto36", "  ")


# -- Mercados, precio, libro, velas --------------------------------------------------------------


class TestDatosPublicos:
    def test_mercados_solo_de_contado_con_pasos_minimos_y_comisiones(self) -> None:
        mercados = conector(claves={}).mercados()
        assert [m.par for m in mercados] == ["BTC/USDT", "ETH/USDT"]
        btc = mercados[0]
        assert (btc.paso_cantidad, btc.paso_precio) == (D("0.00001"), D("0.01"))
        assert (btc.minimo_importe, btc.minimo_cantidad) == (D(5), D("0.00001"))
        assert btc.comision_tomador == D("0.001")

    def test_los_mercados_se_cargan_una_vez(self) -> None:
        ex = CcxtFalso()
        c = conector(ex)
        c.mercados()
        c.precio("BTC/USDT")
        c.libro("BTC/USDT")
        assert ex.cargas == 1

    def test_precio(self) -> None:
        assert conector().precio("BTC/USDT") == D(60000)

    def test_un_par_que_no_existe_o_no_es_de_contado(self) -> None:
        c = conector()
        with pytest.raises(ExchangeError, match="no tiene el par DOGE/USDT"):
            c.precio("DOGE/USDT")
        with pytest.raises(ExchangeError, match="de contado"):
            c.precio("BTC-PERP")

    def test_libro_con_los_niveles_pedidos_y_un_tamano_que_binance_acepta(self) -> None:
        ex = CcxtFalso()
        libro = conector(ex).libro("BTC/USDT", niveles=7)
        assert libro is not None
        assert len(libro.compras) == len(libro.ventas) == 7
        assert libro.mejor_compra == D(59999)
        assert libro.mejor_venta == D(60001)
        assert ex.libros_pedidos == [10]  # Binance solo acepta 5, 10, 20, 50...

    def test_velas_las_ultimas_y_si_estan_cerradas(self) -> None:
        hora = 3_600_000
        ex = CcxtFalso(filas=[[AHORA_MS - (3 - i) * hora, 1, 2, 0.5, 1.5, 10] for i in range(4)])
        c = conector(ex)
        c._reloj = lambda: datetime.fromtimestamp(AHORA_MS / 1000, tz=UTC)  # pyright: ignore[reportPrivateUsage]
        velas = c.velas("BTC/USDT", "1h", limite=3)
        assert len(velas) == 3
        assert velas[-1].cerrada is False  # la de ahora, en curso
        assert all(v.cerrada for v in velas[:-1])
        assert velas[0].cierre == D("1.5")
        assert velas[0].fin - velas[0].inicio == timedelta(hours=1)

    def test_velas_de_muchas_se_piden_por_partes(self) -> None:
        minuto = 60_000
        ex = CcxtFalso(
            filas=[[AHORA_MS - (2500 - i) * minuto, 1, 1, 1, 1, 1] for i in range(2500)],
            velas_por_peticion=1000,
        )
        c = conector(ex)
        c._reloj = lambda: datetime.fromtimestamp(AHORA_MS / 1000, tz=UTC)  # pyright: ignore[reportPrivateUsage]
        velas = c.velas("BTC/USDT", "1m", limite=2400)
        assert len(velas) == 2400
        inicios = [v.inicio for v in velas]
        assert inicios == sorted(set(inicios))
        assert sum("velas" in llamada for llamada in ex.llamadas) >= 3

    def test_un_intervalo_que_no_tiene_lo_dice(self) -> None:
        with pytest.raises(ExchangeError, match="no tiene velas de 3h: tiene 1m, 1h, 1d"):
            conector().velas("BTC/USDT", "3h")

    def test_fin_de_vela_mensual(self) -> None:
        inicio = datetime(2026, 12, 1, tzinfo=UTC)
        assert fin_de_vela(inicio, "1M") == datetime(2027, 1, 1, tzinfo=UTC)

    def test_sin_conexion_en_llano(self) -> None:
        ex = CcxtFalso(fallo_al_leer=Ccxt.RequestTimeout("timeout"))
        with pytest.raises(ExchangeError, match="No hay conexión con Binance"):
            conector(ex).precio("BTC/USDT")


# -- Redondeo y mínimos ------------------------------------------------------------------------


class TestRedondeoYMinimos:
    def test_la_cantidad_se_redondea_hacia_abajo_al_paso(self) -> None:
        ex = CcxtFalso()
        orden = conector(ex).enviar("BTC/USDT", "compra", D("0.0012345678"), id_cliente="o1")
        assert ex.creadas[0]["amount"] == 0.00123
        assert orden.cantidad == D("0.00123")

    def test_el_precio_limite_se_redondea_al_paso(self) -> None:
        ex = CcxtFalso()
        conector(ex).enviar(
            "BTC/USDT", "compra", D("0.001"), id_cliente="o1", tipo="limite", precio=D("59000.126")
        )
        assert ex.creadas[0]["price"] == 59000.13

    def test_por_debajo_del_paso_no_se_envia(self) -> None:
        ex = CcxtFalso()
        with pytest.raises(ExchangeError, match=r"se queda en cero .* \(paso 0.00001\)"):
            conector(ex).enviar("BTC/USDT", "compra", D("0.000001"), id_cliente="o1")
        assert ex.creadas == []

    def test_por_debajo_del_importe_minimo_no_se_envia(self) -> None:
        ex = CcxtFalso()
        with pytest.raises(ExchangeError, match=r"importe mínimo .* es 5 USDT; esta son unos 3.00"):
            conector(ex).enviar("BTC/USDT", "compra", D("0.00005"), id_cliente="o1")
        assert ex.creadas == []

    def test_por_debajo_de_la_cantidad_minima_no_se_envia(self) -> None:
        ex = CcxtFalso()
        ex.markets["BTC/USDT"] = mercado_ccxt(minimo_cantidad=0.001, minimo_importe=None)
        with pytest.raises(ExchangeError, match=r"cantidad mínima de BTC/USDT en Binance es 0.001"):
            conector(ex).enviar("BTC/USDT", "compra", D("0.0005"), id_cliente="o1")

    def test_una_limite_sin_precio(self) -> None:
        with pytest.raises(ExchangeError, match="necesita un precio"):
            conector().enviar("BTC/USDT", "compra", D("0.001"), id_cliente="o1", tipo="limite")


# -- Enviar: id de cliente, reintentos, estado desconocido -------------------------------------


class TestEnviar:
    def test_una_orden_de_mercado_ejecutada_con_su_comision(self) -> None:
        ex = CcxtFalso()
        orden = conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert orden.estado == "ejecutada"
        assert orden.ejecutada == D("0.001")
        assert orden.precio_medio == D(60000)
        assert orden.comision == D("0.06")
        assert orden.comision_moneda == "USDT"
        assert orden.id_cliente == "bot-1"
        assert ex.creadas[0]["clientOrderId"] == "bot-1"

    def test_un_reintento_con_el_mismo_id_no_duplica(self) -> None:
        ex = CcxtFalso()
        c = conector(ex)
        primera = c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        segunda = c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert len(ex.creadas) == 1
        assert segunda.id_exchange == primera.id_exchange

    def test_tampoco_duplica_desde_otro_conector_tras_reiniciar(self) -> None:
        ex = CcxtFalso()
        conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert len(ex.creadas) == 1

    def test_el_mismo_id_para_otra_orden_se_rechaza(self) -> None:
        c = conector()
        c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        with pytest.raises(ExchangeError, match=r"ya se usó .* para otra orden"):
            c.enviar("BTC/USDT", "venta", D("0.001"), id_cliente="bot-1")

    def test_si_no_se_puede_comprobar_si_existia_no_se_envia(self) -> None:
        ex = CcxtFalso(fallo_al_buscar=Ccxt.NetworkError("caída"))
        with pytest.raises(ExchangeError, match="no se ha enviado nada") as error:
            conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert not isinstance(error.value, EstadoDesconocidoError)
        assert ex.creadas == []

    @pytest.mark.parametrize(
        "fallo",
        [Ccxt.RequestTimeout("t"), Ccxt.NetworkError("n"), Ccxt.BadResponse("b"), OSError("x")],
        ids=["timeout", "red", "respuesta-rota", "no-ccxt"],
    )
    def test_un_corte_al_enviar_es_estado_desconocido(self, fallo: Exception) -> None:
        ex = CcxtFalso(fallo_al_crear=fallo)
        with pytest.raises(EstadoDesconocidoError, match="NO se sabe si se ejecutó"):
            conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")

    def test_el_estado_desconocido_se_resuelve_con_orden(self) -> None:
        """Llegó al exchange aunque se cortara la respuesta: `orden()` lo dice, y un reintento
        devuelve esa misma orden en vez de enviar otra."""
        ex = CcxtFalso(fallo_al_crear=Ccxt.RequestTimeout("t"), llega_aunque_falle=True)
        c = conector(ex)
        with pytest.raises(EstadoDesconocidoError):
            c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        ex.fallo_al_crear = None

        resuelta = c.orden("BTC/USDT", id_cliente="bot-1")
        assert resuelta is not None
        assert resuelta.estado == "ejecutada"
        reintento = c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert reintento.id_exchange == resuelta.id_exchange
        assert len(ex.creadas) == 1

    def test_si_no_llego_orden_dice_none(self) -> None:
        ex = CcxtFalso(fallo_al_crear=Ccxt.RequestTimeout("t"))
        c = conector(ex)
        with pytest.raises(EstadoDesconocidoError):
            c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert c.orden("BTC/USDT", id_cliente="bot-1") is None

    @pytest.mark.parametrize(
        ("fallo", "texto"),
        [
            (Ccxt.InsufficientFunds("x"), "No hay saldo suficiente en Binance"),
            (Ccxt.InvalidOrder("Filter failure: LOT_SIZE"), "no acepta la orden: Filter failure"),
            (Ccxt.AuthenticationError("bad"), "rechaza las claves"),
            (Ccxt.InvalidNonce("-1021"), "la hora de tu ordenador"),
        ],
        ids=["saldo", "orden", "claves", "hora"],
    )
    def test_un_rechazo_es_un_error_en_llano_no_un_estado_desconocido(
        self, fallo: Exception, texto: str
    ) -> None:
        ex = CcxtFalso(fallo_al_crear=fallo)
        with pytest.raises(ExchangeError, match=texto) as error:
            conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert not isinstance(error.value, EstadoDesconocidoError)

    def test_un_id_duplicado_es_la_orden_de_antes(self) -> None:
        ex = CcxtFalso(fallo_al_crear=Ccxt.DuplicateOrderId("dup"), llega_aunque_falle=True)
        # La búsqueda previa no la ve (el exchange tarda en enseñarla), el envío dice duplicada.
        buscar = ex._buscar  # pyright: ignore[reportPrivateUsage]
        vistas: list[int] = []

        def busca_tarde(params: dict[str, object] | None) -> dict[str, object] | None:
            vistas.append(1)
            return None if len(vistas) == 1 else buscar(params)

        ex._buscar = busca_tarde  # type: ignore[method-assign]
        orden = conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert orden.estado == "ejecutada"

    def test_si_la_respuesta_trae_solo_los_ids_se_lee_la_orden(self) -> None:
        ex = CcxtFalso(estilo="solo_ids")
        orden = conector(ex, OKX, claves={"apiKey": "k1", "secret": "s1", "password": "p"}).enviar(
            "BTC/USDT", "compra", D("0.001"), id_cliente="bot1"
        )
        assert orden.estado == "ejecutada"
        assert orden.ejecutada == D("0.001")
        assert ex.creadas[0]["tgtCcy"] == "base_ccy"

    def test_una_de_mercado_aun_abierta_se_vuelve_a_leer(self) -> None:
        ex = CcxtFalso(estilo="solo_ids", abierta_tras_crear=2)
        orden = conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert orden.estado == "ejecutada"

    def test_aceptada_pero_ilegible_es_estado_desconocido(self) -> None:
        ex = CcxtFalso(estilo="solo_ids")
        c = conector(ex)
        c._buscar = lambda par, id_ex: None  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(EstadoDesconocidoError, match="aceptó la orden bot-1"):
            c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")

    def test_una_limite_queda_abierta_y_se_cancela(self) -> None:
        ex = CcxtFalso()
        c = conector(ex)
        orden = c.enviar(
            "BTC/USDT", "compra", D("0.001"), id_cliente="lim-1", tipo="limite", precio=D(50000)
        )
        assert orden.estado == "abierta"
        assert [o.id_cliente for o in c.ordenes_abiertas()] == ["lim-1"]
        cancelada = c.cancelar("BTC/USDT", id_cliente="lim-1")
        assert cancelada is not None
        assert cancelada.estado == "cancelada"
        assert c.ordenes_abiertas("BTC/USDT") == []
        assert c.cancelar("BTC/USDT", id_cliente="no-existe") is None

    def test_sin_claves_no_hay_ordenes(self) -> None:
        from invest_ll.exchanges.ccxt_conector import ConectorCcxt

        publico = ConectorCcxt(CcxtFalso(), BINANCE, "real")
        with pytest.raises(ExchangeError, match="solo da datos públicos"):
            publico.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="x")
        with pytest.raises(ExchangeError, match="solo da datos públicos"):
            publico.saldo()


class TestCadaExchangeBuscaASuManera:
    def test_bybit_por_abiertas_y_cerradas_con_order_link_id(self) -> None:
        ex = CcxtFalso(estilo="solo_ids")
        c = conector(ex, BYBIT)
        c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert any("orderLinkId" in llamada for llamada in ex.llamadas)

    def test_coinbase_entre_las_recientes_y_con_su_campo(self) -> None:
        ex = CcxtFalso(estilo="solo_ids")
        c = conector(
            ex, COINBASE, red="real", claves={"apiKey": "organizations/x", "secret": "-----BEGIN"}
        )
        orden = c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert ex.creadas[0]["client_order_id"] == "bot-1"
        assert ex.creadas[0]["price"] == 60000.0  # compra a mercado por importe: con el precio
        assert any("recientes" in llamada for llamada in ex.llamadas)
        assert orden.estado == "ejecutada"

    def test_hyperliquid_con_cloid_y_deslizamiento(self) -> None:
        ex = CcxtFalso()
        c = conector(ex, HYPERLIQUID, claves={"walletAddress": "0x" + "a" * 40, "privateKey": "k"})
        c.enviar("BTC/USDT", "venta", D("0.001"), id_cliente="bot-1")
        enviada = ex.creadas[0]
        assert re.fullmatch(r"0x[0-9a-f]{32}", enviada["clientOrderId"])
        assert enviada["slippage"] == "0.02"
        assert enviada["price"] == 60000.0
        # y las abiertas devuelven el id de quien la envió, no el derivado
        c.enviar("BTC/USDT", "compra", D("0.01"), id_cliente="lim", tipo="limite", precio=D(1000))
        assert [o.id_cliente for o in c.ordenes_abiertas()] == ["lim"]

    def test_kraken_por_cl_ord_id(self) -> None:
        ex = CcxtFalso(estilo="solo_ids")
        c = conector(ex, KRAKEN, red="real")
        c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-con-un-id-largo-1")
        assert re.fullmatch(r"[0-9a-f]{32}", ex.creadas[0]["clientOrderId"])


# -- Comisiones ----------------------------------------------------------------------------------


class TestComisiones:
    def test_la_de_la_orden(self) -> None:
        assert comision_de({"fee": {"cost": 0.06, "currency": "USDT"}}) == (D("0.06"), "USDT")

    def test_varias_en_la_misma_moneda_se_suman(self) -> None:
        crudo = {"fees": [{"cost": 0.01, "currency": "BNB"}, {"cost": 0.02, "currency": "BNB"}]}
        assert comision_de(crudo) == (D("0.03"), "BNB")

    def test_en_varias_monedas_no_se_inventa_la_suma(self) -> None:
        crudo = {"fees": [{"cost": 0.01, "currency": "BNB"}, {"cost": 0.5, "currency": "USDT"}]}
        assert comision_de(crudo) == (None, None)

    def test_las_de_cero_en_otra_moneda_no_cuentan(self) -> None:
        crudo = {"fees": [{"cost": 0.5, "currency": "USDT"}, {"cost": 0, "currency": "BNB"}]}
        assert comision_de(crudo) == (D("0.5"), "USDT")

    def test_binance_la_reparte_en_los_fills(self) -> None:
        crudo = {
            "fee": None,
            "info": {
                "fills": [
                    {"commission": "0.00000100", "commissionAsset": "BTC"},
                    {"commission": "0.00000050", "commissionAsset": "BTC"},
                ]
            },
        }
        assert comision_de(crudo) == (D("0.0000015"), "BTC")

    def test_si_no_la_dice_es_none_no_cero(self) -> None:
        assert comision_de({"fee": None}) == (None, None)

    def test_si_la_orden_no_la_trae_se_buscan_sus_operaciones(self) -> None:
        ex = CcxtFalso(comision_en_la_orden=False)
        orden = conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert orden.comision == D("0.06")
        assert "operaciones de la orden" in ex.llamadas

    def test_hyperliquid_las_busca_en_mis_operaciones(self) -> None:
        ex = CcxtFalso(comision_en_la_orden=False, has={"fetchMyTrades": True})
        c = conector(ex, HYPERLIQUID, claves={"walletAddress": "0x" + "a" * 40, "privateKey": "k"})
        orden = c.enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
        assert orden.comision == D("0.06")
        assert any(llamada.startswith("mis operaciones") for llamada in ex.llamadas)


# -- Estados ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "estado"),
    [
        ({"status": "open", "filled": 0}, "abierta"),
        ({"status": "open", "filled": 0.5, "amount": 1}, "parcial"),
        ({"status": "closed", "filled": 1, "amount": 1}, "ejecutada"),
        ({"status": "closed", "filled": 0.4, "amount": 1}, "parcial"),
        ({"status": "canceled", "filled": 0}, "cancelada"),
        ({"status": "expired", "filled": 0.2}, "parcial"),
        ({"status": "rejected"}, "rechazada"),
        ({"status": None}, "desconocido"),
    ],
)
def test_estado_de_una_orden(crudo: dict[str, object], estado: str) -> None:
    assert estado_de(crudo) == estado


def test_que_errores_dejan_la_orden_en_el_aire() -> None:
    assert es_incierto(Ccxt.RequestTimeout("x"))
    assert es_incierto(Ccxt.BadResponse("x"))
    assert es_incierto(RuntimeError("x"))
    assert not es_incierto(Ccxt.InvalidNonce("x"))
    assert not es_incierto(Ccxt.InsufficientFunds("x"))


# -- Permisos -------------------------------------------------------------------------------------


class TestPermisos:
    def test_binance(self) -> None:
        sin = permisos_binance({"enableWithdrawals": False, "enableSpotAndMarginTrading": True})
        con = permisos_binance({"enableWithdrawals": True, "enableSpotAndMarginTrading": True})
        assert (sin.operar, sin.retirar) == (True, False)
        assert con.retirar is True
        assert "PUEDE RETIRAR" in con.texto

    def test_binance_en_pruebas_no_lo_sabe(self) -> None:
        p = conector(red="pruebas").permisos()
        assert (p.operar, p.retirar) == (None, None)
        assert "red de pruebas de Binance no dice" in p.texto

    def test_binance_real_pregunta_a_api_restrictions(self) -> None:
        ex = CcxtFalso()
        ex.sapiGetAccountApiRestrictions = lambda params: {  # type: ignore[attr-defined]
            "enableWithdrawals": False,
            "enableSpotAndMarginTrading": True,
        }
        p = conector(ex, red="real").permisos()
        assert (p.operar, p.retirar) == (True, False)

    def test_si_no_se_pueden_leer_es_none_y_lo_dice(self) -> None:
        ex = CcxtFalso()

        def falla(params: object) -> object:
            raise Ccxt.NetworkError("caído")

        ex.sapiGetAccountApiRestrictions = falla  # type: ignore[attr-defined]
        p = conector(ex, red="real").permisos()
        assert (p.operar, p.retirar) == (None, None)
        assert "No se pudieron leer los permisos" in p.texto

    def test_bybit(self) -> None:
        base = {"readOnly": 0, "permissions": {"Spot": ["SpotTrade"], "Wallet": []}}
        assert permisos_bybit({"result": base}).retirar is False
        assert permisos_bybit({"result": base}).operar is True
        con = {"readOnly": 0, "permissions": {"Spot": ["SpotTrade"], "Wallet": ["Withdraw"]}}
        assert permisos_bybit({"result": con}).retirar is True
        lectura = {"readOnly": 1, "permissions": {"Spot": ["SpotTrade"]}}
        assert permisos_bybit({"result": lectura}).operar is False

    def test_okx(self) -> None:
        assert permisos_okx({"data": [{"perm": "read_only,trade"}]}).retirar is False
        assert permisos_okx({"data": [{"perm": "read_only,trade,withdraw"}]}).retirar is True
        assert permisos_okx({"data": []}).retirar is None

    def test_kraken(self) -> None:
        sin = permisos_kraken({"result": {"permissions": ["query-funds", "modify-trades"]}})
        con = permisos_kraken({"result": {"permissions": ["modify-trades", "withdraw-funds"]}})
        assert (sin.operar, sin.retirar) == (True, False)
        assert con.retirar is True

    def test_coinbase(self) -> None:
        sin = permisos_coinbase({"can_view": True, "can_trade": True, "can_transfer": False})
        con = permisos_coinbase({"can_trade": True, "can_transfer": True})
        assert (sin.operar, sin.retirar) == (True, False)
        assert con.retirar is True
        assert permisos_coinbase({}).retirar is None

    def test_hyperliquid_la_clave_de_la_cartera_principal_puede_retirar(self) -> None:
        cartera = "0x" + "ab" * 20
        p = permisos_hyperliquid(cartera, cartera.upper().replace("0X", "0x"), [])
        assert p.retirar is True
        assert "cartera principal" in p.texto

    def test_hyperliquid_una_api_wallet_aprobada(self) -> None:
        agente = "0x" + "cd" * 20
        p = permisos_hyperliquid("0x" + "ab" * 20, agente, [{"address": agente, "name": "bot"}])
        assert (p.operar, p.retirar) == (True, False)

    def test_hyperliquid_una_api_wallet_sin_aprobar(self) -> None:
        p = permisos_hyperliquid("0x" + "ab" * 20, "0x" + "cd" * 20, [])
        assert (p.operar, p.retirar) == (False, False)
        assert "no está aprobada" in p.texto

    def test_hyperliquid_desde_el_conector(self) -> None:
        cartera = "0x" + "ab" * 20
        clave = "0x" + "11" * 12 + "cd" * 20
        ex = CcxtFalso(walletAddress=cartera, privateKey=clave)
        ex.publicPostInfo = lambda params: [{"address": "0x" + "cd" * 20}]  # type: ignore[attr-defined]
        p = conector(
            ex, HYPERLIQUID, claves={"walletAddress": cartera, "privateKey": clave}
        ).permisos()
        assert (p.operar, p.retirar) == (True, False)


# -- Ninguna clave en ningún mensaje -------------------------------------------------------------


class TestSinClaves:
    def test_limpiar_quita_los_valores_y_lo_que_parece_una_clave(self) -> None:
        assert SECRETO not in limpiar(f"error con {SECRETO} dentro", [SECRETO])
        assert "apikey" in limpiar("apiKey=XYZ falló").lower()
        assert "XYZ" not in limpiar("apiKey=XYZ falló")
        assert len(limpiar("x" * 1000)) == 200

    def test_ningun_error_del_conector_lleva_el_secreto(self) -> None:
        errores: list[str] = []
        for fallo in (
            Ccxt.InvalidOrder(f"binance {{'secret': '{SECRETO}'}}"),
            Ccxt.ExchangeError(f"rechazada {SECRETO}"),
            Ccxt.AuthenticationError(f"firma {SECRETO}"),
        ):
            ex = CcxtFalso(fallo_al_crear=fallo)
            with pytest.raises(ExchangeError) as error:
                conector(ex).enviar("BTC/USDT", "compra", D("0.001"), id_cliente="bot-1")
            errores.append(str(error.value))
            assert error.value.__cause__ is None
        assert all(SECRETO not in e for e in errores), errores

    def test_el_repr_del_conector_no_lleva_las_claves(self) -> None:
        assert SECRETO not in repr(conector())
