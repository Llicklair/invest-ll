"""Lo que decide cada plantilla, y por qué, con series sintéticas. Sin mirar el futuro."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

import pytest

from invest_ll.bots import decisiones
from invest_ll.bots.decisiones import (
    Decision,
    Orden,
    Situacion,
    aplicar_rejilla,
    cerradas,
    niveles_rejilla,
)

from .bots_apoyo import INICIO, onda, serie, vela

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    from invest_ll.vivo.fuente import Vela

D = Decimal
TENDENCIA = {"media_corta": "3", "media_larga": "5", "intervalo": "1h"}


def situacion(
    *,
    velas: Mapping[str, Sequence[Vela]] | None = None,
    efectivo: str = "1000",
    posiciones: Mapping[str, Decimal] | None = None,
    parametros: Mapping[str, str] = TENDENCIA,
    monedas: tuple[str, ...] = ("BTC",),
    precios: Mapping[str, Decimal] | None = None,
    memoria: Mapping[str, str] | None = None,
    ahora_indice: int | None = None,
) -> Situacion:
    todas = velas or {}
    if ahora_indice is not None:
        ahora = INICIO + timedelta(hours=ahora_indice)
    else:
        ultimas = [v[-1].fin for v in todas.values() if v]
        ahora = max(ultimas) if ultimas else INICIO
    return Situacion(
        ahora=ahora,
        capital=D(1000),
        monedas=monedas,
        parametros=parametros,
        efectivo=D(efectivo),
        posiciones=posiciones or {},
        precios=precios or {},
        velas=todas,
        memoria=memoria or {},
    )


def ordenes(d: Decision) -> list[tuple[str, str]]:
    return [(o.coin, o.lado) for o in d.ordenes]


class TestCerradas:
    def test_la_vela_en_curso_no_cuenta(self) -> None:
        velas = [
            *serie("BTC", "1h", [1, 2, 3]),
            vela("BTC", "1h", INICIO + timedelta(hours=3), 9, cerrada=False),
        ]
        assert [v.cierre for v in cerradas(velas, INICIO + timedelta(hours=3, minutes=30))] == [
            1,
            2,
            3,
        ]

    def test_una_vela_que_cierra_despues_de_ahora_no_se_conoce(self) -> None:
        """Aunque la fuente la diera por cerrada (por un fallo): termina en el futuro."""
        velas = serie("BTC", "1h", [1, 2, 3, 4])
        assert len(cerradas(velas, INICIO + timedelta(hours=2))) == 2


class TestTendencia:
    def test_compra_cuando_la_corta_cruza_por_encima(self) -> None:
        velas = {"BTC": serie("BTC", "1h", [10, 9, 8, 7, 6, 5, 9, 12])}
        d = decisiones.tendencia(situacion(velas=velas))
        assert ordenes(d) == [("BTC", "compra")]
        assert d.ordenes[0].porque == "la media de 3 velas cruzó por encima de la de 5"
        assert d.ordenes[0].fraccion == 1

    def test_vende_cuando_cruza_por_debajo(self) -> None:
        velas = {"BTC": serie("BTC", "1h", [5, 6, 7, 8, 9, 10, 6, 3])}
        d = decisiones.tendencia(situacion(velas=velas, posiciones={"BTC": D(1)}))
        assert ordenes(d) == [("BTC", "venta")]
        assert d.ordenes[0].porque == "la media de 3 velas cruzó por debajo de la de 5"

    def test_si_ya_estaba_por_encima_lo_dice_sin_hablar_de_cruce(self) -> None:
        """Al desplegarlo en plena subida compra, pero no se inventa un cruce que no ha visto."""
        velas = {"BTC": serie("BTC", "1h", [1, 2, 3, 4, 5, 6, 7, 8])}
        d = decisiones.tendencia(situacion(velas=velas))
        assert d.ordenes[0].porque == "la media de 3 velas está por encima de la de 5"

    def test_dentro_y_subiendo_no_hace_nada(self) -> None:
        velas = {"BTC": serie("BTC", "1h", [1, 2, 3, 4, 5, 6, 7, 8])}
        assert decisiones.tendencia(situacion(velas=velas, posiciones={"BTC": D(1)})).ordenes == ()

    def test_sin_historia_bastante_espera_y_lo_dice(self) -> None:
        d = decisiones.tendencia(situacion(velas={"BTC": serie("BTC", "1h", [1, 2, 3])}))
        assert d.ordenes == ()
        assert d.notas == ("Esperando historia de BTC: necesita 5 velas de 1h cerradas.",)

    def test_con_varias_monedas_cada_una_tiene_su_parte(self) -> None:
        sube = [1, 2, 3, 4, 5, 6, 7, 8]
        velas = {"BTC": serie("BTC", "1h", sube), "ETH": serie("ETH", "1h", sube)}
        d = decisiones.tendencia(situacion(velas=velas, monedas=("BTC", "ETH")))
        assert [o.fraccion for o in d.ordenes] == [D(1) / 2, D(1) / 2]

    def test_la_parte_de_una_moneda_que_se_vende_no_se_la_come_la_otra(self) -> None:
        velas = {
            "BTC": serie("BTC", "1h", [5, 6, 7, 8, 9, 10, 6, 3]),
            "ETH": serie("ETH", "1h", [10, 9, 8, 7, 6, 5, 9, 12]),
        }
        d = decisiones.tendencia(
            situacion(velas=velas, monedas=("BTC", "ETH"), posiciones={"BTC": D(1)}, efectivo="0")
        )
        assert ordenes(d) == [("BTC", "venta"), ("ETH", "compra")]
        assert d.ordenes[1].fraccion == D(1) / 2

    def test_sin_efectivo_para_el_minimo_no_propone_comprar(self) -> None:
        velas = {"BTC": serie("BTC", "1h", [10, 9, 8, 7, 6, 5, 9, 12])}
        assert decisiones.tendencia(situacion(velas=velas, efectivo="9.99")).ordenes == ()


class TestSinMirarElFuturo:
    """Alterar lo que viene después no puede cambiar una decisión ya tomada."""

    def _decisiones(self, cierres: list[float]) -> list[list[tuple[str, str]]]:
        todas = serie("BTC", "1h", cierres)
        resultado: list[list[tuple[str, str]]] = []
        posiciones: dict[str, Decimal] = {}
        for i in range(6, 60):
            # La fuente le da TODAS las velas, también las futuras marcadas como cerradas.
            s = situacion(velas={"BTC": todas}, posiciones=posiciones, ahora_indice=i)
            d = decisiones.tendencia(s)
            resultado.append(ordenes(d))
            for o in d.ordenes:
                posiciones = {"BTC": D(1)} if o.lado == "compra" else {}
        return resultado

    def test_cambiar_las_velas_posteriores_no_cambia_las_decisiones_anteriores(self) -> None:
        base = onda(80, periodo=20)
        otra = base[:40] + [200 - p for p in base[40:]]  # la onda al revés desde la vela 40
        antes, despues = self._decisiones(base), self._decisiones(otra)
        hasta = 40 - 6  # las decisiones tomadas con velas hasta la 39
        assert antes[:hasta] == despues[:hasta]
        assert any(antes[:hasta]), "la serie no daba ninguna orden: el test pasaría por vacío"
        assert antes != despues, "las velas cambiadas no cambian nada: el test no demuestra nada"

    def test_btc_freno_tampoco_mira_el_futuro(self) -> None:
        cierres = [100.0 + i for i in range(40)]
        todas = serie("BTC", "1d", cierres)
        hundidas = todas[:35] + serie("BTC", "1d", [1.0] * 5, todas[35].inicio)
        ahora = todas[34].fin
        params = {"dias": "30"}
        con_todas = decisiones.btc_freno(situacion(velas={"BTC": todas}, parametros=params))
        normal = replace(situacion(velas={"BTC": todas}, parametros=params), ahora=ahora)
        hundida = replace(situacion(velas={"BTC": hundidas}, parametros=params), ahora=ahora)
        assert ordenes(decisiones.btc_freno(normal)) == ordenes(decisiones.btc_freno(hundida))
        assert ordenes(con_todas) == [("BTC", "compra")]


class TestBtcFreno:
    PARAMS: ClassVar = {"dias": "30"}

    def test_dentro_si_vale_mas_que_hace_30_dias(self) -> None:
        velas = {"BTC": serie("BTC", "1d", [100.0 + i for i in range(31)], INICIO)}
        d = decisiones.btc_freno(situacion(velas=velas, parametros=self.PARAMS))
        assert ordenes(d) == [("BTC", "compra")]
        assert d.ordenes[0].porque == "Bitcoin vale un +30,0 % respecto a hace 30 días"

    def test_fuera_si_vale_menos(self) -> None:
        velas = {"BTC": serie("BTC", "1d", [130.0 - i for i in range(31)])}
        d = decisiones.btc_freno(
            situacion(velas=velas, parametros=self.PARAMS, posiciones={"BTC": D(1)})
        )
        assert ordenes(d) == [("BTC", "venta")]
        assert d.ordenes[0].porque.endswith("respecto a hace 30 días: paso a USDC")

    def test_compara_con_la_vela_de_hace_exactamente_dias_velas(self) -> None:
        """La regla de TrendAsset: el último cierre contra el de `dias` velas antes."""
        cierres = [100.0] + [50.0] * 29 + [100.5]
        velas = {"BTC": serie("BTC", "1d", cierres)}
        assert ordenes(decisiones.btc_freno(situacion(velas=velas, parametros=self.PARAMS))) == [
            ("BTC", "compra")
        ]

    def test_sin_historia_espera(self) -> None:
        velas = {"BTC": serie("BTC", "1d", [100.0] * 10)}
        d = decisiones.btc_freno(situacion(velas=velas, parametros=self.PARAMS))
        assert d.ordenes == ()
        assert d.notas


class TestRejilla:
    PARAMS: ClassVar = {"precio_bajo": "90", "precio_alto": "110", "escalones": "4"}

    def s(
        self, precio: float, memoria: Mapping[str, str] | None = None, efectivo: str = "1000"
    ) -> Situacion:
        return situacion(
            parametros=self.PARAMS,
            precios={"BTC": D(str(precio))},
            memoria=memoria,
            efectivo=efectivo,
        )

    def test_los_niveles_reparten_el_rango(self) -> None:
        assert niveles_rejilla(D(90), D(110), 4) == [D(90), D(95), D(100), D(105), D(110)]

    def test_al_arrancar_compra_los_escalones_de_encima_del_precio(self) -> None:
        d = decisiones.rejilla(self.s(99))
        (orden,) = d.ordenes
        assert orden.lado == "compra"
        assert orden.escalones == (2, 3)
        assert orden.importe == D(500)
        assert d.memoria == {"fuera": "", "iniciada": "si"}

    def test_compra_un_escalon_cuando_el_precio_baja_a_el(self) -> None:
        memoria = {"iniciada": "si", "escalon_2": "1", "escalon_3": "1"}
        d = decisiones.rejilla(self.s(94.9, memoria))
        (orden,) = d.ordenes
        assert (orden.lado, orden.escalones, orden.importe) == ("compra", (1,), D(250))
        assert orden.porque == "el precio bajó a 95,00: compro el escalón 2 de 4"

    def test_vende_un_escalon_cuando_el_precio_sube_al_siguiente(self) -> None:
        memoria = {"iniciada": "si", "escalon_1": "2.5", "escalon_2": "1", "escalon_3": "1"}
        d = decisiones.rejilla(self.s(100.1, memoria))
        (orden,) = d.ordenes
        assert (orden.lado, orden.escalones, orden.cantidad) == ("venta", (1,), D("2.5"))
        assert (
            orden.porque == "el precio subió a 100,00: vendo el escalón 2 de 4, comprado más abajo"
        )

    def test_entre_dos_niveles_no_hace_nada(self) -> None:
        memoria = {"iniciada": "si", "escalon_2": "1", "escalon_3": "1"}
        assert decisiones.rejilla(self.s(97, memoria)).ordenes == ()

    def test_sin_precio_no_decide(self) -> None:
        assert decisiones.rejilla(situacion(parametros=self.PARAMS)) == Decision()

    def test_fuera_del_rango_por_abajo_lo_avisa_una_vez(self) -> None:
        memoria = {"iniciada": "si", **{f"escalon_{k}": "1" for k in range(4)}}
        d = decisiones.rejilla(self.s(80, memoria))
        assert d.aviso is not None
        assert "por debajo del rango (90,00 a 110,00)" in d.aviso
        assert d.notas == (d.aviso,)
        siguiente = decisiones.rejilla(self.s(79, {**memoria, **(d.memoria or {})}))
        assert siguiente.notas == ()
        assert siguiente.aviso is not None

    def test_al_volver_al_rango_lo_cuenta(self) -> None:
        memoria = {"iniciada": "si", "fuera": "abajo", **{f"escalon_{k}": "1" for k in range(4)}}
        d = decisiones.rejilla(self.s(91, memoria))
        assert d.notas == ("El precio volvió al rango (90,00 a 110,00).",)

    def test_aplicar_reparte_lo_comprado_entre_sus_escalones(self) -> None:
        orden = Orden("BTC", "compra", "x", importe=D(500), escalones=(2, 3))
        memoria = aplicar_rejilla({}, orden, D("0.00000003"))
        assert memoria == {"escalon_2": "1E-8", "escalon_3": "2E-8"}
        assert sum(D(v) for v in memoria.values()) == D("0.00000003")
        vendida = aplicar_rejilla(memoria, Orden("BTC", "venta", "x", escalones=(2,)), D(1))
        assert vendida["escalon_2"] == "0"


class TestPeriodica:
    PARAMS: ClassVar = {"importe": "100", "cada_horas": "24"}

    def test_compra_al_desplegar_y_apunta_la_siguiente(self) -> None:
        d = decisiones.periodica(situacion(parametros=self.PARAMS))
        assert ordenes(d) == [("BTC", "compra")]
        assert d.ordenes[0].importe == D(100)
        assert d.ordenes[0].porque == "toca la compra de cada 24 horas (100,00 USDC)"
        assert d.memoria == {
            "proxima": (INICIO + timedelta(hours=24)).isoformat(),
            "sin_efectivo": "",
        }

    def test_antes_de_su_hora_no_compra(self) -> None:
        memoria = {"proxima": (INICIO + timedelta(hours=1)).isoformat()}
        assert (
            decisiones.periodica(situacion(parametros=self.PARAMS, memoria=memoria)).ordenes == ()
        )

    def test_si_se_salto_compras_no_las_recupera(self) -> None:
        """Con el panel cerrado tres días: una compra, y la siguiente según su horario."""
        proxima = INICIO
        memoria = {"proxima": proxima.isoformat()}
        s = replace(
            situacion(parametros=self.PARAMS, memoria=memoria),
            ahora=INICIO + timedelta(days=3, hours=5),
        )
        d = decisiones.periodica(s)
        assert len(d.ordenes) == 1
        assert d.memoria is not None
        assert d.memoria["proxima"] == (INICIO + timedelta(days=4)).isoformat()

    def test_con_varias_monedas_reparte_y_no_repite_la_que_ya_compro(self) -> None:
        s = situacion(parametros=self.PARAMS, monedas=("BTC", "ETH"))
        d = decisiones.periodica(s)
        assert [(o.coin, o.importe) for o in d.ordenes] == [("BTC", D(50)), ("ETH", D(50))]
        # BTC se compró y ETH esperaba libro: al reintentar solo va ETH.
        memoria = dict(d.ordenes[0].memoria)
        reintento = decisiones.periodica(replace(s, memoria=memoria))
        assert ordenes(reintento) == [("ETH", "compra")]

    def test_cuando_se_acaba_el_efectivo_lo_dice_una_vez_y_deja_de_comprar(self) -> None:
        d = decisiones.periodica(situacion(parametros=self.PARAMS, efectivo="9"))
        assert d.ordenes == ()
        assert len(d.notas) == 1
        assert d.aviso is not None
        assert d.memoria is not None
        luego = decisiones.periodica(
            replace(
                situacion(parametros=self.PARAMS, efectivo="9", memoria=d.memoria),
                ahora=INICIO + timedelta(days=2),
            )
        )
        assert luego.notas == ()
        assert luego.ordenes == ()

    def test_lo_que_queda_se_gasta_si_llega_al_minimo(self) -> None:
        d = decisiones.periodica(situacion(parametros=self.PARAMS, efectivo="40"))
        assert d.ordenes[0].importe == D(40)


@pytest.mark.parametrize(
    ("precio", "texto"),
    [(D("67010.4"), "67.010"), (D("2.5"), "2,50"), (D("0.00001234"), "0,00001234")],
)
def test_los_precios_en_los_motivos_se_leen_como_en_espana(precio: Decimal, texto: str) -> None:
    assert decisiones.precio_txt(precio) == texto
