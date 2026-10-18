"""Panel v4 (docs/panel-v4-real.md): varios exchanges, estrategias a medida con Claude y bots
reales con límites.

Mismas convenciones que los demás `schemas*`: dinero como cadena (Decimal), lo que se dibuja en
`float`, toda cifra con su hora, textos en castellano llano. Las claves NUNCA aparecen en ningún
modelo de respuesta.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from invest_ll.api.schemas_v2 import SaldoMoneda
from invest_ll.api.schemas_v3 import LimitesBot, OperacionBot, PuntoBot

RedExchange = Literal["pruebas", "real"]
EstadoEstrategia = Literal["borrador", "probada", "ficticio", "real"]


# -- Conexiones con exchanges -------------------------------------------------------------------------


class CampoClave(BaseModel):
    clave: str = Field(description="'apiKey', 'secret', 'password', 'walletAddress', 'privateKey'…")
    nombre: str = Field(description="En llano: 'Clave de la API', 'Dirección de la cartera'…")
    secreto: bool = Field(description="True: se escribe oculto y nunca se vuelve a enseñar")
    ayuda: str


class ExchangeDisponible(BaseModel):
    id: str = Field(description="'binance', 'hyperliquid', 'bybit', 'okx', 'kraken', 'coinbase'")
    nombre: str
    tiene_pruebas: bool
    campos: list[CampoClave]
    como_conseguir_pruebas: list[str] = Field(description="Pasos en llano (vacío si no hay red)")
    como_conseguir_real: list[str] = Field(description="Pasos en llano, sin permiso de retirada")
    aviso: str | None


class EstadoRedExchange(BaseModel):
    red: RedExchange
    claves_guardadas: bool
    origen: Literal["panel", "entorno", "ninguno"]
    verificada: bool = Field(description="Hay al menos una orden ejecutada en esta red (evidencia)")
    puede_retirar: bool | None = Field(description="None: el exchange no lo dice")
    comprobado: datetime | None = Field(description="Última prueba de conexión que salió bien")


class EstadoExchange(BaseModel):
    id: str
    nombre: str
    activo: Literal["sin_conectar", "pruebas", "real"]
    redes: list[EstadoRedExchange]
    que_falta_real: list[str] = Field(description="En llano; vacío si se puede activar real")


class ConfigMcp(BaseModel):
    """Para añadir el conector de INVEST LL a Claude Code o Claude Desktop."""

    comando: str
    argumentos: list[str]
    bloque_json: str = Field(description="El bloque listo para pegar en la configuración")
    nota: str = Field(description="Qué puede y qué NO puede hacer Claude con él")


class Conexiones(BaseModel):
    exchanges: list[EstadoExchange]
    mcp: ConfigMcp


class ClavesExchange(BaseModel):
    valores: dict[str, str] = Field(description="Por `CampoClave.clave`")


class PruebaExchange(BaseModel):
    ok: bool
    detalle: str = Field(description="En llano; si falla, qué revisar")
    saldo: list[SaldoMoneda] = Field(description="Solo monedas con saldo, ordenadas")
    permisos: str | None


class ActivarExchange(BaseModel):
    red: RedExchange
    confirmacion: str | None = Field(default=None, description="Para real: 'DINERO REAL'")


class MercadoExchange(BaseModel):
    par: str
    base: str
    cotizada: str
    nombre: str = Field(description="Nombre llano de la base")
    minimo_importe: Decimal | None
    paso_cantidad: Decimal | None


class MercadosExchange(BaseModel):
    exchange: str
    red: RedExchange
    mercados: list[MercadoExchange]


# -- Estrategias a medida -------------------------------------------------------------------------------


class ResultadoPrueba(BaseModel):
    """Una estrategia probada sobre el pasado, con costes, frente a mantener."""

    exchange: str
    monedas: list[str]
    intervalo: str
    desde: datetime
    hasta: datetime
    capital: Decimal
    valor_final: Decimal
    ganancia_pct: float = Field(description="Fracción")
    mantener_pct: float = Field(description="Fracción")
    peor_caida: float = Field(description="Fracción negativa")
    mantener_peor_caida: float
    operaciones: int
    comisiones: Decimal
    tiempo_dentro: float = Field(description="Fracción del tiempo con algo comprado")
    curva: list[PuntoBot]
    curva_mantener: list[PuntoBot]
    lista_operaciones: list[OperacionBot] = Field(description="Las primeras 200")
    versiones_probadas: int = Field(
        description="Cuántas versiones de esta estrategia se han probado"
    )
    aviso_sobreajuste: str | None
    avisos: list[str]


class ResumenEstrategia(BaseModel):
    id: str
    nombre: str
    version: int
    estado: EstadoEstrategia
    autor: Literal["claude", "marcos"]
    explicacion: str
    monedas: list[str]
    intervalo: str
    actualizada: datetime
    ultima_prueba: ResultadoPrueba | None
    bots: list[str] = Field(description="Ids de los bots que la usan")


class Estrategias(BaseModel):
    estrategias: list[ResumenEstrategia]


class VersionEstrategia(BaseModel):
    version: int
    at: datetime
    huella: str
    nota: str


class DetalleEstrategia(ResumenEstrategia):
    definicion: dict[str, Any] = Field(description="La estrategia en su formato (JSON validado)")
    reglas_en_llano: list[str] = Field(description="Cada regla, como frase")
    versiones: list[VersionEstrategia]
    pruebas: list[ResultadoPrueba] = Field(description="La más reciente primero")


class NuevaEstrategia(BaseModel):
    definicion: dict[str, Any]
    autor: Literal["claude", "marcos"] = "marcos"
    nota: str = Field(default="", description="Qué cambia respecto a la versión anterior")
    id: str | None = Field(default=None, description="Si se da, nueva versión de esa estrategia")


class PeticionPruebaEstrategia(BaseModel):
    exchange: str
    capital: Decimal = Field(default=Decimal(1000), gt=0)
    desde: datetime | None = Field(default=None, description="Por defecto, un año atrás")
    hasta: datetime | None = None


class EsquemaEstrategia(BaseModel):
    esquema: dict[str, Any] = Field(description="JSON Schema del formato")
    ejemplos: list[dict[str, Any]]
    explicacion: str


class PeticionDiseno(BaseModel):
    mensaje: str = Field(min_length=1)
    sesion: str | None = Field(default=None, description="Para seguir una conversación")


class MensajeDiseno(BaseModel):
    autor: Literal["marcos", "claude"]
    texto: str = Field(description="Markdown")
    at: datetime


class RespuestaDiseno(BaseModel):
    sesion: str
    respuesta: str = Field(description="Markdown")
    estrategia: str | None = Field(description="La estrategia que creó o cambió en este turno")
    herramientas: list[str] = Field(description="Herramientas del conector que usó, en orden")
    historial: list[MensajeDiseno]


# -- Bots reales ------------------------------------------------------------------------------------------


class ActivarReal(BaseModel):
    confirmacion: str = Field(description="Exactamente 'ACTIVAR <nombre del bot>'")
    exchange: str | None = Field(
        default=None, description="Dónde opera con dinero real; sin él, el de su modo de pruebas"
    )
    limites: LimitesBot | None = Field(
        default=None,
        description="Sus límites en real (su capital máximo es su capital); sin ellos, los de pruebas",
    )
    sin_ficticio: str | None = Field(
        default=None,
        description="Si su estrategia no lleva 30 días en ficticio: 'SIN PRUEBA EN FICTICIO'",
    )
    sin_examen: str | None = Field(
        default=None,
        description="Si no tiene un examen sobre el pasado aprobado y vigente: 'SIN EXAMEN'",
    )


class CambioLimites(BaseModel):
    limites: LimitesBot
    confirmacion: str | None = Field(
        default=None, description="Si alguno sube en un bot real: 'ACTIVAR <nombre del bot>'"
    )


class ParadaGeneral(BaseModel):
    parados: list[str]
    ordenes_canceladas: int
    avisos: list[str] = Field(description="Lo que no se pudo cancelar o comprobar, en llano")


class LimiteDiario(BaseModel):
    limite: Decimal = Field(gt=0, description="Pérdida máxima diaria de todos los bots reales")
    confirmacion: str | None = Field(default=None, description="Para subirlo: 'DINERO REAL'")
