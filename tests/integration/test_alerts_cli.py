"""`invest-ll-alerts` de extremo a extremo."""

from __future__ import annotations

import ast
import csv
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from invest_ll.alerts.models import PERDIDA_DESDE_TU_ENTRADA
from invest_ll.cli.alerts import SALIDA_HAY_QUE_REVISAR, leer_objetivo, leer_posicion, main
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_NO_ENCONTRADO, SALIDA_OK

D = Decimal


def escribir_csv(destino: Path, cierres: list[float], *, hasta: datetime) -> None:
    """Escribe una serie que TERMINA en `hasta`, para controlar si esta al dia."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        inicio = hasta - timedelta(days=len(cierres) - 1)
        for i, cierre in enumerate(cierres):
            marca = inicio + timedelta(days=i)
            w.writerow([marca.isoformat(), cierre, cierre * 1.01, cierre * 0.99, cierre, 1000])


@pytest.fixture
def al_dia(tmp_path: Path) -> Path:
    ruta = tmp_path / "yfinance" / "AAA" / "DAY_1.csv"
    escribir_csv(ruta, [100.0] * 60, hasta=datetime.now(UTC))
    return ruta


@pytest.fixture
def cayendo(tmp_path: Path) -> Path:
    ruta = tmp_path / "yfinance" / "BBB" / "DAY_1.csv"
    escribir_csv(ruta, [100.0] * 30 + [150.0] + [90.0] * 29, hasta=datetime.now(UTC))
    return ruta


def sobre_de(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(capsys.readouterr().out))


def alertas_de(sobre: dict[str, object]) -> list[dict[str, object]]:
    datos = sobre["data"]
    assert isinstance(datos, dict)
    crudas = cast("dict[str, object]", datos)["alerts"]
    assert isinstance(crudas, list)
    return cast("list[dict[str, object]]", crudas)


class TestLecturaDeArgumentos:
    def test_una_posicion_bien_escrita(self) -> None:
        p = leer_posicion("GLD:10:180.5")
        assert p.symbol == "GLD"
        assert p.quantity == D(10)
        assert p.entry_price == D("180.5")

    def test_sin_precio_de_entrada_se_rechaza(self) -> None:
        """No es un capricho de formato: sin el no se puede decir lo que has perdido TU."""
        with pytest.raises(ValueError, match="perdido TU"):
            leer_posicion("GLD:10")

    def test_una_cantidad_que_no_es_numero(self) -> None:
        with pytest.raises(ValueError, match="invalida"):
            leer_posicion("GLD:diez:180")

    def test_pesos_objetivo(self) -> None:
        assert leer_objetivo(["GLD:0.6", "TLT:0.4"]) == {"GLD": D("0.6"), "TLT": D("0.4")}

    def test_un_peso_sin_valor(self) -> None:
        with pytest.raises(ValueError, match="SIMBOLO:PESO"):
            leer_objetivo(["GLD"])


class TestElComando:
    def test_una_serie_tranquila_y_al_dia_no_alerta(
        self, al_dia: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        codigo = main([str(al_dia)])
        assert codigo == SALIDA_OK
        assert "Ninguna regla ha saltado" in capsys.readouterr().out

    def test_no_dice_que_todo_vaya_bien(
        self, al_dia: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sin alertas != todo correcto. Decir lo segundo seria tranquilizar de mas."""
        main([str(al_dia)])
        texto = capsys.readouterr().out
        assert "no significa que todo vaya bien" in texto

    def test_datos_viejos_dan_codigo_de_revisar(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        viejo = tmp_path / "yfinance" / "CCC" / "DAY_1.csv"
        escribir_csv(viejo, [100.0] * 30, hasta=datetime.now(UTC) - timedelta(days=90))

        codigo = main([str(viejo)])
        capsys.readouterr()
        assert codigo == SALIDA_HAY_QUE_REVISAR, "encadenable en un script sin leer el texto"

    def test_una_caida_aparece(self, cayendo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(cayendo), "--json"])
        codigos = {a["code"] for a in alertas_de(sobre_de(capsys))}
        assert "drawdown_from_peak" in codigos

    def test_con_posicion_declarada_sale_tu_perdida(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([str(cayendo), "--holding", "BBB:10:140", "--json"])
        codigos = {a["code"] for a in alertas_de(sobre_de(capsys))}
        assert PERDIDA_DESDE_TU_ENTRADA in codigos

    def test_si_entraste_barato_no_sale_perdida(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Mismo activo, misma caida, distinta entrada: distinta realidad."""
        main([str(cayendo), "--holding", "BBB:10:50", "--json"])
        codigos = {a["code"] for a in alertas_de(sobre_de(capsys))}
        assert PERDIDA_DESDE_TU_ENTRADA not in codigos

    def test_un_fichero_que_no_existe(self, capsys: pytest.CaptureFixture[str]) -> None:
        codigo = main(["no/existe.csv"])
        capsys.readouterr()
        assert codigo == SALIDA_NO_ENCONTRADO


class TestLaComparacionContraElPlanNecesitaLasDosCosas:
    def test_solo_el_drawdown_no_vale(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Pedir una y no la otra suele ser un despiste; callarlo dejaria la mejor regla muda."""
        codigo = main([str(cayendo), "--simulated-drawdown", "-1000"])
        assert codigo == SALIDA_ERROR
        assert "van juntos" in capsys.readouterr().err

    def test_solo_el_capital_tampoco(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        codigo = main([str(cayendo), "--capital", "10000"])
        capsys.readouterr()
        assert codigo == SALIDA_ERROR

    def test_con_las_dos_compara(self, cayendo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(cayendo), "--simulated-drawdown", "-1000", "--capital", "10000", "--json"])
        codigos = {a["code"] for a in alertas_de(sobre_de(capsys))}
        assert "worse_than_simulated" in codigos


class TestElSobreJson:
    def test_encontrar_alertas_no_es_fallar(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`ok` dice si se pudo calcular; `exit_code` dice si hay algo que mirar."""
        codigo = main([str(cayendo), "--json"])
        sobre = sobre_de(capsys)

        assert sobre["ok"] is True, "el comando hizo su trabajo"
        assert sobre["exit_code"] == codigo

    def test_las_alertas_van_en_data_y_no_en_warnings(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Un aviso dice como leer un resultado; aqui las alertas SON el resultado."""
        main([str(cayendo), "--json"])
        sobre = sobre_de(capsys)

        assert alertas_de(sobre), "tiene que haber alertas en data"
        assert sobre["warnings"] == []

    def test_cada_alerta_lleva_medida_y_umbral(
        self, cayendo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Quien consuma esto no deberia tener que sacar el numero de una frase."""
        main([str(cayendo), "--holding", "BBB:10:140", "--json"])
        for alerta in alertas_de(sobre_de(capsys)):
            assert alerta["measured"] is not None, f"{alerta['code']} sin medida"
            assert alerta["threshold"] is not None, f"{alerta['code']} sin umbral"


class TestNoHayNingunMecanismoDeEnvio:
    """Se consulta; no persigue. Es el diseno, no una pieza pendiente.

    La FCA midio +11% de operaciones con notificaciones push. Que este modulo no tenga forma de
    enviar nada no es una carencia que alguien deba "completar" mas adelante.
    """

    # Modulos que sirven para MANDAR algo. Se comprueban como imports reales, no como texto: la
    # primera version leia el fichero plano y se puso roja por la palabra "push" dentro de la
    # frase que explica el hallazgo de la FCA. Es la segunda vez en este proyecto que un guardian
    # confunde hablar de algo con hacerlo; documentar una prohibicion no puede violarla.
    ENVIO = frozenset(
        {"smtplib", "email", "http", "urllib", "requests", "httpx", "socket", "webbrowser"}
    )

    def modulos_importados(self) -> dict[str, set[str]]:
        """Lo que cada fichero del modulo importa de verdad, segun el AST."""
        fuentes = [*Path("src/invest_ll/alerts").rglob("*.py"), Path("src/invest_ll/cli/alerts.py")]
        importados: dict[str, set[str]] = {}
        for fichero in fuentes:
            arbol = ast.parse(fichero.read_text(encoding="utf-8"))
            nombres: set[str] = set()
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    nombres.update(alias.name.split(".")[0] for alias in nodo.names)
                elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                    nombres.add(nodo.module.split(".")[0])
            importados[fichero.name] = nombres
        return importados

    def test_el_modulo_no_importa_nada_que_sirva_para_enviar(self) -> None:
        for fichero, nombres in self.modulos_importados().items():
            culpables = nombres & self.ENVIO
            assert not culpables, (
                f"{fichero} importa {culpables}: las alertas se consultan, no se envian. "
                "Medido por la FCA: las notificaciones aumentan un 11% las operaciones."
            )

    def test_el_guardian_detecta_un_import_de_verdad(self) -> None:
        """Contra codigo que SI deberia marcar, y contra prosa que NO."""
        con_envio = ast.parse("import smtplib\n")
        nombres = {
            alias.name
            for n in ast.walk(con_envio)
            if isinstance(n, ast.Import)
            for alias in n.names
        }
        assert nombres & self.ENVIO, "no ve un import evidente"

        solo_habla = ast.parse('"""Las notificaciones push aumentan un 11% las operaciones."""\n')
        assert not [n for n in ast.walk(solo_habla) if isinstance(n, ast.Import | ast.ImportFrom)]

    def test_hay_ficheros_que_escanear(self) -> None:
        """Si la lista viniera vacia, el test de arriba pasaria sin comprobar nada."""
        assert len(self.modulos_importados()) >= 4
