"""Que ningún secreto llegue a git: el detector que corre antes de cada commit (`.githooks/pre-commit`)
y en la suite (`tests/unit/test_sin_secretos.py`).

El repositorio es público. Las claves de los exchanges y de la wallet viven en el almacén de
credenciales de Windows, nunca en ficheros; esto vigila que ninguna se cuele por descuido (un
`print`, un fichero de pruebas con una clave de verdad, un `.env`).

Solo busca lo que casi seguro es un secreto, para que avise poco y en serio: claves privadas (PEM
con cuerpo, hex de 64 junto a «private/secret/clave»), tokens con formato conocido (Anthropic,
GitHub, AWS, Telegram, Slack) y asignaciones de `secret/password/token/api_key` a una cadena larga
y aleatoria. Los marcadores de los tests (`SECRETO-PRUEBAS-222`, `"k"`, `"s"`) no cuentan.

Uso (sin dependencias, con cualquier Python 3.11+):

    python scripts/sin_secretos.py --staged     # lo que va en el commit (el hook)
    python scripts/sin_secretos.py --todo       # todo lo versionado
    python scripts/sin_secretos.py fichero...   # esos ficheros

Una línea que de verdad tiene que llevar algo así (un ejemplo en la documentación) se marca con el
comentario `secretos: permitido`.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

PERMITIDO = "secretos: permitido"
SIN_MIRAR = (
    "uv.lock",
    "package-lock.json",
    "web/openapi.json",
    "web/src/api/esquema.d.ts",
    ".specify/",
    "tests/fixtures/",
)
EXTENSIONES_BINARIAS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf", ".zip"}
FICHEROS_PROHIBIDOS = re.compile(
    r"(^|/)(\.env(\.[^/]*)?|id_rsa|id_ed25519|[^/]*\.pem|[^/]*\.key|[^/]*\.p12)$"
)
ENV_PERMITIDOS = {".env.development", ".env.example", ".env.production.example"}

PATRONES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "clave privada PEM",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*(?:\\n|\s)*[A-Za-z0-9+/=]{60,}"),
    ),
    ("token de Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("token de OpenAI", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}")),
    (
        "token de GitHub",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})"),
    ),
    ("clave de AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token de Telegram", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b")),
    ("token de Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
)
HEX64 = re.compile(r"(?<![0-9a-fA-F])(?:0x)?([0-9a-fA-F]{64})(?![0-9a-fA-F])")
CERCA_DE_CLAVE = re.compile(r"(?i)priv|secret|clave|signer|firmante|wallet_key|seed|mnemonic")
CERCA_DE_HASH = re.compile(r"(?i)hash|sha256|digest|huella|txid|tx_hash")
ASIGNACION = re.compile(
    r"(?i)[\"']?(api[_-]?key|apikey|secret|secreto|password|passphrase|token|clave_privada|private[_-]?key)[\"']?"
    r"\s*[:=]\s*[\"']([^\"'\s]{24,})[\"']"
)
MARCADOR = re.compile(r"(?i)prueba|falso|fake|ejemplo|example|dummy|xxx|test|<|\{|\$")


@dataclass(frozen=True, slots=True)
class Hallazgo:
    fichero: str
    linea: int
    que: str
    muestra: str

    def __str__(self) -> str:
        return f"{self.fichero}:{self.linea}: {self.que} ({self.muestra})"


def entropia(texto: str) -> float:
    cuenta = Counter(texto)
    return -sum(n / len(texto) * math.log2(n / len(texto)) for n in cuenta.values())


def tapado(valor: str) -> str:
    """Nunca se enseña un secreto entero, ni en la terminal: los 4 primeros y cuánto mide."""
    return f"{valor[:4]}… {len(valor)} caracteres"


def buscar_en_texto(fichero: str, texto: str) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    for n, linea in enumerate(texto.splitlines(), 1):
        if PERMITIDO in linea:
            continue
        vistos: set[str] = set()  # un mismo valor se cuenta una vez, por la regla más concreta
        for que, patron in PATRONES:
            for m in patron.finditer(linea):
                vistos.add(m.group(0))
                hallazgos.append(Hallazgo(fichero, n, que, tapado(m.group(0))))
        for m in HEX64.finditer(linea):
            valor = m.group(1)
            if len(set(valor.lower())) <= 6:
                continue  # 0x000…, 0x1111…: marcadores
            if CERCA_DE_CLAVE.search(linea) and not CERCA_DE_HASH.search(linea):
                vistos.add(m.group(0))
                hallazgos.append(
                    Hallazgo(fichero, n, "clave privada en hexadecimal", tapado(valor))
                )
        for m in ASIGNACION.finditer(linea):
            valor = m.group(2)
            if any(valor in v or v in valor for v in vistos):
                continue
            if MARCADOR.search(valor) or entropia(valor) < 3.5:
                continue
            if not (re.search(r"[0-9]", valor) and re.search(r"[A-Za-z]", valor)):
                continue
            hallazgos.append(
                Hallazgo(
                    fichero, n, f"«{m.group(1)}» con un valor que parece de verdad", tapado(valor)
                )
            )
    return hallazgos


def fichero_prohibido(ruta: str) -> bool:
    nombre = PurePosixPath(ruta).name
    return bool(FICHEROS_PROHIBIDOS.search(ruta)) and nombre not in ENV_PERMITIDOS


def se_mira(ruta: str) -> bool:
    return (
        not ruta.startswith(SIN_MIRAR)
        and PurePosixPath(ruta).suffix.lower() not in EXTENSIONES_BINARIAS
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def revisar(rutas: list[str], leer: Callable[[str], str | None]) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    for ruta in rutas:
        if fichero_prohibido(ruta):
            hallazgos.append(
                Hallazgo(ruta, 0, "un fichero de claves o de entorno no se versiona", "entero")
            )
            continue
        if not se_mira(ruta):
            continue
        texto = leer(ruta)
        if texto is not None:
            hallazgos.extend(buscar_en_texto(ruta, texto))
    return hallazgos


def _leer_disco(ruta: str) -> str | None:
    try:
        return Path(ruta).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _leer_preparado(ruta: str) -> str | None:
    """Lo que va en el commit (lo preparado con `git add`), no lo que hay en disco."""
    r = subprocess.run(["git", "show", f":{ruta}"], capture_output=True, check=False)
    if r.returncode != 0:
        return None
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def main(argv: list[str]) -> int:
    if argv == ["--staged"]:
        rutas = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").split()
        hallazgos = revisar(rutas, _leer_preparado)
    elif argv == ["--todo"]:
        hallazgos = revisar(_git("ls-files").split(), _leer_disco)
    elif argv and not argv[0].startswith("--"):
        hallazgos = revisar(argv, _leer_disco)
    else:
        print(__doc__)
        return 2
    if not hallazgos:
        return 0
    print("Parece que hay secretos en lo que vas a guardar en git (el repositorio es público):")
    for h in hallazgos:
        print(f"  {h}")
    print(
        "\nSi es una clave de verdad, sácala del fichero (al almacén de credenciales) y, si ya llegó"
        "\na GitHub, cámbiala en su servicio. Si es un ejemplo, marca la línea con el comentario"
        f"\n«{PERMITIDO}»."
    )
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
    sys.exit(main(sys.argv[1:]))
