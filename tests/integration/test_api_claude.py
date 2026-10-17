"""Claude con tu suscripción (`/api/claude`): lo que dice `claude auth status`, sin nada que
identifique la cuenta, y el botón que abre el inicio de sesión. El CLI se sustituye: los tests no
lanzan `claude` de verdad."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll import claude_cli

if TYPE_CHECKING:  # pragma: no cover
    from .api_apoyo import Api

RUTA = "C:/falso/claude.exe"
CON_MAX = {
    "loggedIn": True,
    "authMethod": "claude.ai",
    "apiProvider": "firstParty",
    "email": "alguien@ejemplo.com",
    "orgId": "org-123",
    "orgName": "Organización de alguien",
    "subscriptionType": "max",
}


def falso_cli(monkeypatch: pytest.MonkeyPatch, estado: dict[str, Any] | None) -> list[list[str]]:
    """`claude` instalado (o no, con `estado` None) que contesta `estado` a `auth status`. Devuelve
    las órdenes que se abrieron con Popen."""
    monkeypatch.setattr(claude_cli, "ejecutable", lambda: None if estado is None else RUTA)

    def run(orden: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert orden == [RUTA, "auth", "status", "--json"]
        return subprocess.CompletedProcess(orden, 0, json.dumps(estado), "")

    abiertas: list[list[str]] = []

    def popen(orden: list[str], **_: Any) -> object:
        abiertas.append(orden)
        return object()

    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    monkeypatch.setattr(claude_cli.subprocess, "Popen", popen)
    return abiertas


def test_conectado_con_la_suscripcion_dice_el_plan_y_nada_mas(
    cliente: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    falso_cli(monkeypatch, CON_MAX)
    r = cliente.get("/api/claude")
    assert r.status_code == 200
    datos = r.json()
    assert datos["conectado"] is True
    assert datos["con_suscripcion"] is True
    assert datos["plan"] == "Max"
    assert datos["aviso"] is None
    texto = r.text
    for privado in ("alguien@ejemplo.com", "org-123", "Organización de alguien"):
        assert privado not in texto


def test_sin_sesion(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    falso_cli(monkeypatch, {"loggedIn": False})
    datos = cliente.get("/api/claude").json()
    assert (datos["instalado"], datos["conectado"], datos["plan"]) == (True, False, None)


def test_con_clave_de_la_api_lo_avisa(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    falso_cli(monkeypatch, {"loggedIn": True, "authMethod": "console"})
    datos = cliente.get("/api/claude").json()
    assert datos["conectado"] is True
    assert datos["con_suscripcion"] is False
    assert "se paga por uso" in datos["aviso"]


def test_sin_instalar(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    falso_cli(monkeypatch, None)
    datos = cliente.get("/api/claude").json()
    assert datos["instalado"] is False
    assert "npm install -g @anthropic-ai/claude-code" in datos["aviso"]
    r = cliente.post("/api/claude/conectar")
    assert r.status_code == 422
    assert "no está instalado" in r.json()["detail"]


def test_conectar_abre_el_inicio_de_sesion_con_la_suscripcion(
    cliente: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    abiertas = falso_cli(monkeypatch, {"loggedIn": False})
    r = cliente.post("/api/claude/conectar")
    assert r.status_code == 200
    assert r.json()["abierto"] is True
    assert abiertas == [[RUTA, "auth", "login", "--claudeai"]]


def test_conectar_si_ya_lo_esta_es_un_409(cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    abiertas = falso_cli(monkeypatch, CON_MAX)
    r = cliente.post("/api/claude/conectar")
    assert r.status_code == 409
    assert r.json()["detail"] == "Claude ya está conectado con tu suscripción Max."
    assert abiertas == []
