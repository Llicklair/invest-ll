"""Las wallets conectadas, en `config/wallets.json` (fuera de git): solo direcciones públicas.

Por wallet: su dirección (con checksum), el nombre de la wallet con que se conectó (MetaMask,
Rabby…), cuándo, y en qué redes de Hyperliquid tiene autorizada la wallet agente del panel. Nunca
una clave: la del agente va al almacén de claves de Windows, como las de los exchanges.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final, cast

from invest_ll.fetch.atomic_write import replace_atomically

CARPETA: Final = Path("config")
FICHERO: Final = "wallets.json"


@dataclass(frozen=True, slots=True)
class Wallet:
    direccion: str
    nombre: str
    conectada: datetime
    agente_hyperliquid: dict[str, str] = field(default_factory=dict[str, str])
    """Por red ('pruebas', 'real'): la dirección del agente autorizado."""


class RegistroWallets:
    def __init__(self, raiz: Path = CARPETA) -> None:
        self._ruta = raiz / FICHERO

    def lista(self) -> list[Wallet]:
        if not self._ruta.is_file():
            return []
        try:
            datos: object = json.loads(self._ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        salida: list[Wallet] = []
        for crudo in cast("list[object]", datos) if isinstance(datos, list) else []:
            if not isinstance(crudo, dict):
                continue
            d = cast("dict[str, object]", crudo)
            if not d.get("direccion"):
                continue
            agentes = d.get("agente_hyperliquid")
            salida.append(
                Wallet(
                    direccion=str(d["direccion"]),
                    nombre=str(d.get("nombre") or "Wallet"),
                    conectada=datetime.fromisoformat(str(d["conectada"])),
                    agente_hyperliquid={
                        str(k): str(v)
                        for k, v in (
                            cast("dict[object, object]", agentes)
                            if isinstance(agentes, dict)
                            else {}
                        ).items()
                    },
                )
            )
        return salida

    def buscar(self, direccion: str) -> Wallet | None:
        return next((w for w in self.lista() if w.direccion.lower() == direccion.lower()), None)

    def _guardar(self, lista: list[Wallet]) -> None:
        def a_json(w: Wallet) -> dict[str, Any]:
            d = asdict(w)
            d["conectada"] = w.conectada.isoformat()
            return d

        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps([a_json(w) for w in lista], ensure_ascii=False, indent=2)
        replace_atomically(self._ruta, lambda tmp: tmp.write_text(texto, encoding="utf-8"))

    def anadir(self, wallet: Wallet) -> Wallet:
        """La añade (o, si ya estaba, le pone el nombre nuevo y conserva lo demás)."""
        lista = self.lista()
        previa = next((w for w in lista if w.direccion.lower() == wallet.direccion.lower()), None)
        if previa is not None:
            wallet = Wallet(
                previa.direccion, wallet.nombre, previa.conectada, previa.agente_hyperliquid
            )
        lista = [w for w in lista if w.direccion.lower() != wallet.direccion.lower()] + [wallet]
        self._guardar(lista)
        return wallet

    def quitar(self, direccion: str) -> Wallet | None:
        lista = self.lista()
        quitada = next((w for w in lista if w.direccion.lower() == direccion.lower()), None)
        if quitada is not None:
            self._guardar([w for w in lista if w is not quitada])
        return quitada

    def poner_agente(self, direccion: str, red: str, agente: str) -> None:
        """Apunta el agente autorizado en esa red (y lo quita de cualquier otra wallet: Hyperliquid
        tiene una sola conexión por red en el panel)."""
        lista: list[Wallet] = []
        for w in self.lista():
            agentes = {k: v for k, v in w.agente_hyperliquid.items() if k != red}
            if w.direccion.lower() == direccion.lower():
                agentes[red] = agente
            lista.append(Wallet(w.direccion, w.nombre, w.conectada, agentes))
        self._guardar(lista)
