"""Que el panel no empuje a operar de más.

Esto no es una preferencia estética. La FCA probó una app experimental con **más de 9.000
personas** y midió el efecto de cada elemento de diseño:

    notificaciones push  ->  +11% de operaciones,  +8% en inversiones arriesgadas
    puntos y sorteos     ->  +12% de operaciones,  +6% en inversiones arriesgadas

Y el efecto es **mayor** en personas con baja alfabetización financiera y menores de 35 años — el
operador de este proyecto ha declarado explícitamente no entender de inversión.

Lo que convierte eso en dinero son las cifras de este mismo repositorio:

    423 operaciones  ->   2.890 de resultado, 18.151 en comisiones
      1 operación    ->  37.773 de resultado,     87 en comisiones

Un +11% de operaciones no es una métrica de interacción: son comisiones.

Ver `docs/research-aplicaciones.md`. Este fichero convierte esa intención en una garantía: si
alguien añade confeti al panel, la suite se pone roja.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2] / "src" / "invest_ll"

# Módulos que producen la interfaz que ve el operador.
DE_CARA_AL_OPERADOR = ("api", "dashboard", "cli", "report", "proposal")

# Llamadas de Streamlit que son literalmente celebración. `st.balloons()` y `st.snow()` existen
# y lanzan globos y nieve por la pantalla: es el confeti que la FCA señala por su nombre.
CELEBRACIONES_STREAMLIT = ("st.balloons", "st.snow", "st.toast")

# Mecánicas de juego. El patrón busca la palabra, no la subcadena: "racha" aparece legítimamente
# en `longest_losing_streak` (racha de meses en rojo), que es una MÉTRICA DE RIESGO, no un premio.
MECANICAS_DE_JUEGO = (
    r"\bleaderboard\b",
    r"\branking de (usuarios|traders|inversores)\b",
    r"\binsignia\b",
    r"\bbadge\b",
    r"\blogro desbloqueado\b",
    r"\bnivel \d+ alcanzado\b",
    r"\bpuntos ganados\b",
    r"\bsorteo\b",
    r"\bpremio\b",
    r"\bnotificacion push\b",
    r"\bpush_notification\b",
)

# Lenguaje de urgencia: existe para que actúes ya, no para informarte.
URGENCIA = (
    r"\bno te lo pierdas\b",
    r"\bultima oportunidad\b",
    r"\bactua ahora\b",
    r"\bcompra ya\b",
    r"\bvende ya\b",
    r"\bopera ahora\b",
    r"\btiempo limitado\b",
)

# Emojis de celebración. Los de aviso (⚠ ❗) no entran: informan de riesgo, no premian.
EMOJIS_DE_CELEBRACION = ("🎉", "🎊", "🥳", "🏆", "🔥", "🚀", "💰", "🤑", "✨")


def fuentes_visibles() -> list[tuple[Path, str]]:
    """Código de los módulos que generan lo que el operador lee."""
    encontrados: list[tuple[Path, str]] = []
    for sub in DE_CARA_AL_OPERADOR:
        carpeta = RAIZ / sub
        if not carpeta.exists():
            continue
        encontrados.extend(
            (fichero, fichero.read_text(encoding="utf-8")) for fichero in carpeta.rglob("*.py")
        )
    return encontrados


class TestSinCelebraciones:
    """La FCA señala el refuerzo positivo tras una operación como causa de sobreoperar."""

    @pytest.mark.parametrize("llamada", CELEBRACIONES_STREAMLIT)
    def test_no_hay_efectos_de_celebracion(self, llamada: str) -> None:
        culpables = [f.name for f, texto in fuentes_visibles() if llamada in texto]
        assert not culpables, (
            f"{llamada} en {culpables}: es una celebracion. Medido por la FCA: el refuerzo "
            "positivo tras una operacion aumenta el numero de operaciones."
        )

    @pytest.mark.parametrize("emoji", EMOJIS_DE_CELEBRACION)
    def test_no_hay_emojis_de_celebracion(self, emoji: str) -> None:
        """Los de aviso si valen: informan de riesgo en vez de premiar una accion."""
        culpables = [f.name for f, texto in fuentes_visibles() if emoji in texto]
        assert not culpables, f"emoji de celebracion {emoji} en {culpables}"


class TestSinMecanicasDeJuego:
    @pytest.mark.parametrize("patron", MECANICAS_DE_JUEGO)
    def test_no_hay_mecanicas_de_juego(self, patron: str) -> None:
        """Puntos y sorteos: +12% de operaciones, +6% en inversiones arriesgadas."""
        culpables = [
            f.name for f, texto in fuentes_visibles() if re.search(patron, texto, re.IGNORECASE)
        ]
        assert not culpables, f"mecanica de juego {patron!r} en {culpables}"

    def test_la_racha_de_perdidas_si_esta_permitida(self) -> None:
        """Comprobacion del propio test: `longest_losing_streak` es una METRICA DE RIESGO.

        Si el detector la marcara, estaria prohibiendo informar de algo que el operador necesita
        saber — y el test seria peor que no tenerlo.
        """
        texto = "st.metric('Racha en rojo', f'{c.longest_losing_streak} meses')"
        for patron in MECANICAS_DE_JUEGO:
            assert not re.search(patron, texto, re.IGNORECASE), (
                f"el patron {patron!r} marca una metrica de riesgo legitima"
            )


class TestSinUrgencia:
    @pytest.mark.parametrize("patron", URGENCIA)
    def test_no_hay_lenguaje_de_urgencia(self, patron: str) -> None:
        """La urgencia existe para que actues ya, no para informarte."""
        culpables = [
            f.name for f, texto in fuentes_visibles() if re.search(patron, texto, re.IGNORECASE)
        ]
        assert not culpables, f"lenguaje de urgencia {patron!r} en {culpables}"


class TestElDetectorFunciona:
    """Un guardian que no puede fallar es peor que no tener guardian.

    Se comprueba contra texto construido a mano: si el detector no ve una violacion evidente, los
    tests de arriba estan pasando por vacio.
    """

    def test_detecta_una_celebracion(self) -> None:
        assert any(llamada in "st.balloons()" for llamada in CELEBRACIONES_STREAMLIT)

    def test_detecta_una_mecanica_de_juego(self) -> None:
        texto = "st.write('Has desbloqueado una insignia por operar 10 veces')"
        assert any(re.search(p, texto, re.IGNORECASE) for p in MECANICAS_DE_JUEGO)

    def test_detecta_urgencia(self) -> None:
        texto = "st.warning('Ultima oportunidad de entrar')"
        assert any(re.search(p, texto, re.IGNORECASE) for p in URGENCIA)

    def test_hay_ficheros_que_escanear(self) -> None:
        """Si la lista viniera vacia, todos los tests pasarian sin comprobar nada."""
        assert len(fuentes_visibles()) >= 5


class TestLoQueSiDebeEstar:
    """El reverso: hay avisos que el panel NO puede perder."""

    def test_el_win_rate_lleva_su_coletilla(self) -> None:
        textos = " ".join(t for _, t in fuentes_visibles()).lower()
        assert "no es criterio de exito" in textos

    def test_se_advierte_de_la_contaminacion_del_llm(self) -> None:
        textos = " ".join(t for _, t in fuentes_visibles()).lower()
        assert "entrenado" in textos

    def test_se_compara_contra_no_hacer_nada(self) -> None:
        textos = " ".join(t for _, t in fuentes_visibles()).lower()
        assert "comprar y mantener" in textos or "no hacer nada" in textos
