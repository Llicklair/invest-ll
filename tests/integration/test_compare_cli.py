"""El comando de comparación de extremo a extremo (T032).

Con decisiones grabadas y sin red — que es como se usa de verdad para repetir un experimento.
"""

from __future__ import annotations

import csv
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.cli.compare import (
    SALIDA_ERROR,
    SALIDA_NO_CONCLUYENTE,
    SALIDA_NO_ENCONTRADO,
    SALIDA_OK,
    main,
)
from invest_ll.data.universe import build_universe
from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.models import Action, AssetDecision, Decision, DecisionRequest
from invest_ll.decision.prompt import INSTRUCCIONES_VERSION, render_context
from invest_ll.engine.universe_view import UniverseView

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

D = Decimal
MODELO = "modelo-de-prueba"
CADA = 21


def escribir_csv(destino: Path, cierres: list[float]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i, cierre in enumerate(cierres):
            marca = ORIGIN + timedelta(days=i)
            w.writerow([marca.isoformat(), cierre, cierre * 1.01, cierre * 0.99, cierre, 1000])


@pytest.fixture(autouse=True)
def en_un_directorio_vacio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Comparar apunta cuántas pruebas llevas (`attempts/`, relativo al directorio de trabajo):
    sin esto, cada pasada de la suite lo dejaba en la raíz del repositorio con AAA y BBB."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def mercado(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "yfinance" / "AAA" / "DAY_1.csv"
    b = tmp_path / "yfinance" / "BBB" / "DAY_1.csv"
    escribir_csv(a, list(ramp(200)))
    escribir_csv(b, list(ramp(200, start=50.0)))
    return a, b


@pytest.fixture
def decisiones(tmp_path: Path, mercado: tuple[Path, Path]) -> Path:
    """Graba una decisión para cada punto en que la estrategia va a preguntar.

    Se generan con las mismas claves que producirá el backtest: si no coincidieran, el proveedor
    grabado lanzaría — que es justo lo que debe hacer cuando falta una pieza.
    """
    carpeta = tmp_path / "decisiones"
    almacen = DecisionStore(carpeta)

    universo = build_universe(
        [
            series_from_closes(ramp(200), symbol="AAA"),
            series_from_closes(ramp(200, start=50.0), symbol="BBB", start=ORIGIN),
        ]
    )

    # Se alterna de activo en cada punto de decision: con una eleccion fija solo habria una
    # operacion en todo el backtest y el informe seria (con razon) no concluyente.
    for cursor in range(len(universo)):
        vista = UniverseView(universe=universo, cursor=cursor)
        elegido = "AAA" if (cursor // CADA) % 2 == 0 else "BBB"
        peticion = DecisionRequest(
            timestamp=vista.current_timestamp,
            symbols=tuple(vista.symbols),
            market_context=render_context(vista),
            instructions_version=INSTRUCCIONES_VERSION,
            model=MODELO,
        )
        almacen.put(
            peticion.cache_key,
            Decision(
                timestamp=vista.current_timestamp,
                assets=(
                    AssetDecision(
                        symbol=elegido,
                        action=Action.ENTER,
                        weight=D("1.0"),
                        reasoning="es el que mas sube ahora mismo",
                    ),
                ),
                summary=f"me quedo en {elegido}",
                model=MODELO,
            ),
        )
    return carpeta


class TestComparacion:
    def test_compara_llm_y_regla_con_las_mismas_metricas(
        self, mercado: tuple[Path, Path], decisiones: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        codigo = main(
            [
                str(mercado[0]),
                str(mercado[1]),
                "--strategies",
                "llm,momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--recorded",
                str(decisiones),
                "--model",
                MODELO,
                "--every",
                str(CADA),
            ]
        )
        salida = capsys.readouterr().out

        # Con pocas operaciones el veredicto puede ser no concluyente: eso es correcto del
        # sistema, no un fallo. Lo que se comprueba aqui es que ambas salen en la misma tabla.
        assert codigo in (SALIDA_OK, SALIDA_NO_CONCLUYENTE)
        assert "llm" in salida
        assert "momentum" in salida
        assert "comprar y mantener" in salida

    def test_las_dos_estrategias_salen_en_la_misma_tabla(
        self, mercado: tuple[Path, Path], decisiones: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Si el LLM tuviera su propia tabla, comparar dejaria de ser directo."""
        main(
            [
                str(mercado[0]),
                str(mercado[1]),
                "--strategies",
                "llm,momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--recorded",
                str(decisiones),
                "--model",
                MODELO,
            ]
        )
        lineas = capsys.readouterr().out.splitlines()
        cabecera = next(i for i, linea in enumerate(lineas) if "RESULTADO" in linea)
        bloque = "\n".join(lineas[cabecera : cabecera + 6])
        assert "llm" in bloque
        assert "momentum" in bloque

    def test_advierte_de_la_contaminacion_al_incluir_el_llm(
        self, mercado: tuple[Path, Path], decisiones: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(
            [
                str(mercado[0]),
                str(mercado[1]),
                "--strategies",
                "llm",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
                "--recorded",
                str(decisiones),
                "--model",
                MODELO,
            ]
        )
        salida = capsys.readouterr().out
        assert "entrenado" in salida

    def test_sin_llm_no_aparece_esa_advertencia(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(
            [
                str(mercado[0]),
                str(mercado[1]),
                "--strategies",
                "momentum",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
            ]
        )
        assert "entrenado" not in capsys.readouterr().out


class TestReproducibilidad:
    def test_repetir_da_exactamente_lo_mismo(
        self, mercado: tuple[Path, Path], decisiones: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Escenario E2 del quickstart. Sin esto, comparar experimentos no significa nada."""
        argumentos = [
            str(mercado[0]),
            str(mercado[1]),
            "--strategies",
            "llm",
            "--commission",
            "0.001",
            "--slippage",
            "0.0005",
            "--recorded",
            str(decisiones),
            "--model",
            MODELO,
        ]
        separador = "--- historial de esta sesion de trabajo ---"

        # La primera evaluacion de un universo no tiene historial (y lo que va tras el separador
        # sale pegado al resultado): se hace una antes para que las dos que se comparan tengan la
        # misma forma. Este test pasaba solo porque la suite dejaba `attempts/` en la raiz del
        # repositorio y el contador ya venia de pasadas anteriores.
        main(argumentos)
        capsys.readouterr()
        main(argumentos)
        primera = capsys.readouterr().out.split(separador)[0]
        main(argumentos)
        salida_segunda = capsys.readouterr().out
        segunda = salida_segunda.split(separador)[0]

        assert primera == segunda, "el RESULTADO debe ser identico al repetir (FR-044)"
        assert separador in salida_segunda, (
            "y el contador de intentos SI debe aparecer en la segunda: mide cuantas veces has "
            "mirado estos mismos datos, que es justo lo que cambia"
        )


class TestErrores:
    def test_el_llm_sin_decisiones_grabadas_se_rechaza(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """El motor no toca la red: sin decisiones grabadas no hay nada que evaluar."""
        codigo = main(
            [
                str(mercado[0]),
                str(mercado[1]),
                "--strategies",
                "llm",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
            ]
        )
        assert codigo == SALIDA_ERROR
        assert "no toca la red" in capsys.readouterr().err

    def test_un_fichero_que_no_existe_da_codigo_propio(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        codigo = main([str(tmp_path / "nada.csv"), "--commission", "0.001", "--slippage", "0.0005"])
        assert codigo == SALIDA_NO_ENCONTRADO

    def test_una_estrategia_desconocida_se_rechaza(
        self, mercado: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        codigo = main(
            [
                str(mercado[0]),
                str(mercado[1]),
                "--strategies",
                "adivinar",
                "--commission",
                "0.001",
                "--slippage",
                "0.0005",
            ]
        )
        assert codigo == SALIDA_ERROR
        assert "desconocida" in capsys.readouterr().err

    def test_los_costes_son_obligatorios(self, mercado: tuple[Path, Path]) -> None:
        """Como en el resto del proyecto: una simulacion sin friccion es una mentira optimista."""
        with pytest.raises(SystemExit):
            main([str(mercado[0])])
