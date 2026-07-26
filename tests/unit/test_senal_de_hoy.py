"""Qué toca hacer hoy, según la política, con los datos de hoy.

El sistema sabía medir el pasado y sabía enviar órdenes, pero no unía las dos cosas: no había
forma de preguntarle **en qué deberías estar ahora**. Sin eso, la decisión seguía siendo tuya cada
semana, a ojo, que es justo lo que un backtest no puede validar.

Dos cosas que esta pieza se niega a hacer:

- **Callarse la edad de los datos.** Una señal calculada con precios de hace tres semanas no es una
  señal, es arqueología. La fecha del último dato viaja con la respuesta, siempre.
- **Recomendar sin filtro.** Si ningún activo sube, la respuesta es «fuera del mercado». Es la
  pieza que sobrevivió a la validación fuera de muestra, y la que evita el error clásico del
  momentum: quedarse siempre en «el que menos cae».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from invest_ll.data.universe import build_universe
from invest_ll.signal.today import senal_de_hoy

from ..fixtures.builders import series_from_closes

HOY = datetime(2026, 7, 26, tzinfo=UTC)


def universo(**series: list[float]):  # type: ignore[no-untyped-def]
    return build_universe(
        [series_from_closes(precios, symbol=simbolo) for simbolo, precios in series.items()]
    )


SUBE_MUCHO = [100.0 + i * 2 for i in range(60)]
SUBE_POCO = [100.0 + i * 0.2 for i in range(60)]
BAJA = [160.0 - i for i in range(60)]


class TestQueEligeHoy:
    def test_elige_el_que_mas_sube(self) -> None:
        s = senal_de_hoy(universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30)
        assert s.elegido == "AAA"
        assert s.en_mercado

    def test_si_ninguno_sube_se_queda_fuera(self) -> None:
        """El filtro: 'el que menos cae' sigue perdiendo dinero, solo que mas despacio."""
        s = senal_de_hoy(universo(AAA=BAJA, BBB=[160.0 - i * 2 for i in range(60)]), lookback=30)
        assert s.elegido is None
        assert not s.en_mercado

    def test_sin_filtro_elegiria_el_menos_malo(self) -> None:
        s = senal_de_hoy(
            universo(AAA=BAJA, BBB=[160.0 - i * 2 for i in range(60)]),
            lookback=30,
            min_return=None,
        )
        assert s.elegido == "AAA"


class TestLaEdadDeLosDatos:
    def test_dice_de_cuando_son_los_datos(self) -> None:
        s = senal_de_hoy(universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30)
        assert s.datos_hasta is not None

    def test_avisa_si_los_datos_estan_viejos(self) -> None:
        s = senal_de_hoy(
            universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30, ahora=HOY + timedelta(days=30)
        )
        assert s.dias_de_retraso >= 29
        assert s.datos_viejos

    def test_con_datos_recientes_no_avisa(self) -> None:
        u = universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO)
        s = senal_de_hoy(u, lookback=30, ahora=u.timestamps[-1] + timedelta(hours=6))
        assert not s.datos_viejos

    def test_el_aviso_aparece_en_el_texto(self) -> None:
        s = senal_de_hoy(
            universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30, ahora=HOY + timedelta(days=30)
        )
        assert "dia" in s.describe().lower()


class TestComparadaConLoQueTienes:
    def test_si_ya_estas_donde_toca_no_hay_que_hacer_nada(self) -> None:
        s = senal_de_hoy(universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30, tienes="AAA")
        assert not s.hay_que_mover
        assert "nada" in s.describe().lower()

    def test_si_estas_en_otro_hay_que_rotar(self) -> None:
        s = senal_de_hoy(universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30, tienes="BBB")
        assert s.hay_que_mover
        assert s.vender == "BBB"
        assert s.comprar == "AAA"

    def test_estando_fuera_y_tocando_entrar(self) -> None:
        s = senal_de_hoy(universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30, tienes=None)
        assert s.hay_que_mover
        assert s.vender is None
        assert s.comprar == "AAA"

    def test_tocando_salir_del_mercado(self) -> None:
        s = senal_de_hoy(
            universo(AAA=BAJA, BBB=[160.0 - i * 2 for i in range(60)]), lookback=30, tienes="AAA"
        )
        assert s.hay_que_mover
        assert s.vender == "AAA"
        assert s.comprar is None

    def test_fuera_y_tocando_seguir_fuera(self) -> None:
        s = senal_de_hoy(
            universo(AAA=BAJA, BBB=[160.0 - i * 2 for i in range(60)]), lookback=30, tienes=None
        )
        assert not s.hay_que_mover


class TestNoSePasaDeLoQuePuedeSaber:
    def test_no_promete_que_vaya_a_funcionar(self) -> None:
        texto = senal_de_hoy(universo(AAA=SUBE_MUCHO, BBB=SUBE_POCO), lookback=30).describe()
        assert "garantiza" in texto.lower() or "no predice" in texto.lower()

    def test_sin_historia_suficiente_no_inventa_una_senal(self) -> None:
        corto = [100.0 + i for i in range(10)]
        s = senal_de_hoy(universo(AAA=corto, BBB=corto), lookback=30)
        assert s.elegido is None
        assert "suficiente" in s.describe().lower() or not s.en_mercado
