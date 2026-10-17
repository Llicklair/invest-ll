"""La API del panel v2: el plan, qué toca hoy, anotar lo hecho, el inicio y los movimientos."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from invest_ll import llano
from invest_ll.estrategias import objetivo
from invest_ll.estrategias.catalogo import Ficha
from invest_ll.plan import servicio
from invest_ll.portfolio.store import ActivityStore

from ..fixtures.paneles_v2 import escribir_paneles
from .api_apoyo import Api

D = Decimal
HOY = date(2026, 10, 17)
PARTES = [
    {"estrategia": "bolsa-equilibrada", "inicial": "5400", "mensual": "180"},
    {"estrategia": "btc-freno", "inicial": "600", "mensual": "20"},
]
PLAN = {"partes": PARTES, "dia_del_mes": 1}


@pytest.fixture
def con_plan(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> Api:
    escribir_paneles()
    monkeypatch.setattr(servicio, "hoy_local", lambda: HOY)
    assert cliente.put("/api/plan", json=PLAN).status_code == 200
    return cliente


class TestPlan:
    def test_sin_plan(self, cliente: Api) -> None:
        assert cliente.get("/api/plan").json() == {"plan": None}
        hoy = cliente.get("/api/plan/hoy").json()
        assert hoy["sin_plan"] is True
        assert hoy["acciones"] == []
        assert hoy["modo"] == "simulacion"
        assert cliente.delete("/api/plan").status_code == 404

    def test_guardar_leer_y_borrar(self, cliente: Api) -> None:
        guardado = cliente.put("/api/plan", json=PLAN).json()["plan"]
        assert guardado["dia_del_mes"] == 1
        assert guardado["partes"][0] == PARTES[0]
        assert Path("plan/plan.json").exists()
        assert cliente.get("/api/plan").json()["plan"] == guardado
        assert cliente.delete("/api/plan").status_code == 204
        assert cliente.get("/api/plan").json() == {"plan": None}

    def test_reemplazar_conserva_la_fecha_de_creacion(self, cliente: Api) -> None:
        primero = cliente.put("/api/plan", json=PLAN).json()["plan"]
        segundo = cliente.put("/api/plan", json={**PLAN, "dia_del_mes": 5}).json()["plan"]
        assert segundo["creado"] == primero["creado"]
        assert segundo["dia_del_mes"] == 5

    @pytest.mark.parametrize(
        ("partes", "motivo"),
        [
            (["bolsa-equilibrada", "bolsa-eeuu"], "como mucho una estrategia de bolsa"),
            (["cripto-prerregistrada"], "Laboratorio"),
            (["cripto-rotacion"], "retirada"),
            (["no-existe"], "no hay ninguna"),
        ],
    )
    def test_lo_que_no_vale_es_422(self, cliente: Api, partes: list[str], motivo: str) -> None:
        plan = {
            "partes": [{"estrategia": p, "inicial": "1", "mensual": "1"} for p in partes],
            "dia_del_mes": 1,
        }
        r = cliente.put("/api/plan", json=plan)
        assert r.status_code == 422
        assert motivo in r.json()["detail"]
        assert not Path("plan/plan.json").exists()


class TestHoy:
    def test_que_toca_con_un_plan_recien_creado(self, con_plan: Api) -> None:
        hoy = con_plan.get("/api/plan/hoy").json()

        assert hoy["sin_plan"] is False
        donde = [(a["donde"], a["simbolo"], a["lado"]) for a in hoy["acciones"]]
        assert donde == [
            ("binance", "BTC/USDT", "buy"),
            ("broker", "SPY", "buy"),
            ("broker", "IEF", "buy"),
        ]
        btc, spy, ief = hoy["acciones"]
        assert D(btc["importe"]) == pytest.approx(D(620), abs=D(1))
        assert btc["par"] == "BTC/USDT" and btc["moneda"] == "USDT"
        assert (btc["precio_ref_moneda"], btc["referencia"]) == ("USDT", None)
        assert (spy["moneda"], spy["precio_ref_moneda"], spy["referencia"]) == ("EUR", "USD", "SPY")
        assert D(spy["importe"]) == D("3348.00")
        assert D(ief["importe"]) == D("2232.00")
        assert "IE00B5BMR087" in spy["equivalente"]
        assert hoy["resumen"] == "Hoy toca: 1 orden en Binance y 2 compras en tu bróker."
        assert hoy["proxima_fecha"] == "2026-11-01"

    def test_los_ids_son_estables(self, con_plan: Api) -> None:
        primera = [a["id"] for a in con_plan.get("/api/plan/hoy").json()["acciones"]]
        segunda = [a["id"] for a in con_plan.get("/api/plan/hoy").json()["acciones"]]
        assert primera == segunda

    def test_anotar_lo_comprado_en_el_broker(self, con_plan: Api) -> None:
        spy = con_plan.get("/api/plan/hoy").json()["acciones"][1]
        # Un ETF europeo a otro precio: 6 participaciones a 550 = 3300 pagados.
        hecha = {"cantidad": "6", "precio": "550", "comision": "2", "fecha": "2026-10-17"}

        r = con_plan.post(f"/api/plan/hoy/{spy['id']}/hecho", json=hecha)

        assert r.status_code == 201
        quedan = [a["simbolo"] for a in con_plan.get("/api/plan/hoy").json()["acciones"]]
        assert quedan == ["BTC/USDT", "IEF"]
        (mov,) = con_plan.get("/api/cartera/movimientos").json()["movimientos"]
        assert mov["origen"] == "plan"
        assert mov["simbolo"] == "SPY"
        assert mov["activo"] == "Bolsa de EE.UU."
        assert D(mov["importe"]) == pytest.approx(D(3300), abs=D("0.01")), "lo pagado, exacto"
        assert D(mov["precio"]) == D(spy["precio_ref"]), "en unidades del fondo de referencia"
        assert D(mov["comision"]) == D(2)
        assert (mov["moneda"], mov["es_referencia"]) == ("EUR", True), "lo que pagaste"
        unidades = (D(3300) / D(spy["precio_ref"])).quantize(D("0.01"), ROUND_HALF_UP)
        assert mov["nota"] == (
            f"Compraste 6 participaciones a 550 € en tu bróker; se anota como "
            f"{llano.cantidad(unidades)} de SPY (el fondo de EE.UU. de referencia) a "
            f"{llano.dinero(D(spy['precio_ref']), 'USD')} para poder valorarlo."
        )
        (posicion,) = con_plan.get("/api/cartera").json()["abiertas"]
        assert (posicion["activo"], posicion["es_referencia"]) == ("SPY", True), (
            "sus unidades no son tus participaciones: se enseñan importes"
        )
        assert posicion["moneda"] == "EUR", "sus importes son lo que pagaste, sin convertir"

    def test_la_nota_no_cambia_la_huella(self, con_plan: Api) -> None:
        """Anotar dos veces lo mismo sigue siendo imposible aunque la nota sea otra."""
        spy = con_plan.get("/api/plan/hoy").json()["acciones"][1]
        hecha = {"cantidad": "6", "precio": "550", "comision": "2", "fecha": "2026-10-17"}
        r = con_plan.post(f"/api/plan/hoy/{spy['id']}/hecho", json=hecha)
        (mov,) = con_plan.get("/api/cartera/movimientos").json()["movimientos"]
        assert mov["id"] == r.json()["activity_id"]
        (actividad,) = ActivityStore().activities()
        assert actividad.nota is not None
        assert actividad.activity_id == replace(actividad, nota=None).activity_id

    def test_lo_del_broker_es_dinero_real_en_cualquier_modo(
        self, con_plan: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El modo es de Binance; tu bróker es siempre dinero de verdad.

        Caso real del panel: con la compra del bróker ya anotada, al pasar a modo pruebas volvía a
        salir como pendiente, y "Ya lo he comprado" la apuntaba en la cartera de dinero ficticio;
        al volver a simulación, otra vez pendiente: invitaba a comprarla dos veces.
        """
        spy = con_plan.get("/api/plan/hoy").json()["acciones"][1]
        hecha = {"cantidad": "6", "precio": "550", "comision": "2", "fecha": "2026-10-17"}
        assert con_plan.post(f"/api/plan/hoy/{spy['id']}/hecho", json=hecha).status_code == 201

        monkeypatch.setenv("INVEST_LL_MODE", "testnet")
        monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "clave")
        monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "secreto")
        en_pruebas = con_plan.get("/api/plan/hoy").json()
        assert en_pruebas["modo"] == "pruebas"
        assert [a["simbolo"] for a in en_pruebas["acciones"]] == ["BTC/USDT", "IEF"]

        ief = en_pruebas["acciones"][1]
        assert con_plan.post(f"/api/plan/hoy/{ief['id']}/hecho", json=hecha).status_code == 201
        assert not Path("portfolio-pruebas/activities.jsonl").exists(), "nada a la de pruebas"
        assert [a["simbolo"] for a in con_plan.get("/api/plan/hoy").json()["acciones"]] == [
            "BTC/USDT"
        ]

        monkeypatch.delenv("INVEST_LL_MODE")
        monkeypatch.delenv("INVEST_LL_TESTNET_KEY")
        monkeypatch.delenv("INVEST_LL_TESTNET_SECRET")
        quedan = [a["simbolo"] for a in con_plan.get("/api/plan/hoy").json()["acciones"]]
        assert quedan == ["BTC/USDT"], "de vuelta en simulación, las dos siguen hechas"

    def test_las_de_binance_no_se_anotan_a_mano(self, con_plan: Api) -> None:
        btc = con_plan.get("/api/plan/hoy").json()["acciones"][0]
        hecha = {"cantidad": "0.01", "precio": "60000", "comision": "0", "fecha": "2026-10-17"}
        r = con_plan.post(f"/api/plan/hoy/{btc['id']}/hecho", json=hecha)
        assert r.status_code == 422
        assert "Binance" in r.json()["detail"]
        assert con_plan.get("/api/cartera/movimientos").json()["movimientos"] == []

    def test_id_desconocido_404(self, con_plan: Api) -> None:
        hecha = {"cantidad": "1", "precio": "1", "comision": "0", "fecha": "2026-10-17"}
        assert con_plan.post("/api/plan/hoy/nada/hecho", json=hecha).status_code == 404

    @pytest.mark.parametrize("fecha", ["2026-10-18", "2026-09-30"])
    def test_fechas_fuera_del_periodo_422(self, con_plan: Api, fecha: str) -> None:
        spy = con_plan.get("/api/plan/hoy").json()["acciones"][1]
        hecha = {"cantidad": "1", "precio": "550", "comision": "0", "fecha": fecha}
        assert con_plan.post(f"/api/plan/hoy/{spy['id']}/hecho", json=hecha).status_code == 422

    def test_sin_datos_lo_dice_y_no_inventa(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(servicio, "hoy_local", lambda: HOY)
        cliente.put("/api/plan", json=PLAN)
        hoy = cliente.get("/api/plan/hoy").json()
        assert hoy["acciones"] == []
        assert any("invest-ll-quant download --etf" in a for a in hoy["avisos"])
        assert any(a.endswith("uv run invest-ll-quant download") for a in hoy["avisos"])

    def test_datos_viejos_se_avisan(self, cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
        escribir_paneles()
        monkeypatch.setattr(servicio, "hoy_local", lambda: date(2026, 11, 2))
        cliente.put("/api/plan", json=PLAN)
        avisos = cliente.get("/api/plan/hoy").json()["avisos"]
        assert any("son del 16 oct 2026" in a for a in avisos)


class TestInicio:
    def test_sin_nada(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/inicio").json()
        assert cuerpo["plan"] is None
        assert cuerpo["hay_movimientos"] is False
        assert cuerpo["acciones_pendientes"] == 0
        assert cuerpo["patrimonio"]["cartera"] == "real"
        assert cuerpo["patrimonio"]["efectivo"] == "0"
        assert cuerpo["patrimonio"]["moneda"] == "EUR"
        assert cuerpo["patrimonio"]["nota_moneda"] is None, "nada que convertir"
        assert cuerpo["mercado"] == []

    def test_con_plan_y_una_compra(self, con_plan: Api) -> None:
        spy = con_plan.get("/api/plan/hoy").json()["acciones"][1]
        hecha = {"cantidad": "6", "precio": "550", "comision": "2", "fecha": "2026-10-17"}
        con_plan.post(f"/api/plan/hoy/{spy['id']}/hecho", json=hecha)

        cuerpo = con_plan.get("/api/inicio").json()

        assert cuerpo["hay_movimientos"] is True
        assert cuerpo["acciones_pendientes"] == 2
        assert cuerpo["proxima_fecha"] == "2026-11-01"
        p = cuerpo["patrimonio"]
        assert D(p["puesto"]) == pytest.approx(D(3302), abs=D("0.01"))
        assert D(p["valor"]) == pytest.approx(D(3300), abs=D("0.01")), "al precio de referencia"
        assert p["fecha_precios"] == "2026-10-16"
        assert p["incompleto"] is False
        assert (p["moneda"], p["efectivo"]) == ("EUR", "0")
        assert p["nota_moneda"] == "Aproximado: sin contar el cambio euro-dólar."
        equilibrada, btc = cuerpo["plan"]
        assert equilibrada["estrategia"] == "bolsa-equilibrada"
        assert (equilibrada["moneda"], btc["moneda"]) == ("EUR", "USDT")
        assert D(equilibrada["puesto"]) == pytest.approx(D(3302), abs=D("0.01"))
        assert D(btc["puesto"]) == 0
        assert [m["nombre"] for m in cuerpo["mercado"]] == [
            "Bitcoin",
            "Bolsa de EE.UU.",
            "Oro",
            "Bonos del Tesoro de EE.UU. a 7-10 años",
        ]
        assert all(m["var_1m"] is not None for m in cuerpo["mercado"])
        assert not any("USDT en tu cuenta" in a for a in cuerpo["avisos"])


# -- Ventas en el bróker ------------------------------------------------------------------------

PRUDENTE = {
    "partes": [{"estrategia": "bolsa-prudente", "inicial": "10000", "mensual": "0"}],
    "dia_del_mes": 1,
}
DE_HOY = objetivo.de_hoy


def _quiere(monkeypatch: pytest.MonkeyPatch, pesos: dict[str, float]) -> None:
    """Lo que la Prudente quiere hoy, fijado: así se ve qué pasa cuando deja fuera un fondo."""

    def de_hoy(f: Ficha) -> objetivo.Objetivo | None:
        if f.clave != "bolsa-prudente":
            return DE_HOY(f)
        return objetivo.Objetivo(fecha=date(2026, 10, 16), pesos=dict(pesos))

    monkeypatch.setattr(objetivo, "de_hoy", de_hoy)


class TestVentasDelBroker:
    @pytest.fixture
    def con_eem(self, cliente: Api, monkeypatch: pytest.MonkeyPatch) -> Api:
        """Compró su inicial (40 % SPY, 20 % EEM, 40 % SHY) a 50 € la participación el día 16 (la
        aportación de octubre vence el 1); hoy, 17, la estrategia deja fuera los mercados
        emergentes."""
        escribir_paneles()
        monkeypatch.setattr(servicio, "hoy_local", lambda: HOY)
        _quiere(monkeypatch, {"SPY": 0.4, "EEM": 0.2, "SHY": 0.4})
        assert cliente.put("/api/plan", json=PRUDENTE).status_code == 200
        for a in cliente.get("/api/plan/hoy").json()["acciones"]:
            cantidad = D(a["importe"]) / 50
            hecha = {
                "cantidad": str(cantidad),
                "precio": "50",
                "comision": "0",
                "fecha": "2026-10-16",
            }
            assert cliente.post(f"/api/plan/hoy/{a['id']}/hecho", json=hecha).status_code == 201
        assert cliente.get("/api/plan/hoy").json()["acciones"] == []
        _quiere(monkeypatch, {"SPY": 0.5, "SHY": 0.5})
        return cliente

    def test_toca_vender_lo_que_sale_y_comprar_con_ello(self, con_eem: Api) -> None:
        hoy = con_eem.get("/api/plan/hoy").json()

        assert [(a["simbolo"], a["lado"]) for a in hoy["acciones"]] == [
            ("EEM", "sell"),
            ("SHY", "buy"),
            ("SPY", "buy"),
        ]
        venta, shy, spy = hoy["acciones"]
        assert venta["donde"] == "broker"
        assert venta["titulo"] == "Vende todo tu ETF de mercados emergentes (unos 2.000 €)"
        assert venta["explicacion"].startswith("Lleva meses bajando: tu estrategia sale de él")
        assert (venta["moneda"], venta["referencia"]) == ("EUR", "EEM")
        assert D(shy["importe"]) == pytest.approx(D(1000), abs=D("0.1"))
        assert D(spy["importe"]) == pytest.approx(D(1000), abs=D("0.1"))
        assert hoy["resumen"] == "Hoy toca: 1 venta y 2 compras en tu bróker."
        assert con_eem.get("/api/inicio").json()["acciones_pendientes"] == 3

    def test_anotar_la_venta(self, con_eem: Api) -> None:
        venta = con_eem.get("/api/plan/hoy").json()["acciones"][0]
        # El euro se ha movido: cobra 2.080 € por lo que el fondo de referencia valora en 2.000.
        hecha = {"cantidad": "40", "precio": "52", "comision": "1", "fecha": "2026-10-17"}

        r = con_eem.post(f"/api/plan/hoy/{venta['id']}/hecho", json=hecha)

        assert r.status_code == 201
        mov = con_eem.get("/api/cartera/movimientos").json()["movimientos"][0]
        assert (mov["tipo"], mov["simbolo"], mov["origen"]) == ("venta", "EEM", "plan")
        assert D(mov["importe"]) == pytest.approx(D(2080), abs=D("0.01")), "lo cobrado, exacto"
        assert (mov["moneda"], mov["es_referencia"]) == ("EUR", True)
        assert mov["nota"].startswith(
            "Vendiste 40 participaciones a 52 € en tu bróker; se anota como la venta de todo lo "
            "que tenías de EEM con tu plan"
        )
        # Ya no hay nada que vender; lo cobrado (menos la comisión) espera en la lista de la compra.
        hoy = con_eem.get("/api/plan/hoy").json()
        assert [(a["simbolo"], a["lado"]) for a in hoy["acciones"]] == [
            ("SHY", "buy"),
            ("SPY", "buy"),
        ]
        assert sum(D(a["importe"]) for a in hoy["acciones"]) == pytest.approx(D(2079), abs=D("0.1"))
        assert hoy["acciones"][0]["explicacion"].startswith(
            "Con lo que cobraste al vender y aún no has invertido"
        )

        cartera = con_eem.get("/api/cartera").json()
        assert D(cartera["efectivo_broker"]) == pytest.approx(D(2079), abs=D("0.01"))
        assert [p["activo"] for p in cartera["abiertas"]] == ["SHY", "SPY"]
        (eem,) = cartera["retiradas"]
        assert (eem["activo"], eem["moneda"]) == ("EEM", "EUR"), "pagado y cobrado en euros"
        assert D(eem["pnl_realizado"]) == pytest.approx(D(79), abs=D("0.01"))

        inicio = con_eem.get("/api/inicio").json()
        (prudente,) = inicio["plan"]
        assert D(prudente["efectivo"]) == pytest.approx(D(2079), abs=D("0.01"))
        assert D(prudente["valor"]) == pytest.approx(D(10079), abs=D("0.1"))
        p = inicio["patrimonio"]
        assert D(p["efectivo"]) == pytest.approx(D(2079), abs=D("0.01")), (
            "sin ingresos anotados el efectivo derivado sale negativo: lo cobrado se cuenta igual"
        )
        assert D(p["valor"]) == pytest.approx(D(10079), abs=D("0.1")), (
            "vender no hace bajar tu dinero"
        )

    def test_reinvertir_gasta_lo_cobrado(self, con_eem: Api) -> None:
        venta = con_eem.get("/api/plan/hoy").json()["acciones"][0]
        hecha = {"cantidad": "40", "precio": "50", "comision": "0", "fecha": "2026-10-17"}
        assert con_eem.post(f"/api/plan/hoy/{venta['id']}/hecho", json=hecha).status_code == 201
        shy = con_eem.get("/api/plan/hoy").json()["acciones"][0]
        compra = {"cantidad": "20", "precio": "50", "comision": "0", "fecha": "2026-10-17"}
        assert con_eem.post(f"/api/plan/hoy/{shy['id']}/hecho", json=compra).status_code == 201

        assert D(con_eem.get("/api/cartera").json()["efectivo_broker"]) == pytest.approx(
            D(1000), abs=D("0.01")
        )
        assert [a["simbolo"] for a in con_eem.get("/api/plan/hoy").json()["acciones"]] == ["SPY"]

    def test_vender_mas_de_lo_que_tienes_es_422_en_llano(self, con_eem: Api) -> None:
        venta = con_eem.get("/api/plan/hoy").json()["acciones"][0]
        hecha = {"cantidad": "100", "precio": "52", "comision": "0", "fecha": "2026-10-17"}

        r = con_eem.post(f"/api/plan/hoy/{venta['id']}/hecho", json=hecha)

        assert r.status_code == 422
        assert "es más de lo que tienes" in r.json()["detail"]
        movimientos = con_eem.get("/api/cartera/movimientos").json()["movimientos"]
        assert all(m["tipo"] == "compra" for m in movimientos), "no se anota nada"

    def test_una_venta_de_antes_de_comprar_es_422(self, con_eem: Api) -> None:
        venta = con_eem.get("/api/plan/hoy").json()["acciones"][0]
        hecha = {"cantidad": "40", "precio": "50", "comision": "0", "fecha": "2026-10-15"}
        r = con_eem.post(f"/api/plan/hoy/{venta['id']}/hecho", json=hecha)
        assert r.status_code == 422
        assert "no tienes nada" in r.json()["detail"]

    def test_la_fecha_de_la_venta_no_puede_ser_futura(self, con_eem: Api) -> None:
        venta = con_eem.get("/api/plan/hoy").json()["acciones"][0]
        hecha = {"cantidad": "40", "precio": "50", "comision": "0", "fecha": "2026-10-18"}
        r = con_eem.post(f"/api/plan/hoy/{venta['id']}/hecho", json=hecha)
        assert r.status_code == 422
        assert r.json()["detail"] == "La fecha de la venta no puede ser posterior a hoy."
