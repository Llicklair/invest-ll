"""Lanzador del panel.

Streamlit necesita ejecutar el script con su propio runtime; llamar a `main()` directamente
mostraría avisos y no levantaría el servidor. Este módulo existe para que `invest-ll-panel`
funcione como cualquier otro comando del proyecto.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).parent / "app.py"


def main(argv: list[str] | None = None) -> int:
    """Arranca el panel. Los argumentos extra se pasan tal cual a Streamlit."""
    extra = list(argv if argv is not None else sys.argv[1:])
    comando = [sys.executable, "-m", "streamlit", "run", str(APP), *extra]
    return subprocess.call(comando)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
