"use client";

/**
 * Los datos en vivo del panel v3 (docs/panel-v3-vivo.md, seccion 5): UN stream SSE
 * (`GET /api/vivo/stream?coin=&intervalo=&canales=`) cuyos eventos traen exactamente el JSON de
 * su ruta REST, asi que se usan los mismos tipos generados.
 *
 * - Reconexion sola: si la conexion se corta, el navegador reintenta (EventSource); si la ruta
 *   falla del todo (404/500, o no abre en 8 s), se reintenta con espera creciente (2, 4, 8... 60 s).
 * - Si no hay stream, se pregunta a las rutas REST cada 3 s: los datos siguen llegando, y se dice.
 * - Un vigia: abierto pero 12 s sin ningun evento cuenta como cortado (el contrato no tiene
 *   latido; `monedas` y `cuenta` llegan cada ~1 s).
 * - Sin tirones: el libro y las operaciones pueden llegar muchas veces por segundo; cada canal se
 *   repinta como mucho cada 200 ms (5 veces por segundo) con lo ultimo que haya llegado. Las
 *   velas van aparte, sin React: la grafica las aplica directamente (`suscribirVela`).
 *
 * El modo de ejemplo (`npm run dev:mock`) cambia el EventSource por el stream simulado de
 * web/mocks/vivo.ts; en un `next build` esa rama ni se compila.
 */
