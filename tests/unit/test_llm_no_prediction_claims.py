"""Lo que el sistema NO puede decir (T029, T030 · FR-013, FR-010).

Estos tests no comprueban comportamiento sino **lenguaje**, y están aquí porque el operador ha
declarado no entender de inversión. Eso obliga a más honestidad en la presentación, no a menos:
alguien que no puede detectar por sí mismo cuándo le están vendiendo algo depende de que el
sistema no se lo venda.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2] / "src" / "invest_ll"

# Expresiones que afirmarian capacidad de prediccion. Si aparecen en texto que ve el operador,
# el sistema esta prometiendo algo que no puede cumplir.
PROHIBIDAS = (
    r"\bpredice\b",
    r"\bpredecir[aá]\b",
    r"\bprediccion fiable\b",
    r"\bva a subir\b",
    r"\bva a bajar\b",
    r"\bgarantiza\w* (ganancia|rentabilidad|beneficio)",
    r"\brentabilidad asegurada\b",
    r"\bsin riesgo\b",
    r"\bacierta siempre\b",
    r"\bestrategia infalible\b",
)

# Modulos cuyo texto llega al operador.
DE_CARA_AL_OPERADOR = ("cli", "report", "dashboard", "decision", "strategy")


def textos_visibles() -> list[tuple[Path, str]]:
    """Cadenas literales de los módulos que producen texto para el operador."""
    encontrados: list[tuple[Path, str]] = []
    for sub in DE_CARA_AL_OPERADOR:
        carpeta = RAIZ / sub
        if not carpeta.exists():
            continue
        for fichero in carpeta.rglob("*.py"):
            encontrados.append((fichero, fichero.read_text(encoding="utf-8")))
    return encontrados


class TestNoAfirmaPrediccion:
    @pytest.mark.parametrize("patron", PROHIBIDAS)
    def test_ninguna_expresion_prohibida_aparece(self, patron: str) -> None:
        """FR-013: el LLM no tiene ventaja predictiva demostrable y el sistema no puede
        presentarlo como si la tuviera."""
        culpables = [
            fichero.name
            for fichero, texto in textos_visibles()
            if re.search(patron, texto, re.IGNORECASE)
        ]
        assert not culpables, f"expresion {patron!r} encontrada en {culpables}"


class TestAdvierteDeLaContaminacion:
    """FR-010: el modelo sabe que paso despues del periodo simulado, y eso no tiene arreglo."""

    def test_el_comando_de_comparacion_lo_advierte(self) -> None:
        from invest_ll.cli.compare import ADVERTENCIA_CONTAMINACION

        texto = ADVERTENCIA_CONTAMINACION.lower()
        assert "entrenado" in texto
        assert "no se puede eliminar" in texto

    def test_la_advertencia_dice_que_hacer_en_su_lugar(self) -> None:
        """Advertir sin decir la salida deja al operador igual de perdido."""
        from invest_ll.cli.compare import ADVERTENCIA_CONTAMINACION

        assert "comparar con lo que pase" in ADVERTENCIA_CONTAMINACION.lower()

    def test_la_advertencia_es_imprimible_en_consola_windows(self) -> None:
        from invest_ll.cli.compare import ADVERTENCIA_CONTAMINACION

        ADVERTENCIA_CONTAMINACION.encode("cp1252")

    def test_el_modulo_del_prompt_documenta_el_limite(self) -> None:
        """Quien lea el codigo tiene que encontrarse con esto, no descubrirlo por su cuenta."""
        texto = (RAIZ / "decision" / "prompt.py").read_text(encoding="utf-8").lower()
        assert "no puede arreglar" in texto


class TestElWinRateNoSePresentaSolo:
    def test_la_comparacion_explica_por_que_no_aparece(self) -> None:
        from invest_ll.cli import compare

        fuente = Path(compare.__file__).read_text(encoding="utf-8")
        assert "no es criterio de exito" in fuente
