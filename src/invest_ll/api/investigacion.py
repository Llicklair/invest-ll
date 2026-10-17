"""Pestaña Investigación: la cartera prerregistrada hoy, su prueba hacia delante y el último estudio.

Todo sale de `invest_ll.quant` y de los ficheros que escribe `invest-ll-quant`; aquí solo se lee.
Nada de esto envía nada: ejecutar las cantidades objetivo sigue siendo cosa tuya.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from invest_ll.api.errores import RESPUESTAS_DE_ERROR_EN_JSON, no_encontrado
from invest_ll.api.schemas import Estudio, Investigacion, PesoObjetivo, PruebaAdelante
from invest_ll.quant.panel import Panel, load_binance_universe

router = APIRouter()

DATOS_UNIVERSO = Path("data/market/binance-universe")
ESTUDIOS = Path("research/runs")
PESO_MINIMO = 1e-6
CAPITAL_PRUEBA = 10_000

ETIQUETAS = {
    "preregistered": "Prerregistrada",
    "filtered": "Segunda fase (filtro de mercado + banda)",
    "btc-trend": "Tendencia de BTC (BTC o liquidez)",
}

SIN_DATOS = "Sin datos todavía. Descárgalos con `uv run invest-ll-quant download` (unos 6 minutos)."
SIN_REGISTROS = (
    "Todavía no hay registros. `uv run invest-ll-quant paper record` guarda la cartera de hoy; "
    "`scripts/paper-daily.ps1` lo hace cada día y lo deja en un commit con fecha."
)
SIN_ESTUDIO = "Ningún estudio todavía. `uv run invest-ll-quant study` genera el informe completo."


def latest_report(runs: Path = ESTUDIOS) -> Path | None:
    """El `report.html` más reciente de `research/runs/*/`. `None` si no hay ninguno."""
    reports = sorted(runs.glob("*/report.html"), key=lambda p: p.stat().st_mtime)
    return reports[-1] if reports else None


@lru_cache(maxsize=2)
def _panel(ruta: Path, firma: tuple[int, int]) -> Panel:
    """El universo de Binance, leído una vez por versión del fichero (tarda varios segundos)."""
    del firma  # solo es clave de cache: cambia si el fichero se reescribe
    return load_binance_universe(ruta)


def cargar_panel(klines: Path) -> Panel:
    estado = klines.stat()
    return _panel(klines.resolve(), (estado.st_mtime_ns, estado.st_size))


def olvidar_panel() -> None:
    """Suelta el universo leído (al acabar de actualizar los datos: libera la versión vieja)."""
    _panel.cache_clear()


def _estudio() -> Estudio | None:
    informe = latest_report()
    if informe is None:
        return None
    return Estudio(
        ruta=informe.as_posix(),
        generado=datetime.fromtimestamp(informe.stat().st_mtime, tz=UTC),
    )


def _objetivo(panel: Panel, capital: float) -> list[PesoObjetivo]:
    from invest_ll.quant.paper import current_targets
    from invest_ll.quant.study import FLAGSHIP, FLAGSHIP_UNIVERSE, REBALANCE_EVERY, TRANCHES

    pesos = current_targets(
        panel, FLAGSHIP, FLAGSHIP_UNIVERSE, rebalance_every=REBALANCE_EVERY, tranches=TRANCHES
    )
    filas = [
        PesoObjetivo(
            moneda=panel.symbols[i].removesuffix("USDT"), peso=float(w), usdt=float(w) * capital
        )
        for i, w in sorted(enumerate(pesos), key=lambda x: -x[1])
        if w > PESO_MINIMO
    ]
    liquidez = 1.0 - sum(float(w) for w in pesos if w > PESO_MINIMO)
    filas.append(PesoObjetivo(moneda="liquidez", peso=liquidez, usdt=liquidez * capital))
    return filas


def _pruebas_adelante(panel: Panel) -> list[PruebaAdelante]:
    from invest_ll.quant.metrics import summarise
    from invest_ll.quant.paper import read, replay, variants

    pruebas: list[PruebaAdelante] = []
    for variante in variants().values():
        registros = read(variante.ledger)
        base = {
            "clave": variante.key,
            "etiqueta": ETIQUETAS.get(variante.key, variante.key),
            "registros": len(registros),
            "desde": date.fromisoformat(registros[0].data_date) if registros else None,
            "valor_final": None,
            "mantener_btc": None,
            "peor_caida": None,
            "nota": None,
        }
        if not registros:
            pruebas.append(PruebaAdelante.model_validate({**base, "nota": SIN_REGISTROS}))
            continue
        try:
            resultado = replay(panel, registros, no_trade_band=variante.no_trade_band)
            if resultado is None or len(resultado.returns) < 1:
                nota = (
                    f"Primer registro el {registros[0].data_date}: aún no hay días después "
                    "para medir."
                )
                pruebas.append(PruebaAdelante.model_validate({**base, "nota": nota}))
                continue
            resumen = summarise(resultado)
            btc = panel.close[:, panel.column("BTCUSDT")]
            mantener_btc = CAPITAL_PRUEBA * float(btc[-1] / btc[resultado.start])
        except (ValueError, KeyError, IndexError) as error:
            # Registros que el panel descargado no cubre: se dice, no se inventa una cifra.
            nota = f"No se pudo medir con los datos descargados: {error}"
            pruebas.append(PruebaAdelante.model_validate({**base, "nota": nota}))
            continue
        pruebas.append(
            PruebaAdelante.model_validate(
                {
                    **base,
                    "valor_final": resumen.final_value,
                    "mantener_btc": mantener_btc,
                    "peor_caida": resumen.max_drawdown,
                }
            )
        )
    return pruebas


@router.get("/investigacion", tags=["investigacion"])
def investigacion(capital: float = Query(default=1000.0, ge=0)) -> Investigacion:
    """La cartera prerregistrada hoy, su prueba hacia delante y el último estudio."""
    klines = DATOS_UNIVERSO / "klines_1d.parquet"
    if not klines.exists():
        return Investigacion(
            disponible=False,
            motivo=SIN_DATOS,
            ultimo_dato=None,
            dias_desfase=None,
            objetivo=[],
            prueba_adelante=[],
            estudio=_estudio(),
        )

    panel = cargar_panel(klines)
    ultimo = panel.date_at(len(panel) - 1)
    return Investigacion(
        disponible=True,
        motivo=None,
        ultimo_dato=ultimo,
        # Mas de 2 dias es lo que el panel avisaba: actualiza con invest-ll-quant download.
        dias_desfase=(datetime.now(UTC).date() - ultimo).days,
        objetivo=_objetivo(panel, capital),
        prueba_adelante=_pruebas_adelante(panel),
        estudio=_estudio(),
    )


@router.get(
    "/investigacion/estudio",
    tags=["investigacion"],
    response_class=HTMLResponse,
    responses=RESPUESTAS_DE_ERROR_EN_JSON,
)
def estudio() -> str:
    """El HTML del último estudio, para incrustarlo. 404 si no hay ninguno."""
    informe = latest_report()
    if informe is None:
        raise no_encontrado(SIN_ESTUDIO)
    return informe.read_text(encoding="utf-8")