import { createContext, createElement, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import { api, comoErrorApi, pedir, urlApi } from "./cliente";
import type { Actividad, Bots, CanalVivo, CuentaPractica, EstadoVivo, EventosVivo, LibroVivo, Monedas, MovimientoBot, OperacionMercado, VelaVivo } from "./tipos";

export const CANALES: readonly CanalVivo[] = ["monedas", "libro", "operaciones", "vela", "cuenta", "bots", "estado", "actividad"];

const REPINTADO_MS = 200;
export const SONDEO_MS = 3000;
const PLAZO_APERTURA_MS = 8000;
const SILENCIO_MS = 12_000;
const MAX_OPERACIONES = 40;
/** Los movimientos de los bots que se guardan (el feed "Ahora mismo"). */
const MAX_MOVIMIENTOS = 200;

export type Conexion =
  | { tipo: "conectando" }
  /** El stream esta abierto y llegan eventos. */
  | { tipo: "en-vivo" }
  /** El stream se corto hace poco y se esta reintentando (mientras, se pregunta por REST). */
  | { tipo: "reconectando"; intento: number }
  /** No hay stream: los datos llegan preguntando a la API cada `cadaMs`. */
  | { tipo: "sondeo"; cadaMs: number }
  /** Ni stream ni REST: lo que se ve es lo ultimo que llego. */
  | { tipo: "sin-conexion"; detalle: string };

export interface EstadoConexion {
  conexion: Conexion;
  /** Lo ultimo que dijo la API de Hyperliquid (`EstadoVivo`): conectado, fuente, aviso. */
  fuente: EstadoVivo | null;
  /** La hora (`at`) de los datos mas recientes que han llegado, en ms. */
  ultimoDato: number | null;
}

interface Datos {
  monedas: Monedas | null;
  libro: LibroVivo | null;
  operaciones: OperacionMercado[];
  cuenta: CuentaPractica | null;
  bots: Bots | null;
  /** v5: los movimientos de los bots, el mas reciente primero; null hasta el primer envio. */
  actividad: MovimientoBot[] | null;
}
type ClaveDatos = keyof Datos;

function esCanal(nombre: string): nombre is CanalVivo {
  return (CANALES as readonly string[]).includes(nombre);
}

function msDe(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/** Identidad de una operacion de mercado (el contrato no trae su id): hora, precio, cantidad y lado. */
function claveOperacion(o: OperacionMercado): string {
  return `${o.at}|${o.precio}|${o.cantidad}|${o.lado}`;
}

// -- El almacen ----------------------------------------------------------------------------------

export class AlmacenVivo {
  private datos: Datos = { monedas: null, libro: null, operaciones: [], cuenta: null, bots: null, actividad: null };
  private pendiente: Partial<Datos> = {};
  private opsPendientes: OperacionMercado[] = [];
  private movPendientes: MovimientoBot[] = [];
  /** Los ids de los movimientos que llegaron despues del primer envio: los que se resaltan. */
  readonly recientes = new Set<string>();
  private estado: EstadoConexion = { conexion: { tipo: "conectando" }, fuente: null, ultimoDato: null };
  private oyentes = new Map<ClaveDatos | "conexion", Set<() => void>>();
  private oyentesVela = new Set<(v: VelaVivo) => void>();
  private temporizador: ReturnType<typeof setTimeout> | null = null;
  private ultimoRepintado = 0;
  coin: string | null = null;
  intervalo = "1h";

  leer<K extends ClaveDatos>(k: K): Datos[K] {
    return this.datos[k];
  }

  leerConexion(): EstadoConexion {
    return this.estado;
  }

  suscribir(k: ClaveDatos | "conexion", fn: () => void): () => void {
    let s = this.oyentes.get(k);
    if (!s) {
      s = new Set();
      this.oyentes.set(k, s);
    }
    s.add(fn);
    return () => s.delete(fn);
  }

  suscribirVela(fn: (v: VelaVivo) => void): () => void {
    this.oyentesVela.add(fn);
    return () => this.oyentesVela.delete(fn);
  }

  private avisar(k: ClaveDatos | "conexion"): void {
    this.oyentes.get(k)?.forEach((fn) => fn());
  }

  /** Otra moneda u otro intervalo: lo que era de la anterior deja de valer. */
  cambiarMercado(coin: string | null, intervalo: string): void {
    const otraMoneda = coin !== this.coin;
    this.coin = coin;
    this.intervalo = intervalo;
    if (otraMoneda) {
      this.datos = { ...this.datos, libro: null, operaciones: [] };
      delete this.pendiente.libro;
      this.opsPendientes = [];
      this.avisar("libro");
      this.avisar("operaciones");
    }
  }

  fijarConexion(conexion: Conexion): void {
    const a = this.estado.conexion;
    if (a.tipo === conexion.tipo && JSON.stringify(a) === JSON.stringify(conexion)) return;
    this.estado = { ...this.estado, conexion };
    this.avisar("conexion");
  }

  private anotarHora(at: string | null | undefined): void {
    const t = msDe(at);
    if (t === null) return;
    if (this.estado.ultimoDato === null || t > this.estado.ultimoDato) {
      this.estado = { ...this.estado, ultimoDato: t };
      // La hora se repinta con el resto (no hace falta avisar 5 veces por segundo).
      this.programar();
    }
  }

  /** Un evento del stream (o una respuesta REST con la misma forma). */
  recibir<C extends CanalVivo>(canal: C, valor: EventosVivo[C]): void {
    switch (canal) {
      case "estado": {
        const v = valor as EstadoVivo;
        this.estado = { ...this.estado, fuente: v };
        this.avisar("conexion");
        return;
      }
      case "vela": {
        const v = valor as VelaVivo;
        if (v.coin !== this.coin || v.intervalo !== this.intervalo) return;
        this.oyentesVela.forEach((fn) => fn(v));
        return;
      }
      case "operaciones": {
        const nuevas = (valor as OperacionMercado[]).filter((o) => o.coin === this.coin);
        if (!nuevas.length) return;
        this.opsPendientes = [...nuevas, ...this.opsPendientes].slice(0, MAX_OPERACIONES);
        this.anotarHora(nuevas[0]?.at);
        break;
      }
      case "libro": {
        const v = valor as LibroVivo;
        if (v.coin !== this.coin) return;
        this.pendiente.libro = v;
        this.anotarHora(v.at);
        break;
      }
      case "monedas": {
        const v = valor as Monedas;
        this.pendiente.monedas = v;
        // `Monedas` trae tambien el estado de la fuente.
        this.estado = { ...this.estado, fuente: v.estado };
        this.anotarHora(v.at);
        break;
      }
      case "cuenta": {
        const v = valor as CuentaPractica;
        this.pendiente.cuenta = v;
        this.anotarHora(v.at);
        break;
      }
      case "bots": {
        const v = valor as Bots;
        this.pendiente.bots = v;
        this.anotarHora(v.at);
        break;
      }
      case "actividad": {
        const v = valor as Actividad;
        if (v.inicial) {
          // Lo ultimo que hay (al conectar o reconectar): se junta con lo que ya hubiera.
          this.movPendientes = [...this.movPendientes, ...v.movimientos];
          if (this.datos.actividad === null && !v.movimientos.length) this.datos = { ...this.datos, actividad: [] };
        } else {
          v.movimientos.forEach((x) => this.recientes.add(x.id));
          this.movPendientes = [...v.movimientos, ...this.movPendientes];
        }
        if (this.datos.actividad === null && !this.movPendientes.length) {
          this.avisar("actividad");
          return;
        }
        break;
      }
    }
    this.programar();
  }

  /** El texto JSON de un evento SSE. Lo que no se entiende se ignora (y se dice en la consola). */
  recibirTexto(nombre: string, texto: string): void {
    if (!esCanal(nombre)) return;
    let valor: unknown;
    try {
      valor = JSON.parse(texto);
    } catch {
      console.warn(`Evento «${nombre}» del stream con un JSON que no se entiende`);
      return;
    }
    // El contenido es el de la ruta REST tipada; se confia en el contrato como en `pedir`.
    this.recibir(nombre, valor as EventosVivo[typeof nombre]);
  }

  /** La lista entera de operaciones (REST): sustituye a la que hubiera, sin duplicar. */
  fijarOperaciones(lista: OperacionMercado[]): void {
    const vistas = new Set(lista.map(claveOperacion));
    const propias = this.datos.operaciones.filter((o) => !vistas.has(claveOperacion(o)));
    // Las del stream que la REST aun no trae (mas nuevas) se quedan delante.
    const nuevas = propias.filter((o) => (msDe(o.at) ?? 0) > (msDe(lista[0]?.at) ?? 0));
    this.datos = { ...this.datos, operaciones: [...nuevas, ...lista.filter((o) => o.coin === this.coin)].slice(0, MAX_OPERACIONES) };
    this.anotarHora(lista[0]?.at);
    this.avisar("operaciones");
  }

  /** Al momento, sin esperar al stream: la cuenta que devuelve una orden, por ejemplo. */
  fijarYa<K extends "cuenta" | "bots">(k: K, valor: Datos[K]): void {
    delete this.pendiente[k];
    this.datos = { ...this.datos, [k]: valor };
    this.avisar(k);
  }

  private programar(): void {
    if (this.temporizador !== null) return;
    const espera = Math.max(0, REPINTADO_MS - (Date.now() - this.ultimoRepintado));
    this.temporizador = setTimeout(() => this.repintar(), espera);
  }

  private repintar(): void {
    this.temporizador = null;
    this.ultimoRepintado = Date.now();
    const cambiados: ClaveDatos[] = [];
    const p = this.pendiente;
    this.pendiente = {};
    let datos = this.datos;
    for (const k of ["monedas", "libro", "cuenta", "bots"] as const) {
      if (p[k] !== undefined) {
        datos = { ...datos, [k]: p[k] };
        cambiados.push(k);
      }
    }
    if (this.movPendientes.length) {
      const juntos = new Map<string, MovimientoBot>();
      for (const x of [...this.movPendientes, ...(datos.actividad ?? [])]) if (!juntos.has(x.id)) juntos.set(x.id, x);
      this.movPendientes = [];
      const lista = [...juntos.values()].sort((a, b) => (msDe(b.at) ?? 0) - (msDe(a.at) ?? 0)).slice(0, MAX_MOVIMIENTOS);
      datos = { ...datos, actividad: lista };
      cambiados.push("actividad");
    }
    if (this.opsPendientes.length) {
      const vistas = new Set(datos.operaciones.map(claveOperacion));
      const nuevas = this.opsPendientes.filter((o) => !vistas.has(claveOperacion(o)));
      this.opsPendientes = [];
      if (nuevas.length) {
        datos = { ...datos, operaciones: [...nuevas, ...datos.operaciones].slice(0, MAX_OPERACIONES) };
        cambiados.push("operaciones");
      }
    }
    this.datos = datos;
    cambiados.forEach((k) => this.avisar(k));
    this.avisar("conexion");
  }

  destruir(): void {
    if (this.temporizador !== null) clearTimeout(this.temporizador);
    this.temporizador = null;
  }
}

// -- Transporte -----------------------------------------------------------------------------------

interface Manejadores {
  abierto: () => void;
  evento: (nombre: string, datos: string) => void;
  /** `cerrado`: el navegador no va a reintentar (la ruta fallo); si no, esta reintentando. */
  error: (cerrado: boolean) => void;
}
type Abrir = (params: URLSearchParams, m: Manejadores) => () => void;

const abrirEventSource: Abrir = (params, m) => {
  const es = new EventSource(urlApi(`/api/vivo/stream?${params.toString()}`));
  es.onopen = () => m.abierto();
  for (const canal of CANALES) {
    es.addEventListener(canal, (e) => {
      if (e instanceof MessageEvent && typeof e.data === "string") m.evento(canal, e.data);
    });
  }
  es.onerror = () => m.error(es.readyState === EventSource.CLOSED);
  return () => es.close();
};

async function transporte(): Promise<Abrir> {
  // Misma condicion que en api/cliente.ts: en `next build` es falsa y el simulador no se incluye.
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK === "1") {
    return (await import("@mocks/vivo")).abrirStream;
  }
  return abrirEventSource;
}

// -- La conexion ----------------------------------------------------------------------------------

interface Peticion {
  coin: string | null;
  intervalo: string;
  canales: readonly CanalVivo[];
}

class ConexionVivo {
  private cerrarStream: (() => void) | null = null;
  private abiertoAlgunaVez = false;
  private intento = 0;
  private reintento: ReturnType<typeof setTimeout> | null = null;
  private sondeo: ReturnType<typeof setInterval> | null = null;
  private inicioSondeo: ReturnType<typeof setTimeout> | null = null;
  private vigia: ReturnType<typeof setInterval> | null = null;
  private ultimoEvento = 0;
  private abierto = false;
  private parado = false;

  constructor(
    private readonly almacen: AlmacenVivo,
    private readonly p: Peticion,
  ) {}

  private quiere(c: CanalVivo): boolean {
    return this.p.canales.includes(c);
  }

  iniciar(): void {
    void this.preguntar(true);
    void this.conectar();
    this.vigia = setInterval(() => {
      if (this.abierto && Date.now() - this.ultimoEvento > SILENCIO_MS) this.falloStream(true);
    }, 2000);
  }

  parar(): void {
    this.parado = true;
    this.cerrarStream?.();
    this.cerrarStream = null;
    for (const t of [this.reintento, this.inicioSondeo]) if (t !== null) clearTimeout(t);
    for (const t of [this.sondeo, this.vigia]) if (t !== null) clearInterval(t);
  }

  private async conectar(): Promise<void> {
    this.reintento = null;
    const abrir = await transporte();
    if (this.parado) return;
    const params = new URLSearchParams();
    if (this.p.coin) params.set("coin", this.p.coin);
    params.set("intervalo", this.p.intervalo);
    params.set("canales", this.p.canales.join(","));
    let abiertoEste = false;
    const plazo = setTimeout(() => {
      if (!abiertoEste) this.falloStream(true);
    }, PLAZO_APERTURA_MS);
    this.cerrarStream = abrir(params, {
      abierto: () => {
        if (this.parado) return;
        abiertoEste = true;
        clearTimeout(plazo);
        this.abierto = true;
        this.abiertoAlgunaVez = true;
        this.intento = 0;
        this.ultimoEvento = Date.now();
        this.pararSondeo();
        this.almacen.fijarConexion({ tipo: "en-vivo" });
      },
      evento: (nombre, datos) => {
        if (this.parado) return;
        this.ultimoEvento = Date.now();
        this.almacen.recibirTexto(nombre, datos);
      },
      error: (cerrado) => {
        if (this.parado) return;
        // Antes de abrir, un error "reintentando" es el navegador probando: decide el plazo.
        if (!abiertoEste && !cerrado) return;
        clearTimeout(plazo);
        this.falloStream(cerrado);
      },
    });
  }

  private falloStream(cerrado: boolean): void {
    if (this.parado) return;
    this.abierto = false;
    this.intento += 1;
    if (!cerrado) {
      // El EventSource reintenta solo. Si tarda, se empieza a preguntar por REST.
      this.almacen.fijarConexion({ tipo: "reconectando", intento: this.intento });
      if (this.inicioSondeo === null && this.sondeo === null) {
        this.inicioSondeo = setTimeout(() => {
          this.inicioSondeo = null;
          if (!this.abierto) this.empezarSondeo();
        }, 4000);
      }
      return;
    }
    this.cerrarStream?.();
    this.cerrarStream = null;
    const espera = Math.min(60_000, 2000 * 2 ** Math.min(this.intento - 1, 5));
    this.almacen.fijarConexion(
      this.abiertoAlgunaVez && this.intento <= 2 ? { tipo: "reconectando", intento: this.intento } : { tipo: "sondeo", cadaMs: SONDEO_MS },
    );
    this.empezarSondeo();
    if (this.reintento === null) this.reintento = setTimeout(() => void this.conectar(), espera);
  }

  private empezarSondeo(): void {
    if (this.sondeo !== null || this.parado) return;
    void this.preguntar(false);
    this.sondeo = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      void this.preguntar(false);
    }, SONDEO_MS);
  }

  private pararSondeo(): void {
    if (this.inicioSondeo !== null) clearTimeout(this.inicioSondeo);
    this.inicioSondeo = null;
    if (this.sondeo !== null) clearInterval(this.sondeo);
    this.sondeo = null;
  }

  /** Lo mismo que trae el stream, pidiendolo a las rutas REST (al empezar y en el sondeo). */
  private async preguntar(inicial: boolean): Promise<void> {
    const { coin, intervalo } = this.p;
    const a = this.almacen;
    const tareas: Promise<unknown>[] = [];
    if (this.quiere("monedas")) tareas.push(pedir(api.GET("/api/vivo/monedas")).then((v) => a.recibir("monedas", v)));
    else if (this.quiere("estado")) tareas.push(pedir(api.GET("/api/vivo/estado")).then((v) => a.recibir("estado", v)));
    if (coin && this.quiere("libro")) tareas.push(pedir(api.GET("/api/vivo/libro", { params: { query: { coin } } })).then((v) => a.recibir("libro", v)));
    if (coin && this.quiere("operaciones")) {
      tareas.push(pedir(api.GET("/api/vivo/operaciones", { params: { query: { coin } } })).then((v) => a.fijarOperaciones(v.operaciones)));
    }
    // La grafica pide su historico ella misma; aqui solo la vela en curso (y la que acaba de cerrar).
    if (!inicial && coin && this.quiere("vela")) {
      tareas.push(
        pedir(api.GET("/api/vivo/velas", { params: { query: { coin, intervalo, limite: 2 } } })).then((v) => v.velas.forEach((vela) => a.recibir("vela", vela))),
      );
    }
    if (this.quiere("cuenta")) tareas.push(pedir(api.GET("/api/practica")).then((v) => a.recibir("cuenta", v)));
    if (this.quiere("bots")) tareas.push(pedir(api.GET("/api/bots")).then((v) => a.recibir("bots", v)));
    if (this.quiere("actividad")) tareas.push(pedir(api.GET("/api/actividad")).then((v) => a.recibir("actividad", { ...v, inicial: true })));
    const resultados = await Promise.allSettled(tareas);
    if (this.parado || inicial || this.abierto) return;
    const fallos = resultados.filter((r): r is PromiseRejectedResult => r.status === "rejected");
    if (fallos.length && fallos.length === resultados.length) {
      this.almacen.fijarConexion({ tipo: "sin-conexion", detalle: comoErrorApi(fallos[0]?.reason).detalle });
    } else if (this.almacen.leerConexion().conexion.tipo === "sin-conexion") {
      this.almacen.fijarConexion({ tipo: "sondeo", cadaMs: SONDEO_MS });
    }
  }
}

