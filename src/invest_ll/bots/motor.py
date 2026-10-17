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

**Huecos.** Los bots solo funcionan con el panel abierto. Al volver (o si el equipo se suspendió),
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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from invest_ll import llano
from invest_ll.bots.cuenta import (
    Cuenta,
    Hecha,
    OrdenPequenaError,
    cantidades_mantener,
    usdc,
    valor_mantener,
)
from invest_ll.bots.decisiones import Orden, Situacion, cerradas, precio_txt, y
from invest_ll.bots.plantillas import Plantilla, plantilla, validar
from invest_ll.bots.registro import (
    CARPETA,
    BotNoEncontradoError,
    Definicion,
    Estado,
    Evento,
    Operacion,
    Punto,
    Registro,
    TipoEvento,
    nuevo_id,
)
from invest_ll.nombres import nombre_llano
from invest_ll.vivo.ejecucion import COMISIONES, Comisiones, LibroInsuficienteError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Mapping, Sequence
    from datetime import tzinfo
    from pathlib import Path

    from invest_ll.vivo.fuente import FuentePrecios, Libro, Vela

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
NOTA: Final = "Dinero ficticio. Los bots solo funcionan con el panel abierto."


def ahora_utc() -> datetime:
    return datetime.now(UTC)


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
        self.plantilla: Plantilla = plantilla(definicion.plantilla)
        # Solo en memoria: se rehace al cargar.
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
    ) -> None:
        self.fuente = fuente
        self.registro = Registro(raiz)
        self._reloj = reloj
        self._zona = zona
        self._comisiones = comisiones
        self._umbral_hueco = umbral_hueco
        self._bots: dict[str, Bot] = {}
        self._cerrojo = threading.RLock()
        self._tarea: asyncio.Task[None] | None = None
        self.sin_precios_desde: datetime | None = None
        """Desde cuándo la fuente no da precios (o None si los da)."""

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

    def _seguir(self, bot: Bot) -> None:
        if self.fuente is None:
            return
        intervalo = bot.plantilla.intervalo(bot.definicion.parametros)
        for coin in bot.definicion.monedas:
            self.fuente.seguir(coin, libro=True, intervalos=(intervalo,) if intervalo else ())

    def _precio(self, coin: str) -> Decimal | None:
        return self.fuente.precio(coin) if self.fuente is not None else None

    def _refrescar_precios(self, bot: Bot) -> dict[str, Decimal]:
        """Los precios de ahora de sus monedas (los que se conozcan), apuntados en el bot."""
        e = bot.estado
        frescos: dict[str, Decimal] = {}
        for coin in bot.definicion.monedas:
            precio = self._precio(coin)
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
        return bot.aviso(self.ahora(), self.sin_precios_desde, self._zona)

    def operaciones(self, bot_id: str) -> list[Operacion]:
        """La más reciente primero (las últimas `MAX_OPERACIONES`)."""
        return list(reversed(self.registro.operaciones(self.bot(bot_id).id)))[:MAX_OPERACIONES]

    def eventos(self, bot_id: str) -> list[Evento]:
        """El más reciente primero (los últimos `MAX_EVENTOS`)."""
        return list(reversed(self.registro.eventos(self.bot(bot_id).id)))[:MAX_EVENTOS]

    def desplegar(
        self,
        clave: str,
        nombre: str,
        monedas: Sequence[str],
        capital: Decimal,
        parametros: Mapping[str, str],
    ) -> Bot:
        """Valida, crea el bot en disco y lo pone en marcha (decide en la vuelta siguiente)."""
        with self._cerrojo:
            v = validar(clave, nombre, monedas, capital, parametros, self._precio)
            ahora = self.ahora()
            definicion = Definicion(
                id=nuevo_id(v.nombre),
                nombre=v.nombre,
                plantilla=v.plantilla.clave,
                monedas=v.monedas,
                capital=v.capital,
                parametros=v.parametros,
                creado=ahora,
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
            monedas_txt = y([nombre_llano(c) for c in v.monedas])
            self._evento(
                bot,
                ahora,
                "arranque",
                f"Desplegado con {llano.numero(v.capital)} USDC ficticios en {monedas_txt}.",
            )
            self._apuntar_punto(bot, ahora, v.capital)
            self._bots[definicion.id] = bot
            self._seguir(bot)
            return bot

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
        with self._cerrojo:
            bot = self.bot(bot_id)
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
        with self._cerrojo:
            bot = self.bot(bot_id)
            del self._bots[bot.id]
            self.registro.borrar(bot.id)

    # -- El bucle ----------------------------------------------------------------------------------

    def paso(self) -> None:
        """Una vuelta: valora todos los bots y deja decidir a los que están en marcha."""
        with self._cerrojo:
            ahora = self.ahora()
            conectada = self.fuente is not None and self.fuente.conectada()
            corte = self._corte(ahora, conectada)
            for bot in list(self._bots.values()):
                try:
                    self._paso_bot(bot, ahora, conectada=conectada, corte=corte)
                except Exception as error:
                    self._fallo(bot, ahora, error)

    async def correr(self, cada: float = 1.0) -> None:
        """Da una vuelta cada `cada` segundos hasta que lo cancelen."""
        while True:
            try:
                self.paso()
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
    ) -> None:
        e = bot.estado
        frescos = self._refrescar_precios(bot)
        if e.estado == "en_marcha":
            if e.ultima_vez is not None and ahora - e.ultima_vez > self._umbral_hueco:
                self._hueco(bot, "Panel cerrado", e.ultima_vez, ahora)
            elif corte is not None:
                self._hueco(bot, "Sin precios de Hyperliquid", *corte)
            e.ultima_vez = ahora
            if conectada:
                self._decidir(bot, ahora, frescos)
        self._valorar(bot, ahora)
        if bot.sucio or bot.ultimo_guardado is None or ahora - bot.ultimo_guardado >= CADA_GUARDADO:
            self._guardar(bot, ahora)

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
            libro = self.fuente.libro(orden.coin)
            if libro is None:
                esperando = f"Sin libro de órdenes de {orden.coin}: la {orden.lado} espera."
                continue
            try:
                hecha = self._ejecutar(bot, orden, libro)
            except LibroInsuficienteError:
                esperando = (
                    f"El libro de {orden.coin} no da para la {orden.lado} ahora mismo: espera."
                )
                continue
            except OrdenPequenaError:
                continue  # por debajo del mínimo de Hyperliquid: no se hace, y no hay que esperar
            self._apuntar_operacion(bot, ahora, orden, hecha)
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

    def _ejecutar(self, bot: Bot, orden: Orden, libro: Libro) -> Hecha:
        cuenta = bot.cuenta
        if orden.lado == "venta":
            return cuenta.vender(libro, orden.cantidad)
        if orden.importe is not None:
            gastar = orden.importe
        else:
            gastar = cuenta.efectivo * (orden.fraccion if orden.fraccion is not None else 1)
        return cuenta.comprar(libro, gastar)

    def _apuntar_operacion(self, bot: Bot, ahora: datetime, orden: Orden, hecha: Hecha) -> None:
        verbo = "Compré" if hecha.lado == "compra" else "Vendí"
        precio = _precio_guardado(hecha.precio)
        motivo = (
            f"{verbo} {llano.cantidad(hecha.cantidad)} {hecha.coin} a {precio_txt(precio)}: "
            f"{orden.porque}"
        )
        self.registro.operacion(
            bot.id,
            Operacion(
                at=ahora,
                coin=hecha.coin,
                lado=hecha.lado,
                cantidad=hecha.cantidad,
                precio=precio,
                importe=hecha.importe,
                comision=hecha.comision,
                motivo=motivo,
            ),
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
        self.registro.evento(bot.id, Evento(ahora, tipo, texto))
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
