"""El motor que hace correr los bots en el proceso del panel (docs/panel-v3-vivo.md §3).

`crear_app(en_vivo=True)` llama a `arrancar()` después de `invest_ll.vivo.servicio.arrancar()`
(necesita su fuente de precios) y a `parar()` antes de cerrarla. Entre medias, un bucle de asyncio
da una vuelta (`Motor.paso`) cada segundo:

- valora cada bot con el precio de ahora (en marcha, parado o con error: sus posiciones siguen
  valiendo lo que valen);
- cada bot en marcha decide: los de velas, cuando cierra una vela de su intervalo; la rejilla, con
  cada precio; la periódica, según su horario. Las órdenes se ejecutan contra el libro del momento
  (`cuenta.Cuenta`, con `vivo.ejecucion`). Si no hay libro, la orden no se inventa: se apunta y se
  vuelve a decidir en la vuelta siguiente;
- un bot que lanza una excepción pasa a "con error" con su motivo; los demás siguen.

**Huecos.** Los bots solo funcionan con el motor en marcha (su servicio aparte, `bots.servicio`, que
sigue aunque se cierre el panel). Al volver (o si el equipo se suspendió),
cada bot en marcha apunta el tiempo que no pudo operar ("Panel cerrado de 14:02 a 18:30: no pudo
operar") y lo enseña en su tarjeta durante un día. Igual con un corte de los precios de más de 30 s.

El motor recibe la fuente y el reloj (inyección): las pruebas lo mueven con `FuenteFalsa` y un
reloj que avanza a mano, sin esperar ni tocar la red. Todo lo que cambia el estado pasa por un
cerrojo: las rutas de la API (en otro hilo) y el bucle no se pisan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from bisect import bisect_right
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from invest_ll import llano
from invest_ll.bots import real
from invest_ll.bots.actividad import (
    AL_ABRIR_POR_BOT,
    MAX_ACTIVIDAD,
    Movimiento,
    de_evento,
    de_operacion,
)
from invest_ll.bots.cuenta import (
    Cuenta,
    Hecha,
    OrdenPequenaError,
    cantidades_mantener,
    usdc,
    valor_mantener,
)
from invest_ll.bots.decisiones import CERO, Orden, Situacion, cerradas, precio_txt, y
from invest_ll.bots.metricas import resultado_venta, resultados
from invest_ll.bots.plantillas import BotInvalidoError, Plantilla, plantilla_de, validar
from invest_ll.bots.registro import (
    CARPETA,
    BotNoEncontradoError,
    Definicion,
    Estado,
    Evento,
    Limites,
    Operacion,
    Pausa,
    Punto,
    Registro,
    TipoEvento,
    nuevo_id,
)
from invest_ll.exchanges.conector import EstadoDesconocidoError, ExchangeError
from invest_ll.nombres import nombre_hyperliquid
from invest_ll.vivo.ejecucion import COMISIONES, Comisiones, LibroInsuficienteError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from datetime import tzinfo
    from pathlib import Path

    from invest_ll.bots.registro import ModoBot
    from invest_ll.exchanges.conector import Conector, OrdenExchange, Red
    from invest_ll.vivo.fuente import FuentePrecios, Libro, Vela

    ConectorDe = Callable[[str, Red], Conector]
    AnotarOrden = Callable[[OrdenExchange, str, Red, str], object]

log = logging.getLogger(__name__)

UMBRAL_HUECO: Final = timedelta(minutes=2)
"""Más que esto sin atender un bot en marcha es un hueco (el estado se guarda cada minuto)."""
CORTE_MINIMO: Final = timedelta(seconds=30)
"""Un corte de los precios más corto que esto no se apunta: la fuente reconecta sola."""
CADA_PUNTO: Final = timedelta(minutes=1)
CADA_GUARDADO: Final = timedelta(minutes=1)
AVISO_DURA: Final = timedelta(hours=24)
PUNTOS_CURVA: Final = 100
MAX_OPERACIONES: Final = 500
MAX_EVENTOS: Final = 200
ZONA: Final = ZoneInfo("Europe/Madrid")
"""Las horas de los textos ("Panel cerrado de 14:02 a 18:30"), como las lee Marcos."""
NOTA: Final = "Dinero ficticio. Los bots siguen aunque cierres el panel, mientras el ordenador esté encendido."
CADA_CONCILIACION: Final = timedelta(minutes=5)
REINTENTO_CONCILIACION: Final = timedelta(minutes=1)
"""Si no se pudo leer el saldo del exchange, se vuelve a probar al cabo de esto."""
CADA_PRECIO_EXCHANGE: Final = timedelta(seconds=15)
"""Los bots de exchange se valoran con el precio de su exchange, leído cada tanto (no cada vuelta)."""


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def conector_de_serie(exchange: str, red: Red) -> Conector:
    """El conector con claves de ese exchange y red; vuelve a mirar que siga activo en ella."""
    from invest_ll.exchanges import registro as exchanges

    return exchanges.conector(exchange, red)


def anotar_de_serie(orden: OrdenExchange, exchange: str, red: Red, bot: str) -> object:
    """Al registro de órdenes (`ledger/`), con su modo, exchange y bot."""
    from invest_ll.exchanges.anotar import anotar

    return anotar(orden, exchange=exchange, red=red, bot=bot)


def red_de(modo: ModoBot) -> Red | None:
    """La red del exchange de un bot: la de pruebas o la real; None si es ficticio."""
    if modo == "pruebas":
        return "pruebas"
    if modo == "real":
        return "real"
    return None


def limites_suben(antes: Limites | None, despues: Limites) -> bool:
    """Si el cambio deja al bot arriesgar más en algo (en un bot real, eso pide la activación)."""
    if antes is None:
        return True
    return (
        despues.capital_max > antes.capital_max
        or despues.orden_max > antes.orden_max
        or despues.perdida_max_pct > antes.perdida_max_pct
        or despues.operaciones_max_dia > antes.operaciones_max_dia
        or (antes.vender_al_parar and not despues.vender_al_parar)
    )


def _precio_guardado(precio: Decimal) -> Decimal:
    """Diez cifras significativas: el precio medio de una ejecución sale con 28."""
    return precio.quantize(Decimal(1).scaleb(precio.adjusted() - 9))


def tramo(desde: datetime, hasta: datetime, zona: tzinfo = ZONA) -> str:
    """'de 14:02 a 18:30', o 'del 16 oct, 14:02, al 17 oct, 18:30' si cambia el día."""
    a, b = desde.astimezone(zona), hasta.astimezone(zona)
    if a.date() == b.date():
        return f"de {a:%H:%M} a {b:%H:%M}"
    return (
        f"del {llano.fecha_corta(a.date())}, {a:%H:%M}, al {llano.fecha_corta(b.date())}, {b:%H:%M}"
    )


class Bot:
    """Un bot cargado: su definición, su estado y su curva, en memoria."""

    def __init__(self, definicion: Definicion, estado: Estado, curva: list[Punto]) -> None:
        self.definicion = definicion
        self.estado = estado
        self.curva = curva
        self.plantilla: Plantilla = plantilla_de(definicion.plantilla, definicion.estrategia)
        # Solo en memoria: se rehace al cargar.
        self.limite_avisado: str | None = None
        """El último «no sale» apuntado: no se repite en cada decisión mientras siga igual."""
        self.abiertas: set[tuple[str, str]] = set()
        """(par, id de cliente) de sus órdenes que el exchange dejó abiertas: «Parar todo lo
        real» las cancela (solo las suyas, nunca las de Marcos)."""
        self.velas_vistas: dict[str, datetime] | None = None
        """La última vela cerrada con que decidió, por moneda: no decide dos veces la misma."""
        self.esperando: str | None = None
        """Por qué hay una orden esperando (sin libro): se reintenta en la vuelta siguiente."""
        self.notas_previas: tuple[str, ...] = ()
        """Las notas de la decisión anterior: lo que se repite de una a otra no se vuelve a
        apuntar ("Esperando historia…" en cada vela hasta que la haya)."""
        self.aviso_plantilla: str | None = None
        self.ultimo_guardado: datetime | None = None
        self.sucio = False

    @property
    def id(self) -> str:
        return self.definicion.id

    @property
    def cuenta(self) -> Cuenta:
        return self.estado.cuenta

    @property
    def red(self) -> Red | None:
        return red_de(self.definicion.modo)

    @property
    def grupo(self) -> tuple[str, Red] | None:
        """(exchange, red) de un bot de pruebas o real: los del mismo grupo comparten cuenta."""
        red, exchange = self.red, self.definicion.exchange
        return (exchange, red) if red is not None and exchange is not None else None

    def valor(self) -> Decimal | None:
        return self.cuenta.valor(self.estado.ultimos_precios)

    def mantener(self) -> Decimal | None:
        d = self.definicion
        cantidades = cantidades_mantener(
            d.capital, d.monedas, self.estado.precios_arranque, self.cuenta.comisiones
        )
        return valor_mantener(cantidades, self.estado.ultimos_precios)

    def ganancia_24h_pct(self, ahora: datetime) -> float | None:
        """Desde hace 24 h (o desde que arrancó, si es más joven)."""
        valor = self.valor()
        if valor is None:
            return None
        i = bisect_right(self.curva, ahora - timedelta(hours=24), key=lambda p: p.at)
        base = self.curva[i - 1].valor if i > 0 else self.definicion.capital
        return float(valor / base - 1) if base > 0 else None

    def curva_muestreada(self, ahora: datetime) -> list[Punto]:
        """Unos 100 puntos desde que arrancó, el último con el valor de ahora."""
        guardados = self.curva
        valor = self.valor()
        vivo: list[Punto] = []
        if valor is not None and (not guardados or ahora > guardados[-1].at):
            vivo = [Punto(ahora, valor, self.mantener())]
        total = len(guardados) + len(vivo)
        if total <= PUNTOS_CURVA:
            return [*guardados, *vivo]
        ultimo = total - 1
        indices = sorted({round(i * ultimo / (PUNTOS_CURVA - 1)) for i in range(PUNTOS_CURVA)})
        # Sin copiar la curva entera (un mes son 43.200 puntos): la lista se pide cada 2 s.
        return [guardados[i] if i < len(guardados) else vivo[0] for i in indices]

    def aviso(
        self, ahora: datetime, sin_precios_desde: datetime | None, zona: tzinfo = ZONA
    ) -> str | None:
        """Lo que la tarjeta tiene que decir ahora mismo, lo más urgente primero."""
        e = self.estado
        if e.pausa is not None:
            return e.pausa.texto
        if e.estado == "en_marcha" and sin_precios_desde is not None:
            hora = f" desde las {sin_precios_desde.astimezone(zona):%H:%M}"
            return f"Sin precios de Hyperliquid{hora}: no opera hasta que vuelvan."
        if e.estado == "en_marcha" and self.esperando:
            return self.esperando
        if e.aviso and e.aviso_hasta is not None and ahora < e.aviso_hasta:
            return e.aviso
        if e.estado == "en_marcha":
            return self.aviso_plantilla
        return None


class Motor:
    """Los bots de una carpeta, con su fuente de precios y su reloj."""

    def __init__(
        self,
        fuente: FuentePrecios | None,
        raiz: Path = CARPETA,
        *,
        reloj: Callable[[], datetime] = ahora_utc,
        zona: tzinfo = ZONA,
        comisiones: Comisiones = COMISIONES,
        umbral_hueco: timedelta = UMBRAL_HUECO,
        conector_de: ConectorDe = conector_de_serie,
        anotar_orden: AnotarOrden = anotar_de_serie,
        globales: Path = real.GLOBALES,
    ) -> None:
        self.fuente = fuente
        self.registro = Registro(raiz)
        self._reloj = reloj
        self._zona = zona
        self._comisiones = comisiones
        self._umbral_hueco = umbral_hueco
        self._conector_de = conector_de
        self._anotar_orden = anotar_orden
        self._ruta_globales = globales
        self._conciliado: dict[tuple[str, Red], datetime] = {}
        """Cuándo cuadró por última vez cada exchange y red. Un bot de exchange no opera hasta
        que su grupo ha cuadrado desde que se cargó (antes de su primera orden)."""
        self._intento_conciliar: dict[tuple[str, Red], datetime] = {}
        self._error_conciliar: dict[tuple[str, Red], str] = {}
        self._precios_exchange: dict[tuple[str, Red, str], tuple[datetime, Decimal]] = {}
        self._leido_precio: dict[tuple[str, Red, str], datetime] = {}
        self._cambios = 0
        """Sube con cada ejecución apuntada: un saldo leído antes de una ya no vale para cuadrar."""
        self._bots: dict[str, Bot] = {}
        self._cerrojo = threading.RLock()
        self._tarea: asyncio.Task[None] | None = None
        self.sin_precios_desde: datetime | None = None
        """Desde cuándo la fuente no da precios (o None si los da)."""
        self._actividad: deque[tuple[int, Movimiento]] = deque(maxlen=MAX_ACTIVIDAD)
        """Los últimos movimientos de todos los bots, con su número de orden (el feed)."""
        self._secuencia = 0

    def ahora(self) -> datetime:
        return self._reloj()

    @property
    def cerrojo(self) -> threading.RLock:
        """Para leer varios bots de una vez sin que el bucle los cambie a mitad (las rutas)."""
        return self._cerrojo

    # -- Cargar y seguir ---------------------------------------------------------------------------

    def cargar(self) -> None:
        """Lee los bots de disco. Uno ilegible no impide cargar los demás."""
        with self._cerrojo:
            self._bots.clear()
            self._conciliado.clear()  # al cargar, los de exchange vuelven a cuadrar antes de operar
            for bot_id in self.registro.ids():
                try:
                    bot = Bot(
                        self.registro.definicion(bot_id),
                        self.registro.estado(bot_id),
                        self.registro.curva(bot_id),
                    )
                except Exception:
                    log.exception("no se pudo cargar el bot %s", bot_id)
                    continue
                bot.estado.cuenta.comisiones = self._comisiones
                self._bots[bot_id] = bot
                self._seguir(bot)
            if self.fuente is None or not self.fuente.conectada():
                self.sin_precios_desde = self.ahora()
            self._rellenar_actividad()

    def _rellenar_actividad(self) -> None:
        """El feed al abrir el panel: lo último de cada bot que hay en disco, por orden de hora."""
        semilla: list[Movimiento] = []
        for bot in self._bots.values():
            d = bot.definicion
            try:
                ops = self.registro.operaciones(bot.id)
                eventos = self.registro.eventos(bot.id)
            except Exception:
                log.exception("no se pudo leer la actividad del bot %s", bot.id)
                continue
            # El resultado de una venta depende de todas las compras de antes: se repasan todas.
            con_resultado = list(zip(ops, resultados(ops), strict=True))[-AL_ABRIR_POR_BOT:]
            semilla.extend(de_operacion(bot.id, d.nombre, o, r, d.modo) for o, r in con_resultado)
            semilla.extend(
                de_evento(bot.id, d.nombre, e, d.modo) for e in eventos[-AL_ABRIR_POR_BOT:]
            )
        self._actividad.clear()
        for movimiento in sorted(semilla, key=lambda m: m.at)[-MAX_ACTIVIDAD:]:
            self._anotar(movimiento)

    def _anotar(self, movimiento: Movimiento) -> None:
        self._secuencia += 1
        self._actividad.append((self._secuencia, movimiento))

    def _seguir(self, bot: Bot) -> None:
        if self.fuente is None:
            return
        intervalo = bot.plantilla.intervalo(bot.definicion.parametros)
        for coin in bot.definicion.monedas:
            self.fuente.seguir(coin, libro=True, intervalos=(intervalo,) if intervalo else ())

    def _precio(self, coin: str) -> Decimal | None:
        return self.fuente.precio(coin) if self.fuente is not None else None

    def _precio_de(self, bot: Bot, coin: str) -> Decimal | None:
        """El de su exchange si es de exchange y se ha leído; si no, el de Hyperliquid."""
        grupo = bot.grupo
        if grupo is not None:
            leido = self._precios_exchange.get((*grupo, coin))
            if leido is not None:
                return leido[1]
        return self._precio(coin)

    def _refrescar_precios(self, bot: Bot) -> dict[str, Decimal]:
        """Los precios de ahora de sus monedas (los que se conozcan), apuntados en el bot."""
        e = bot.estado
        frescos: dict[str, Decimal] = {}
        for coin in bot.definicion.monedas:
            precio = self._precio_de(bot, coin)
            if precio is None:
                continue
            frescos[coin] = precio
            e.ultimos_precios[coin] = precio
            if coin not in e.precios_arranque:
                e.precios_arranque[coin] = precio
                bot.sucio = True
        return frescos

    # -- Lo que piden las rutas --------------------------------------------------------------------

    def bots(self) -> list[Bot]:
        """Todos, con sus precios al día, del más antiguo al más reciente."""
        with self._cerrojo:
            for bot in self._bots.values():
                self._refrescar_precios(bot)
            return sorted(self._bots.values(), key=lambda b: b.definicion.creado)

    def bot(self, bot_id: str) -> Bot:
        with self._cerrojo:
            bot = self._bots.get(bot_id)
            if bot is None:
                raise BotNoEncontradoError(f"No hay ningún bot «{bot_id}».")
            self._refrescar_precios(bot)
            return bot

    def aviso(self, bot: Bot) -> str | None:
        texto = bot.aviso(self.ahora(), self.sin_precios_desde, self._zona)
        if texto is None and bot.estado.estado == "en_marcha" and not self._cuadrado(bot):
            error = self._error_conciliar.get(bot.grupo) if bot.grupo else None
            if error:
                return f"No se pudo leer el saldo de su exchange ({error}): no opera hasta poder."
            return "Comprobando el saldo en su exchange antes de operar."
        return texto

    def _cuadrado(self, bot: Bot) -> bool:
        """Un ficticio, siempre; uno de exchange, si su grupo ha cuadrado desde que se cargó."""
        return bot.grupo is None or bot.grupo in self._conciliado

    def globales(self) -> real.Globales:
        return real.leer_globales(self._ruta_globales)

    def perdida_hoy(self) -> Decimal:
        """Lo que han perdido hoy (desde las 00:00 de Madrid) los bots reales, entre todos; lo que
        ganan unos compensa lo que pierden otros. Cero si van ganando."""
        with self._cerrojo:
            ahora = self.ahora()
            medianoche = ahora.astimezone(self._zona).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            total = Decimal(0)
            for bot in self._bots.values():
                if bot.definicion.modo != "real":
                    continue
                valor = bot.valor()
                if valor is None:
                    continue
                i = bisect_right(bot.curva, medianoche, key=lambda p: p.at)
                base = bot.curva[i - 1].valor if i > 0 else bot.definicion.capital
                total += base - valor
            return max(usdc(total), Decimal(0))

    def operaciones(self, bot_id: str) -> list[Operacion]:
        """La más reciente primero (las últimas `MAX_OPERACIONES`)."""
        return list(reversed(self.registro.operaciones(self.bot(bot_id).id)))[:MAX_OPERACIONES]

    def eventos(self, bot_id: str) -> list[Evento]:
        """El más reciente primero (los últimos `MAX_EVENTOS`)."""
        return list(reversed(self.registro.eventos(self.bot(bot_id).id)))[:MAX_EVENTOS]

    def todas_las_operaciones(self, bot_id: str) -> list[Operacion]:
        """Todas, de la más antigua a la más reciente: para las métricas."""
        return self.registro.operaciones(self.bot(bot_id).id)

    def actividad(
        self, desde: int = 0, bot_id: str | None = None, limite: int = 50
    ) -> tuple[int, list[Movimiento]]:
        """Los movimientos posteriores al número `desde` (de ese bot, si se pide), el más reciente
        primero, y el número del último: quien lo guarde pide la próxima vez desde ahí."""
        with self._cerrojo:
            lista = [
                m
                for n, m in reversed(self._actividad)
                if n > desde and (bot_id is None or m.bot_id == bot_id)
            ]
            return self._secuencia, lista[:limite]

    def velas_de(self, bot: Bot) -> dict[str, list[Vela]]:
        """Las velas con que decide ahora (vacío si no usa velas o no hay fuente)."""
        with self._cerrojo:
            return self._velas(bot, self.ahora())[0]

    def desplegar(
        self,
        clave: str,
        nombre: str,
        monedas: Sequence[str],
        capital: Decimal,
        parametros: Mapping[str, str],
        *,
        modo: ModoBot = "ficticio",
        exchange: str | None = None,
        estrategia: str | None = None,
        limites: Limites | None = None,
    ) -> Bot:
        """Valida, crea el bot en disco y lo pone en marcha (decide en la vuelta siguiente).

        En pruebas opera con la red de pruebas de su exchange, que tiene que estar conectada, con
        límites y con saldo para su capital. En real no se crea: se activa (`activar_real`)."""
        with self._cerrojo:
            if modo == "real":
                raise BotInvalidoError(
                    "Un bot no se crea con dinero real: créalo en pruebas o en ficticio y actívalo "
                    "desde su ficha, con sus límites y escribiendo la activación."
                )
            v = validar(
                clave, nombre, monedas, capital, parametros, self._precio, estrategia=estrategia
            )
            red = red_de(modo)
            if red is not None:
                if exchange is None:
                    raise BotInvalidoError("Un bot de pruebas necesita su exchange.")
                if limites is None:
                    raise BotInvalidoError(
                        "Un bot de pruebas necesita sus límites (capital máximo, máximo por orden, "
                        "pérdida máxima y operaciones por día)."
                    )
                if v.capital > limites.capital_max:
                    raise BotInvalidoError(
                        f"El capital ({llano.numero(v.capital)} USDC) pasa de su capital máximo "
                        f"({llano.numero(limites.capital_max)} USDC)."
                    )
                self._comprobar_exchange(
                    exchange, red, v.monedas, real.Tenencia(v.capital, {}), excepto=None
                )
            ahora = self.ahora()
            definicion = Definicion(
                id=nuevo_id(v.nombre),
                nombre=v.nombre,
                plantilla=v.plantilla.clave,
                monedas=v.monedas,
                capital=v.capital,
                parametros=v.parametros,
                creado=ahora,
                modo=modo,
                exchange=exchange if red is not None else None,
                estrategia=estrategia,
                limites=limites if red is not None else None,
                activado=ahora,
            )
            estado = Estado(
                estado="en_marcha",
                cuenta=Cuenta(efectivo=v.capital, comisiones=self._comisiones),
                maximo=v.capital,
                peor_caida=0.0,
            )
            bot = Bot(definicion, estado, [])
            self._refrescar_precios(bot)
            self.registro.crear(definicion, estado)
            monedas_txt = y([nombre_hyperliquid(c) for c in v.monedas])
            if red is None:
                texto = f"Desplegado con {llano.numero(v.capital)} USDC ficticios en {monedas_txt}."
            else:
                texto = (
                    f"Desplegado en pruebas en {self._nombre_exchange(exchange)}, con "
                    f"{llano.numero(v.capital)} USDC de su red de pruebas en {monedas_txt}."
                )
            self._evento(bot, ahora, "arranque", texto)
            self._apuntar_punto(bot, ahora, v.capital)
            self._bots[definicion.id] = bot
            self._seguir(bot)
            return bot

    @staticmethod
    def _nombre_exchange(exchange: str | None) -> str:
        return real.nombre_exchange(exchange)

    def _comprobar_exchange(
        self,
        exchange: str,
        red: Red,
        monedas: Iterable[str],
        nueva: real.Tenencia,
        *,
        excepto: str | None,
    ) -> None:
        """Antes de desplegar o activar: el exchange está activo en esa red, tiene par de contado
        de cada moneda y saldo para lo que creen tener sus bots más el nuevo. Lee los precios del
        exchange de esas monedas, para valorarlo desde el principio con ellos."""
        try:
            conector = self._conector_de(exchange, red)
            for coin in monedas:
                m = real.mercado(conector, coin)
                precio = conector.precio(m.par)
                if precio is not None:
                    self._precios_exchange[(exchange, red, coin)] = (self.ahora(), precio)
            tenencias = [
                real.Tenencia(b.cuenta.efectivo, b.cuenta.cantidades())
                for b in self._bots.values()
                if b.grupo == (exchange, red) and b.id != excepto
            ]
            falta = real.descuadre(conector, [*tenencias, nueva], conector.saldo())
        except ExchangeError as error:
            raise BotInvalidoError(str(error)) from error
        if falta is not None:
            donde = "su red de pruebas" if red == "pruebas" else "la cuenta"
            raise BotInvalidoError(
                f"No hay saldo bastante en {donde} de {self._nombre_exchange(exchange)} para "
                f"este bot y los que ya operan allí. {falta}"
            )

    def parar_bot(self, bot_id: str) -> Bot:
        with self._cerrojo:
            bot = self.bot(bot_id)
            if bot.estado.estado != "parado":
                bot.estado.estado = "parado"
                bot.aviso_plantilla = None
                self._evento(
                    bot,
                    self.ahora(),
                    "parada",
                    "Parado: deja de operar y conserva sus posiciones, que se siguen valorando.",
                )
                self._guardar(bot, self.ahora())
            return bot

    def reanudar_bot(self, bot_id: str) -> Bot:
        """Vuelve a operar. Uno de exchange en pausa resuelve antes su pausa (consulta la orden
        desconocida, o vuelve a cuadrar el saldo): si no se puede, sigue en pausa y lo dice."""
        with self._cerrojo:
            bot = self.bot(bot_id)
            if bot.definicion.modo == "real" and self.globales().parado_todo:
                raise real.NoSePuedeError(
                    "Está puesto «Parar todo lo real»: quítalo antes de reanudar un bot real."
                )
            if bot.estado.pausa is not None:
                self._resolver_pausa(bot)
            if bot.estado.estado != "en_marcha":
                ahora = self.ahora()
                antes = bot.estado.estado
                bot.estado.estado = "en_marcha"
                bot.estado.motivo_error = None
                bot.estado.ultima_vez = ahora
                bot.velas_vistas = None
                bot.esperando = None
                texto = "Reanudado tras el error." if antes == "error" else "Reanudado."
                self._evento(bot, ahora, "arranque", texto)
                self._guardar(bot, ahora)
                self._seguir(bot)
            return bot

    def borrar_bot(self, bot_id: str) -> None:
        """Lo borra con su registro. Uno de exchange tiene que estar parado y sin pausa, y lo que
        tenga se queda en el exchange: borrar no vende nada."""
        with self._cerrojo:
            bot = self.bot(bot_id)
            if bot.grupo is not None and bot.estado.estado == "en_marcha":
                raise real.NoSePuedeError(
                    "Páralo antes de borrarlo: está operando en su exchange. Al borrarlo, lo que "
                    "tenga se queda en el exchange (borrar no vende nada)."
                )
            if bot.estado.pausa is not None and bot.estado.pausa.motivo == "desconocido":
                raise real.NoSePuedeError(
                    "Tiene una orden de la que no se sabe si salió: reanúdalo para resolverla "
                    "(o compruébala en el exchange) antes de borrarlo."
                )
            del self._bots[bot.id]
            self.registro.borrar(bot.id)
            # Sus movimientos se van con él: el feed no enlaza a un bot que ya no existe.
            quedan = [(n, m) for n, m in self._actividad if m.bot_id != bot.id]
            self._actividad = deque(quedan, maxlen=MAX_ACTIVIDAD)

    # -- Dinero real -------------------------------------------------------------------------------
    # Solo las rutas del panel llaman a esto, después de comprobar la confirmación tecleada: el
    # conector MCP no tiene ninguna herramienta que llegue aquí (docs/panel-v4-real.md §0.5).

    def activar_real(self, bot_id: str, exchange: str, limites: Limites) -> Bot:
        """Pasa a real un bot ficticio o de pruebas: empieza de cero con su capital máximo como
        capital (su historia de antes se archiva aparte) y no opera hasta cuadrar el saldo."""
        with self._cerrojo:
            bot = self.bot(bot_id)
            d = bot.definicion
            if d.modo == "real":
                raise real.NoSePuedeError(f"«{d.nombre}» ya opera con dinero real.")
            if self.globales().parado_todo:
                raise real.NoSePuedeError(
                    "Está puesto «Parar todo lo real»: quítalo antes de activar un bot real."
                )
            if bot.grupo is not None and bot.cuenta.posiciones:
                raise real.NoSePuedeError(
                    f"«{d.nombre}» aún tiene monedas en la red de pruebas: véndelas o espera a que "
                    "las venda antes de pasarlo a real (empieza de cero)."
                )
            if bot.estado.pausa is not None and bot.estado.pausa.motivo == "desconocido":
                raise real.NoSePuedeError(
                    "Tiene una orden de pruebas de la que no se sabe si salió: resuélvela antes."
                )
            capital = limites.capital_max
            self._comprobar_exchange(
                exchange, "real", d.monedas, real.Tenencia(capital, {}), excepto=bot.id
            )
            ahora = self.ahora()
            self.registro.archivar_historia(bot.id, f"{d.modo}-{ahora:%Y%m%d%H%M%S}")
            definicion = replace(
                d, modo="real", exchange=exchange, limites=limites, capital=capital, activado=ahora
            )
            estado = Estado(
                estado="en_marcha",
                cuenta=Cuenta(efectivo=capital, comisiones=self._comisiones),
                maximo=capital,
                peor_caida=0.0,
            )
            nuevo = Bot(definicion, estado, [])
            self.registro.guardar_definicion(definicion)
            self._bots[bot.id] = nuevo
            self._refrescar_precios(nuevo)
            self._evento(
                nuevo,
                ahora,
                "real",
                f"Dinero real activado en {self._nombre_exchange(exchange)}: capital de "
                f"{llano.numero(capital)} USDC, {self._limites_txt(limites)}. Empieza de cero.",
            )
            self._apuntar_punto(nuevo, ahora, capital)
            self._guardar(nuevo, ahora)
            self._conciliado.pop((exchange, "real"), None)
            self._seguir(nuevo)
            return nuevo

    @staticmethod
    def _limites_txt(lim: Limites) -> str:
        vender = ", y vende todo al pararse" if lim.vender_al_parar else ""
        return (
            f"máximo {llano.numero(lim.orden_max)} USDC por orden, se para si pierde un "
            f"{llano.porcentaje(lim.perdida_max_pct, 1)}{vender}, hasta "
            f"{lim.operaciones_max_dia} operaciones al día"
        )

    def cambiar_limites(self, bot_id: str, limites: Limites) -> Bot:
        """Cambia los límites de un bot de exchange (la ruta exige la activación para subirlos en
        uno real)."""
        with self._cerrojo:
            bot = self.bot(bot_id)
            if bot.grupo is None:
                raise BotInvalidoError("Un bot ficticio no tiene límites: no mueve dinero.")
            definicion = replace(bot.definicion, limites=limites)
            bot.definicion = definicion
            bot.limite_avisado = None
            self.registro.guardar_definicion(definicion)
            self._evento(
                bot, self.ahora(), "info", f"Límites cambiados: {self._limites_txt(limites)}."
            )
            self._guardar(bot, self.ahora())
            return bot

    def parar_todo_real(self, motivo: str = "Lo paraste tú.") -> tuple[list[str], int, list[str]]:
        """El interruptor: para todos los bots reales y cancela sus órdenes abiertas (solo las
        suyas). Devuelve los ids parados, cuántas órdenes se cancelaron y lo que no se pudo."""
        with self._cerrojo:
            ahora = self.ahora()
            g = self.globales()
            real.guardar_globales(
                real.Globales(g.limite_diario, True, g.parado_desde or ahora, motivo),
                self._ruta_globales,
            )
            parados: list[str] = []
            canceladas = 0
            avisos: list[str] = []
            for bot in self._bots.values():
                if bot.definicion.modo != "real":
                    continue
                if bot.estado.estado == "en_marcha":
                    bot.estado.estado = "parado"
                    bot.aviso_plantilla = None
                    self._evento(bot, ahora, "parada", f"Parado por «Parar todo lo real». {motivo}")
                    parados.append(bot.id)
                hechas, fallos = self._cancelar_abiertas(bot)
                canceladas += hechas
                avisos.extend(fallos)
                self._guardar(bot, ahora)
            return parados, canceladas, avisos

    def _cancelar_abiertas(self, bot: Bot) -> tuple[int, list[str]]:
        grupo = bot.grupo
        if grupo is None or not bot.abiertas:
            return 0, []
        canceladas = 0
        fallos: list[str] = []
        try:
            conector = self._conector_de(*grupo)
        except ExchangeError as error:
            return 0, [f"{bot.definicion.nombre}: no se pudieron cancelar sus órdenes: {error}"]
        for par, id_cliente in sorted(bot.abiertas):
            try:
                orden = conector.cancelar(par, id_cliente=id_cliente)
            except ExchangeError as error:
                fallos.append(f"{bot.definicion.nombre}: {par}: {error}")
                continue
            bot.abiertas.discard((par, id_cliente))
            if orden is not None and orden.estado in ("cancelada", "parcial"):
                canceladas += 1
        return canceladas, fallos

    def reanudar_todo_real(self) -> None:
        """Quita el interruptor; cada bot real sigue parado hasta reanudarlo uno a uno."""
        with self._cerrojo:
            g = self.globales()
            real.guardar_globales(real.Globales(g.limite_diario), self._ruta_globales)

    def cambiar_limite_diario(self, limite: Decimal | None) -> None:
        with self._cerrojo:
            g = self.globales()
            real.guardar_globales(replace(g, limite_diario=limite), self._ruta_globales)

    def _resolver_pausa(self, bot: Bot) -> None:
        """Al reanudar: la orden desconocida se consulta (y si salió, se apunta); el descuadre se
        vuelve a comprobar. `NoSePuedeError` si sigue sin resolverse."""
        pausa, grupo = bot.estado.pausa, bot.grupo
        assert pausa is not None
        if grupo is None:  # pragma: no cover - un ficticio no se pausa
            bot.estado.pausa = None
            return
        ahora = self.ahora()
        try:
            conector = self._conector_de(*grupo)
            if pausa.motivo == "desconocido" and pausa.id_cliente and pausa.coin:
                self._resolver_desconocida(bot, conector, pausa, ahora)
            elif pausa.motivo == "conciliacion":
                falta = real.descuadre(conector, self._tenencias(grupo), conector.saldo())
                if falta is not None:
                    raise real.NoSePuedeError(
                        f"Sigue sin cuadrar: {falta} Pon en el exchange lo que falta (o para y "
                        "borra el bot) antes de reanudarlo."
                    )
                for otro in self._bots.values():
                    pausa_otro = otro.estado.pausa
                    if otro.grupo == grupo and pausa_otro and pausa_otro.motivo == "conciliacion":
                        otro.estado.pausa = None
                        otro.sucio = True
                self._conciliado[grupo] = ahora
        except ExchangeError as error:
            raise real.NoSePuedeError(
                f"No se pudo consultar {self._nombre_exchange(grupo[0])}: {error} Sigue en pausa."
            ) from error
        bot.estado.pausa = None
        self._evento(bot, ahora, "info", "Pausa resuelta.")
        self._guardar(bot, ahora)

    def _resolver_desconocida(
        self, bot: Bot, conector: Conector, pausa: Pausa, ahora: datetime
    ) -> None:
        assert pausa.id_cliente is not None and pausa.coin is not None
        m = real.mercado(conector, pausa.coin)
        orden = conector.orden(m.par, id_cliente=pausa.id_cliente)
        if orden is not None and orden.estado in ("abierta", "parcial"):
            orden = conector.cancelar(m.par, id_cliente=pausa.id_cliente) or orden
        if orden is None or orden.ejecutada <= 0:
            self._evento(
                bot,
                ahora,
                "info",
                f"La orden {pausa.id_cliente} no llegó a ejecutarse en {real.nombre_exchange(conector.exchange)}: no "
                "había nada que apuntar.",
            )
            return
        self._aplicar(bot, ahora, orden, pausa.coin, "Orden que había quedado sin confirmar.")
        # Lo que tiene ha cambiado: vuelve a cuadrar antes de la siguiente orden.
        if bot.grupo is not None:
            self._conciliado.pop(bot.grupo, None)

    def _tenencias(self, grupo: tuple[str, Red]) -> list[real.Tenencia]:
        return [
            real.Tenencia(b.cuenta.efectivo, b.cuenta.cantidades())
            for b in self._bots.values()
            if b.grupo == grupo
        ]

    # -- El bucle ----------------------------------------------------------------------------------

    def paso(self) -> None:
        """Una vuelta: valora todos los bots y deja decidir a los que están en marcha."""
        self._al_dia_exchanges()
        with self._cerrojo:
            ahora = self.ahora()
            conectada = self.fuente is not None and self.fuente.conectada()
            corte = self._corte(ahora, conectada)
            hay_reales = any(b.definicion.modo == "real" for b in self._bots.values())
            globales = self.globales() if hay_reales else real.Globales()
            for bot in list(self._bots.values()):
                try:
                    self._paso_bot(bot, ahora, conectada=conectada, corte=corte, globales=globales)
                except Exception as error:
                    self._fallo(bot, ahora, error)
            if hay_reales:
                self._vigilar_limite_diario(globales)

    async def correr(self, cada: float = 1.0) -> None:
        """Da una vuelta cada `cada` segundos hasta que lo cancelen. La vuelta va en un hilo: los
        bots de exchange esperan a la red y el bucle de asyncio (las rutas) no se para."""
        while True:
            try:
                await asyncio.to_thread(self.paso)
            except Exception:  # pragma: no cover - paso() ya aísla cada bot
                log.exception("fallo en la vuelta del motor de bots")
            await asyncio.sleep(cada)

    def iniciar(self, cada: float = 1.0) -> None:
        self._tarea = asyncio.get_running_loop().create_task(self.correr(cada))

    async def detener(self) -> None:
        """Para el bucle y guarda el estado de todos."""
        if self._tarea is not None:
            self._tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tarea
            self._tarea = None
        self.guardar()

    def guardar(self) -> None:
        with self._cerrojo:
            ahora = self.ahora()
            for bot in self._bots.values():
                self._guardar(bot, ahora)

    # -- Por dentro --------------------------------------------------------------------------------

    def _corte(self, ahora: datetime, conectada: bool) -> tuple[datetime, datetime] | None:
        """El corte de precios que acaba de terminar, si duró lo bastante para apuntarlo."""
        if not conectada:
            if self.sin_precios_desde is None:
                self.sin_precios_desde = ahora
            return None
        desde, self.sin_precios_desde = self.sin_precios_desde, None
        if desde is not None and ahora - desde >= CORTE_MINIMO:
            return desde, ahora
        return None

    def _paso_bot(
        self,
        bot: Bot,
        ahora: datetime,
        *,
        conectada: bool,
        corte: tuple[datetime, datetime] | None,
        globales: real.Globales,
    ) -> None:
        e = bot.estado
        frescos = self._refrescar_precios(bot)
        if bot.grupo is not None:
            dia = real.dia_de(ahora, self._zona)
            if e.dia != dia:
                e.dia, e.operaciones_hoy = dia, 0
                bot.limite_avisado = None
                bot.sucio = True
        if e.estado == "en_marcha":
            if e.ultima_vez is not None and ahora - e.ultima_vez > self._umbral_hueco:
                self._hueco(bot, "Panel cerrado", e.ultima_vez, ahora)
            elif corte is not None:
                self._hueco(bot, "Sin precios de Hyperliquid", *corte)
            e.ultima_vez = ahora
            bloqueado = bot.definicion.modo == "real" and globales.parado_todo
            if conectada and e.pausa is None and self._cuadrado(bot) and not bloqueado:
                self._decidir(bot, ahora, frescos)
        self._valorar(bot, ahora)
        if bot.grupo is not None:
            self._vigilar_perdida(bot, ahora)
        if bot.sucio or bot.ultimo_guardado is None or ahora - bot.ultimo_guardado >= CADA_GUARDADO:
            self._guardar(bot, ahora)

    # -- Bots de exchange --------------------------------------------------------------------------

    def _al_dia_exchanges(self) -> None:
        """Lee los precios de los exchanges (cada 15 s) y su saldo para conciliar (cada 5 min, y
        antes de la primera orden). La red va fuera del cerrojo, para no frenar las rutas; lo leído
        se apunta después, con él."""
        with self._cerrojo:
            ahora = self.ahora()
            grupos: dict[tuple[str, Red], set[str]] = {}
            for bot in self._bots.values():
                if bot.grupo is not None:
                    grupos.setdefault(bot.grupo, set()).update(bot.definicion.monedas)
            precios = [
                (g, coin)
                for g, monedas in grupos.items()
                for coin in sorted(monedas)
                if self._toca(self._leido_precio, (*g, coin), CADA_PRECIO_EXCHANGE, ahora)
            ]
            for g, coin in precios:
                self._leido_precio[(*g, coin)] = ahora
            conciliar = [g for g in grupos if self._toca_conciliar(g, ahora)]
            for g in conciliar:
                self._intento_conciliar[g] = ahora
            version = self._cambios
        if not precios and not conciliar:
            return
        conectores: dict[tuple[str, Red], Conector] = {}
        fallos: dict[tuple[str, Red], str] = {}
        for g in sorted({g for g, _ in precios} | set(conciliar)):
            try:
                conectores[g] = self._conector_de(*g)
            except ExchangeError as error:
                fallos[g] = str(error)
        leidos: dict[tuple[str, Red, str], Decimal] = {}
        for g, coin in precios:
            conector = conectores.get(g)
            if conector is None:
                continue
            try:
                precio = conector.precio(real.mercado(conector, coin).par)
            except ExchangeError:
                continue
            if precio is not None and precio > 0:
                leidos[(*g, coin)] = precio
        saldos: dict[tuple[str, Red], Mapping[str, Decimal]] = {}
        for g in conciliar:
            conector = conectores.get(g)
            if conector is None:
                continue
            try:
                saldos[g] = conector.saldo()
            except ExchangeError as error:
                fallos[g] = str(error)
        with self._cerrojo:
            ahora = self.ahora()
            for clave, precio in leidos.items():
                self._precios_exchange[clave] = (ahora, precio)
            for g in conciliar:
                if g in fallos:
                    self._error_conciliar[g] = fallos[g]
                elif g in saldos and self._cambios == version:
                    self._conciliar(g, conectores[g], saldos[g], ahora)
                # Si una orden se apuntó mientras se leía el saldo, se vuelve a leer en la siguiente.
                elif g in saldos:
                    self._intento_conciliar.pop(g, None)

    @staticmethod
    def _toca(
        cuando: Mapping[tuple[str, Red, str], datetime],
        clave: tuple[str, Red, str],
        cada: timedelta,
        ahora: datetime,
    ) -> bool:
        antes = cuando.get(clave)
        return antes is None or ahora - antes >= cada

    def _toca_conciliar(self, grupo: tuple[str, Red], ahora: datetime) -> bool:
        if any(
            b.grupo == grupo
            and b.estado.pausa is not None
            and b.estado.pausa.motivo == "desconocido"
            for b in self._bots.values()
        ):
            return False  # con una orden sin resolver, el saldo no puede cuadrar: primero eso
        intento = self._intento_conciliar.get(grupo)
        if intento is not None and ahora - intento < REINTENTO_CONCILIACION:
            return False
        cuadro = self._conciliado.get(grupo)
        return cuadro is None or ahora - cuadro >= CADA_CONCILIACION

    def _conciliar(
        self,
        grupo: tuple[str, Red],
        conector: Conector,
        saldo: Mapping[str, Decimal],
        ahora: datetime,
    ) -> None:
        try:
            falta = real.descuadre(conector, self._tenencias(grupo), saldo)
        except ExchangeError as error:
            self._error_conciliar[grupo] = str(error)
            return
        self._error_conciliar.pop(grupo, None)
        if falta is None:
            self._conciliado[grupo] = ahora
            return
        self._conciliado.pop(grupo, None)
        nombre = self._nombre_exchange(grupo[0])
        texto = (
            f"No cuadra el saldo de {nombre}: {falta} Pausado hasta que lo mires: reanúdalo cuando "
            "cuadre."
        )
        for bot in self._bots.values():
            if bot.grupo == grupo and bot.estado.pausa is None:
                bot.estado.pausa = Pausa("conciliacion", texto, diferencia=falta, at=ahora)
                self._evento(bot, ahora, "conciliacion", texto)
                self._guardar(bot, ahora)

    def _orden_exchange(
        self, bot: Bot, orden: Orden, ahora: datetime
    ) -> tuple[Hecha, Decimal | None] | None:
        """Una orden de un bot de pruebas o real: límites, id guardado antes, envío y lo ejecutado
        a su cuenta. None si no sale (y se dice por qué) o no se ejecutó nada."""
        grupo, d, e = bot.grupo, bot.definicion, bot.estado
        assert grupo is not None
        cuenta = bot.cuenta
        if orden.lado == "compra":
            if orden.importe is not None:
                importe = min(orden.importe, cuenta.efectivo)
            else:
                fraccion = orden.fraccion if orden.fraccion is not None else Decimal(1)
                importe = cuenta.efectivo * fraccion
            cantidad = None
        else:
            importe = Decimal(0)
            posicion = cuenta.posiciones.get(orden.coin)
            tiene = posicion.cantidad if posicion is not None else CERO
            cantidad = min(orden.cantidad, tiene) if orden.cantidad is not None else tiene
        no = real.por_que_no(
            d.limites,
            orden.lado,
            importe,
            gastado_ahora=real.gastado(cuenta),
            operaciones_hoy=e.operaciones_hoy,
        )
        if no is not None:
            if no != bot.limite_avisado:
                self._evento(bot, ahora, "limite", no)
                bot.limite_avisado = no
            return None
        try:
            conector = self._conector_de(*grupo)
        except ExchangeError as error:
            self._aviso_exchange(bot, ahora, f"No se puede operar en su exchange: {error}")
            return None
        id_cliente = real.nuevo_id_cliente()
        # Antes de enviar, a disco: si el motor muere a mitad, al volver se sabe qué buscar.
        e.pausa = Pausa(
            "desconocido",
            f"Se estaba enviando una {orden.lado} de {nombre_hyperliquid(orden.coin)} cuando se "
            "paró el motor: no se sabe si salió. Reanúdalo para consultarla en el exchange.",
            id_cliente=id_cliente,
            at=ahora,
            coin=orden.coin,
            lado=orden.lado,
        )
        self._guardar(bot, ahora)
        try:
            enviada = real.enviar(
                conector,
                orden.coin,
                orden.lado,
                id_cliente=id_cliente,
                importe=importe if orden.lado == "compra" else None,
                cantidad=cantidad,
            )
        except OrdenPequenaError:
            e.pausa = None
            self._guardar(bot, ahora)
            return None
        except EstadoDesconocidoError as error:
            e.pausa = replace(
                e.pausa, texto=f"{error} El bot se pausa: reanúdalo para consultarla."
            )
            self._evento(bot, ahora, "desconocido", e.pausa.texto)
            self._guardar(bot, ahora)
            return None
        except ExchangeError as error:
            e.pausa = None
            self._aviso_exchange(
                bot,
                ahora,
                f"{real.nombre_exchange(conector.exchange)} no aceptó la {orden.lado}: {error}",
            )
            self._guardar(bot, ahora)
            return None
        e.pausa = None
        bot.limite_avisado = None
        hecho = self._aplicar(bot, ahora, enviada, orden.coin, orden.porque)
        if enviada.estado in ("abierta", "parcial"):
            bot.abiertas.add((enviada.par, enviada.id_cliente))
        if hecho is None:
            self._evento(
                bot,
                ahora,
                "info",
                f"La {orden.lado} de {nombre_hyperliquid(orden.coin)} no se ejecutó en "
                f"{real.nombre_exchange(conector.exchange)} (quedó {enviada.estado}).",
            )
            self._guardar(bot, ahora)
        return hecho

    def _aviso_exchange(self, bot: Bot, ahora: datetime, texto: str) -> None:
        """Un fallo del exchange que no es del bot: se apunta una vez (no en cada decisión)."""
        if texto != bot.limite_avisado:
            self._evento(bot, ahora, "error", texto)
            bot.limite_avisado = texto

    def _aplicar(
        self, bot: Bot, ahora: datetime, orden: OrdenExchange, coin: str, porque: str
    ) -> tuple[Hecha, Decimal | None] | None:
        """Lo ejecutado por el exchange: a su cuenta, al registro de órdenes y a sus operaciones."""
        grupo = bot.grupo
        assert grupo is not None
        hecha = real.hecha_de(orden, coin)
        if hecha is None:
            return None
        cuenta = bot.cuenta
        resultado: Decimal | None = None
        if hecha.lado == "venta":
            antes = cuenta.posiciones.get(coin)
            if antes is not None and antes.cantidad > 0:
                resultado = resultado_venta(
                    antes.cantidad, antes.coste, hecha.cantidad, hecha.importe, hecha.comision
                )
        cuenta.anotar(hecha)
        self._cambios += 1
        bot.estado.operaciones_hoy += 1
        try:
            self._anotar_orden(orden, grupo[0], grupo[1], bot.id)
        except Exception:  # la orden ya salió: el fallo de anotarla no la deshace
            log.exception("no se pudo anotar en el registro la orden %s", orden.id_cliente)
        self._apuntar_operacion(bot, ahora, porque, hecha, resultado)
        return hecha, resultado

    def _vigilar_perdida(self, bot: Bot, ahora: datetime) -> None:
        """Si cae hasta su pérdida máxima, se para y, si así se eligió, vende todo lo suyo."""
        d = bot.definicion
        if bot.estado.estado != "en_marcha":
            return
        texto = real.perdida_superada(d.limites, bot.valor(), d.capital)
        if texto is None:
            return
        bot.estado.estado = "parado"
        bot.aviso_plantilla = None
        self._evento(bot, ahora, "limite", texto)
        if d.limites is not None and d.limites.vender_al_parar:
            self._vender_todo(bot, ahora, "Vende todo al pararse por su pérdida máxima.")
        self._guardar(bot, ahora)

    def _vender_todo(self, bot: Bot, ahora: datetime, porque: str) -> None:
        for coin in sorted(bot.cuenta.posiciones):
            if bot.estado.pausa is not None:
                return  # una venta quedó desconocida: no se sigue a ciegas
            self._orden_exchange(bot, Orden(coin=coin, lado="venta", porque=porque), ahora)

    def _vigilar_limite_diario(self, globales: real.Globales) -> None:
        """Si los bots reales han perdido hoy su límite diario entre todos, se para todo lo real."""
        if globales.limite_diario is None or globales.parado_todo:
            return
        perdida = self.perdida_hoy()
        if perdida < globales.limite_diario:
            return
        self.parar_todo_real(
            f"Los bots reales han perdido hoy {llano.numero(perdida)} USDC entre todos y el límite "
            f"diario es {llano.numero(globales.limite_diario)} USDC."
        )

    def _velas(
        self, bot: Bot, ahora: datetime
    ) -> tuple[dict[str, list[Vela]], dict[str, datetime]]:
        """Las velas que necesita y la última cerrada de cada moneda."""
        p, d = bot.plantilla, bot.definicion
        intervalo = p.intervalo(d.parametros)
        if intervalo is None or self.fuente is None:
            return {}, {}
        # Una más que las necesarias: la última que da la fuente puede estar en curso.
        limite = p.velas_necesarias(d.parametros) + 1
        velas = {c: self.fuente.velas(c, intervalo, limite) for c in d.monedas}
        vistas: dict[str, datetime] = {}
        for coin, lista in velas.items():
            hechas = cerradas(lista, ahora)
            if hechas:
                vistas[coin] = hechas[-1].inicio
        return velas, vistas

    def _decidir(self, bot: Bot, ahora: datetime, precios: dict[str, Decimal]) -> None:
        assert self.fuente is not None
        p, d, e = bot.plantilla, bot.definicion, bot.estado
        velas, vistas = self._velas(bot, ahora)
        usa_velas = p.intervalo(d.parametros) is not None
        if usa_velas and vistas == bot.velas_vistas and bot.esperando is None:
            return  # ninguna vela nueva cerrada desde la última decisión
        decision = p.decidir(
            Situacion(
                ahora=ahora,
                capital=d.capital,
                monedas=d.monedas,
                parametros=d.parametros,
                efectivo=e.cuenta.efectivo,
                posiciones=e.cuenta.cantidades(),
                precios=precios,
                velas=velas,
                memoria=dict(e.memoria),
            )
        )
        for nota in decision.notas:
            if nota not in bot.notas_previas:
                self._evento(bot, ahora, "info", nota)
        bot.notas_previas = decision.notas
        bot.aviso_plantilla = decision.aviso

        memoria = dict(e.memoria)
        esperando: str | None = None
        # Primero las ventas: lo que cobran puede pagar las compras de la misma decisión.
        for orden in sorted(decision.ordenes, key=lambda o: o.lado != "venta"):
            if bot.grupo is not None:
                if e.pausa is not None:
                    break  # una orden quedó desconocida: no se sigue a ciegas
                hecho = self._orden_exchange(bot, orden, ahora)
                if hecho is not None:
                    memoria.update(orden.memoria)
                    if p.aplicar is not None:
                        memoria = p.aplicar(memoria, orden, hecho[0].cantidad)
                continue
            libro = self.fuente.libro(orden.coin)
            if libro is None:
                esperando = f"Sin libro de órdenes de {orden.coin}: la {orden.lado} espera."
                continue
            try:
                hecha, resultado = self._ejecutar(bot, orden, libro)
            except LibroInsuficienteError:
                esperando = (
                    f"El libro de {orden.coin} no da para la {orden.lado} ahora mismo: espera."
                )
                continue
            except OrdenPequenaError:
                continue  # por debajo del mínimo de Hyperliquid: no se hace, y no hay que esperar
            self._apuntar_operacion(bot, ahora, orden.porque, hecha, resultado)
            memoria.update(orden.memoria)
            if p.aplicar is not None:
                memoria = p.aplicar(memoria, orden, hecha.cantidad)

        if esperando is None:
            if decision.memoria:
                memoria.update(decision.memoria)
            bot.velas_vistas = vistas
        elif esperando != bot.esperando:
            self._evento(bot, ahora, "info", esperando)
        bot.esperando = esperando
        if memoria != e.memoria:
            e.memoria = memoria
            bot.sucio = True

    def _ejecutar(self, bot: Bot, orden: Orden, libro: Libro) -> tuple[Hecha, Decimal | None]:
        """La orden hecha y, si es una venta, lo que ganó o perdió (con el coste de antes)."""
        cuenta = bot.cuenta
        if orden.lado == "venta":
            antes = cuenta.posiciones.get(orden.coin)
            cantidad, coste = (antes.cantidad, antes.coste) if antes is not None else (CERO, CERO)
            hecha = cuenta.vender(libro, orden.cantidad)
            resultado = (
                resultado_venta(cantidad, coste, hecha.cantidad, hecha.importe, hecha.comision)
                if cantidad > 0
                else None
            )
            return hecha, resultado
        if orden.importe is not None:
            gastar = orden.importe
        else:
            gastar = cuenta.efectivo * (orden.fraccion if orden.fraccion is not None else 1)
        return cuenta.comprar(libro, gastar), None

    def _apuntar_operacion(
        self, bot: Bot, ahora: datetime, porque: str, hecha: Hecha, resultado: Decimal | None
    ) -> None:
        verbo = "Compré" if hecha.lado == "compra" else "Vendí"
        precio = _precio_guardado(hecha.precio)
        motivo = (
            f"{verbo} {llano.cantidad(hecha.cantidad)} {hecha.coin} a {precio_txt(precio)}: "
            f"{porque}"
        )
        operacion = Operacion(
            at=ahora,
            coin=hecha.coin,
            lado=hecha.lado,
            cantidad=hecha.cantidad,
            precio=precio,
            importe=hecha.importe,
            comision=hecha.comision,
            motivo=motivo,
        )
        self.registro.operacion(bot.id, operacion)
        self._anotar(
            de_operacion(bot.id, bot.definicion.nombre, operacion, resultado, bot.definicion.modo)
        )
        bot.estado.operaciones += 1
        bot.estado.ultima_operacion = ahora
        bot.sucio = True

    def _valorar(self, bot: Bot, ahora: datetime) -> None:
        e = bot.estado
        valor = bot.valor()
        if valor is None:
            return
        if e.maximo is None or valor > e.maximo:
            e.maximo = valor
        caida = float(valor / e.maximo - 1) if e.maximo > 0 else 0.0
        if e.peor_caida is None or caida < e.peor_caida:
            e.peor_caida = caida
        if not bot.curva or ahora - bot.curva[-1].at >= CADA_PUNTO:
            self._apuntar_punto(bot, ahora, valor)

    def _apuntar_punto(self, bot: Bot, ahora: datetime, valor: Decimal) -> None:
        mantener = bot.mantener()
        punto = Punto(ahora, usdc(valor), usdc(mantener) if mantener is not None else None)
        bot.curva.append(punto)
        self.registro.punto(bot.id, punto)

    def _hueco(self, bot: Bot, que: str, desde: datetime, hasta: datetime) -> None:
        texto = f"{que} {tramo(desde, hasta, self._zona)}: no pudo operar."
        self._evento(bot, hasta, "hueco", texto)
        bot.estado.aviso = texto
        bot.estado.aviso_hasta = hasta + AVISO_DURA
        bot.velas_vistas = None  # al volver decide con lo último, sin recuperar lo perdido

    def _fallo(self, bot: Bot, ahora: datetime, error: Exception) -> None:
        log.exception("el bot %s ha fallado", bot.id)
        if bot.estado.estado == "error":
            return
        bot.estado.estado = "error"
        bot.estado.motivo_error = f"Falló al decidir u operar: {error}"
        bot.aviso_plantilla = None
        self._evento(bot, ahora, "error", bot.estado.motivo_error)
        with contextlib.suppress(Exception):
            self._guardar(bot, ahora)

    def _evento(self, bot: Bot, ahora: datetime, tipo: TipoEvento, texto: str) -> None:
        evento = Evento(ahora, tipo, texto)
        self.registro.evento(bot.id, evento)
        self._anotar(de_evento(bot.id, bot.definicion.nombre, evento, bot.definicion.modo))
        bot.sucio = True

    def _guardar(self, bot: Bot, ahora: datetime) -> None:
        self.registro.guardar_estado(bot.id, bot.estado)
        bot.ultimo_guardado = ahora
        bot.sucio = False


# -- El motor del panel ----------------------------------------------------------------------------

_activo: Motor | None = None


def activo() -> Motor | None:
    """El motor en marcha en este proceso (el del panel), o None."""
    return _activo


def usar(motor: Motor | None) -> None:
    """Pone (o quita) el motor del proceso sin arrancar su bucle: para las pruebas de la API."""
    global _activo
    _activo = motor


def fuente_del_servicio() -> FuentePrecios | None:
    """La fuente en vivo del panel, o None si no la hay (sin servicio en vivo: tests, contrato)."""
    from invest_ll.vivo import servicio

    try:
        return servicio.fuente()
    except (NotImplementedError, RuntimeError):
        return None


async def arrancar(
    fuente: FuentePrecios | None = None,
    *,
    raiz: Path = CARPETA,
    reloj: Callable[[], datetime] = ahora_utc,
    cada: float = 1.0,
) -> None:
    """Carga los bots de `bots/` y pone en marcha los que lo estaban (apuntando el hueco)."""
    if fuente is None:
        fuente = fuente_del_servicio()
        if fuente is None:
            log.warning("sin fuente de precios en vivo: los bots no operarán")
    motor = Motor(fuente, raiz, reloj=reloj)
    motor.cargar()
    motor.iniciar(cada)
    usar(motor)


async def parar() -> None:
    """Para el bucle y deja el estado de cada bot guardado."""
    motor = _activo
    usar(None)
    if motor is not None:
        await motor.detener()