// -- React ---------------------------------------------------------------------------------------

const Contexto = createContext<AlmacenVivo | null>(null);

/**
 * Abre el stream para lo que pide la pantalla (moneda, intervalo y canales) y lo reparte a los
 * componentes de dentro. Cambiar de moneda o de intervalo vuelve a abrirlo con los nuevos.
 */
export function ProveedorVivo({
  coin = null,
  intervalo = "1h",
  canales = CANALES,
  children,
}: {
  coin?: string | null;
  intervalo?: string;
  canales?: readonly CanalVivo[];
  children: ReactNode;
}) {
  const [almacen] = useState(() => new AlmacenVivo());
  const claveCanales = canales.join(",");

  useEffect(() => {
    const lista = claveCanales.split(",").filter(esCanal);
    almacen.cambiarMercado(coin, intervalo);
    const c = new ConexionVivo(almacen, { coin, intervalo, canales: lista });
    c.iniciar();
    return () => c.parar();
  }, [almacen, coin, intervalo, claveCanales]);

  useEffect(() => () => almacen.destruir(), [almacen]);

  return createElement(Contexto.Provider, { value: almacen }, children);
}

export function useAlmacenVivo(): AlmacenVivo {
  const a = useContext(Contexto);
  if (!a) throw new Error("useAlmacenVivo fuera de <ProveedorVivo>");
  return a;
}

const SIN_NADA: EstadoConexion = { conexion: { tipo: "conectando" }, fuente: null, ultimoDato: null };

/** Un canal del stream como estado de React (se repinta como mucho 5 veces por segundo). */
export function useVivo<K extends ClaveDatos>(k: K): Datos[K] {
  const a = useAlmacenVivo();
  return useSyncExternalStore(
    (fn) => a.suscribir(k, fn),
    () => a.leer(k),
    () => a.leer(k),
  );
}

export function useConexionVivo(): EstadoConexion {
  const a = useContext(Contexto);
  return useSyncExternalStore(
    (fn) => (a ? a.suscribir("conexion", fn) : () => undefined),
    () => (a ? a.leerConexion() : SIN_NADA),
    () => SIN_NADA,
  );
}
