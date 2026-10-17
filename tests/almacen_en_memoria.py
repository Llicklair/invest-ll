"""Un almacén de credenciales en memoria, para que ningún test toque el del sistema.

El panel guarda las claves de Binance con `keyring`, que en Windows escribe en el Administrador de
credenciales del usuario. Un test que escribiera ahí dejaría claves de mentira en el equipo de
quien corre la suite (o borraría las de verdad). `tests/conftest.py` pone este almacén en todos
los tests, sin excepción.
"""

from __future__ import annotations

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


class AlmacenEnMemoria(KeyringBackend):
    """Guarda en un diccionario y olvida al terminar."""

    priority = 1  # pyright: ignore[reportAssignmentType, reportIncompatibleMethodOverride] - keyring la declara como propiedad de clase

    def __init__(self) -> None:
        super().__init__()
        self.guardado: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.guardado.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.guardado[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.guardado:
            raise PasswordDeleteError("no existe")
        del self.guardado[(service, username)]
