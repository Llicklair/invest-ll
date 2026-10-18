"""El detector de secretos (`scripts/sin_secretos.py`): que el repositorio no lleve ninguno y que el
detector de verdad los vea.

Los secretos de ejemplo se fabrican al vuelo (`secrets.token_hex`, trozos pegados): si estuvieran
escritos tal cual, este fichero sería el primero en saltar, aquí y en GitGuardian.
"""

from __future__ import annotations

import importlib.util
import secrets
import string
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _cargar() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "sin_secretos", RAIZ / "scripts" / "sin_secretos.py"
    )
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["sin_secretos"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


S = _cargar()


def _aleatorio(n: int, alfabeto: str = string.ascii_letters + string.digits) -> str:
    return "".join(secrets.choice(alfabeto) for _ in range(n))


def _que(texto: str, fichero: str = "src/x.py") -> list[str]:
    return [h.que for h in S.buscar_en_texto(fichero, texto)]


def test_el_repositorio_no_lleva_secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(RAIZ)
    assert S.main(["--todo"]) == 0


@pytest.mark.parametrize(
    ("linea", "que"),
    [
        (f'firmante = "0x{secrets.token_hex(32)}"', "clave privada en hexadecimal"),
        (f"PRIVATE_KEY={secrets.token_hex(32)}", "clave privada en hexadecimal"),
        ("sk-" + "ant-" + _aleatorio(40), "token de Anthropic"),
        ("gh" + "p_" + _aleatorio(36), "token de GitHub"),
        ("AK" + "IA" + _aleatorio(16, string.ascii_uppercase + string.digits), "clave de AWS"),
        ("1234567890" + ":AA" + _aleatorio(33), "token de Telegram"),
        ('"secret": "' + _aleatorio(32) + '"', "«secret» con un valor que parece de verdad"),
        (
            "-----BEGIN EC " + "PRIVATE KEY-----\\n" + _aleatorio(80, string.ascii_letters + "+/"),
            "clave privada PEM",
        ),
    ],
)
def test_ve_los_secretos_de_verdad(linea: str, que: str) -> None:
    assert que in _que(linea)


@pytest.mark.parametrize(
    "linea",
    [
        '{"apiKey": "CLAVE-PRUEBAS-111", "secret": "SECRETO-PRUEBAS-222"}',
        '{"apiKey": "k", "secret": "s", "password": "frase"}',
        '"secret": "-----BEGIN EC PRIVATE KEY-----x"',
        f'"hash": "0x{secrets.token_hex(32)}"',
        f'firmante = "0x{"1" * 64}"',
        f'"sha256": "{secrets.token_hex(32)}"',
        f'"secret": "{_aleatorio(32)}"  # secretos: permitido',
        '"token": "{token_de_telegram}"',
    ],
)
def test_no_salta_con_marcadores_ni_hashes(linea: str) -> None:
    assert _que(linea) == []


@pytest.mark.parametrize(
    ("ruta", "prohibido"),
    [
        (".env", True),
        ("config/.env.local", True),
        ("claves/hyperliquid.pem", True),
        ("web/.env.development", False),
        (".env.example", False),
        ("src/invest_ll/exchanges/credenciales.py", False),
    ],
)
def test_ficheros_de_claves_no_se_versionan(ruta: str, *, prohibido: bool) -> None:
    assert S.fichero_prohibido(ruta) is prohibido


def test_nunca_ensena_el_secreto_entero() -> None:
    valor = secrets.token_hex(32)
    (h,) = S.buscar_en_texto("src/x.py", f'clave_privada = "0x{valor}"')
    assert valor not in str(h)
    assert valor[4:] not in str(h)
