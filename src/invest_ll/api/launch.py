"""`invest-ll-panel`: arranca el panel. Un proceso, un puerto, como antes.

uvicorn sirve la API en `/api` y el frontend ya compilado (`web/out`) en `/`, en
http://127.0.0.1:8601, y se abre el navegador cuando el servidor ya escucha. Siempre el mismo
puerto: cuando cada arranque buscaba uno nuevo, el navegador se quedaba mirando un panel viejo.

Si el frontend no está compilado se dice cómo compilarlo y se arranca la API igualmente: su
documentación interactiva (`/docs`) sirve para mirarla mientras tanto.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from typing import TYPE_CHECKING, Protocol

from invest_ll.api.app import FRONTEND, crear_app

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from fastapi import FastAPI

HOST = "127.0.0.1"
PUERTO = 8601
COMPILAR_FRONTEND = "npm --prefix web ci && npm --prefix web run build"
ESPERA_MAXIMA = 30.0
"""Segundos que se espera a que el servidor escuche antes de renunciar a abrir el navegador."""


class _Arrancable(Protocol):
    @property
    def started(self) -> bool: ...


def abrir_navegador(url: str) -> None:
    webbrowser.open(url)


def cuando_arranque(servidor: _Arrancable, accion: Callable[[], None]) -> None:
    """Ejecuta `accion` en cuanto el servidor haya arrancado; si no arranca, no hace nada.

    Se mira la marca del propio uvicorn y no se prueba a conectar: este paquete no abre sockets
    (tests/unit/test_no_network_in_suite.py lo vigila). Si el puerto estaba ocupado, uvicorn ya
    lo cuenta y no se abre una pestaña contra un panel que no existe.
    """
    limite = time.monotonic() + ESPERA_MAXIMA
    while time.monotonic() < limite:
        if servidor.started:
            accion()
            return
        time.sleep(0.2)


def _precalentar() -> None:
    from invest_ll.estrategias.historico import precalentar

    try:
        precalentar()
    except Exception as error:
        print(f"[!] No se pudo precalcular el catalogo de estrategias: {error}", file=sys.stderr)


def servir(
    app: FastAPI, *, host: str, puerto: int, al_arrancar: Callable[[], None] | None = None
) -> None:
    """El servidor de verdad. Bloquea hasta Ctrl+C. Los tests lo sustituyen."""
    import uvicorn

    servidor = uvicorn.Server(uvicorn.Config(app, host=host, port=puerto))
    # El catalogo de estrategias tarda unos segundos en calcularse la primera vez: se adelanta
    # en segundo plano para que la primera visita a Estrategias no espere. Si alguien lo pide
    # antes de que acabe, espera a este mismo calculo (no lo repite).
    threading.Thread(target=_precalentar, name="precalentar", daemon=True).start()
    if al_arrancar is not None:
        threading.Thread(
            target=cuando_arranque, args=(servidor, al_arrancar), name="al-arrancar", daemon=True
        ).start()
    servidor.run()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-panel",
        description=(
            "Arranca el panel de INVEST LL: la API y el frontend en un solo proceso. "
            "Arranca en simulacion salvo que INVEST_LL_MODE diga otra cosa."
        ),
    )
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    parser.add_argument(
        "--puerto", type=int, default=PUERTO, help=f"puerto local (por defecto {PUERTO})"
    )
    args = parser.parse_args(argv)

    url = f"http://{HOST}:{args.puerto}"
    destino = url
    if not (FRONTEND / "index.html").exists():
        destino = f"{url}/docs"
        print(
            f"[!] El frontend no esta compilado (falta {FRONTEND / 'index.html'}).\n"
            f"    Compilalo con:  {COMPILAR_FRONTEND}\n"
            f"    Mientras tanto arranca solo la API; su documentacion esta en {destino}",
            file=sys.stderr,
        )

    print(f"Panel en {url}  (Ctrl+C para pararlo)", flush=True)

    def abrir() -> None:
        abrir_navegador(destino)

    servir(
        crear_app(frontend=FRONTEND),
        host=HOST,
        puerto=args.puerto,
        al_arrancar=None if args.no_browser else abrir,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
