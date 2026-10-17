/**
 * El panel v3 en el modo de ejemplo (docs/panel-v3-vivo.md): un mercado de mentira que se mueve
 * solo (paseo aleatorio con semilla), la cuenta de practica y los bots, con las MISMAS rutas que
 * la API (`/api/vivo/*`, `/api/practica*`, `/api/bots*`) y un stream simulado que emite cada
 * ~250 ms los mismos eventos que `GET /api/vivo/stream`.
 *
 * Todo cuerpo va tipado con el contrato (`S["..."]`): si `web/openapi.json` cambia, `tsc` falla
 * aqui. Solo existe con `npm run dev:mock` (NEXT_PUBLIC_MOCK=1); `next build` no lo incluye.
 *
 * La ejecucion ficticia imita a invest_ll/vivo/ejecucion.py: a mercado recorre el libro nivel a
 * nivel con comision de tomador; con limite espera a que el precio la cruce y paga la de creador.
 */
import type { components } from "@/api/esquema";
import { COMISION_CREADOR, COMISION_TOMADOR, decimalesPrecio, esIntervalo, msIntervalo, pasoPrecio, truncar } from "@/lib/vivo";

import { escenarioActual, type Escenario } from "./escenarios";

type S = components["schemas"];

// -- Azar con semilla -----------------------------------------------------------------------------

function mulberry32(semilla: number): () => number {
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function semilla(texto: string): number {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i++) h = Math.imul(h ^ texto.charCodeAt(i), 16777619);
  return h >>> 0;
}

function normal(rnd: () => number): number {
  const u = Math.max(rnd(), 1e-12);
  const v = rnd();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function poisson(rnd: () => number, lambda: number): number {
  const l = Math.exp(-lambda);
  let k = 0;
  let p = 1;
  do {
    k += 1;
    p *= rnd();
  } while (p > l && k < 20);
  return k - 1;
}

const iso = (ms: number): string => new Date(ms).toISOString();
const PASO_MS = 250;
const DIA_MS = 86_400_000;

// -- Monedas --------------------------------------------------------------------------------------

interface DefMoneda {
  coin: string;
  nombre: string;
  precio: number;
  /** Volumen de 24 h en USDC. */
  volumen: number;
  /** `decimales_cantidad` (szDecimals de Hyperliquid). */
  dec: number;
  /** Volatilidad diaria (fraccion). */
  vol: number;
  /** Variacion de las ultimas 24 h al arrancar, en %. */
  var24: number;
}

// Inventadas, con ordenes de magnitud creibles para octubre de 2026. Las mas negociadas primero.
const DEFS: DefMoneda[] = [
  { coin: "BTC", nombre: "Bitcoin", precio: 67420, volumen: 1.86e9, dec: 5, vol: 0.032, var24: 2.14 },
  { coin: "ETH", nombre: "Ethereum", precio: 2451.3, volumen: 9.3e8, dec: 4, vol: 0.041, var24: -0.82 },
  { coin: "SOL", nombre: "Solana", precio: 152.84, volumen: 3.1e8, dec: 2, vol: 0.055, var24: 3.47 },
  { coin: "HYPE", nombre: "Hyperliquid", precio: 38.412, volumen: 2.4e8, dec: 2, vol: 0.07, var24: 5.92 },
  { coin: "XRP", nombre: "XRP", precio: 0.58214, volumen: 1.2e8, dec: 0, vol: 0.05, var24: -1.31 },
  { coin: "DOGE", nombre: "Dogecoin", precio: 0.12874, volumen: 9.6e7, dec: 0, vol: 0.06, var24: 0.44 },
  { coin: "SUI", nombre: "Sui", precio: 1.9473, volumen: 7.8e7, dec: 1, vol: 0.07, var24: -4.08 },
  { coin: "kPEPE", nombre: "Pepe (por mil)", precio: 0.010231, volumen: 6.1e7, dec: 0, vol: 0.09, var24: 7.66 },
  { coin: "AVAX", nombre: "Avalanche", precio: 27.115, volumen: 4.2e7, dec: 2, vol: 0.06, var24: -2.2 },
  { coin: "LINK", nombre: "Chainlink", precio: 11.482, volumen: 3.9e7, dec: 1, vol: 0.055, var24: 1.05 },
  { coin: "BNB", nombre: "BNB", precio: 586.2, volumen: 3.3e7, dec: 3, vol: 0.035, var24: 0.31 },
  { coin: "ADA", nombre: "Cardano", precio: 0.35121, volumen: 2.6e7, dec: 0, vol: 0.055, var24: -0.97 },
  { coin: "LTC", nombre: "Litecoin", precio: 68.41, volumen: 1.9e7, dec: 2, vol: 0.045, var24: 0.12 },
  { coin: "TON", nombre: "Toncoin", precio: 5.2142, volumen: 1.4e7, dec: 1, vol: 0.05, var24: -3.4 },
  { coin: "AAVE", nombre: "Aave", precio: 146.31, volumen: 1.2e7, dec: 2, vol: 0.06, var24: 2.81 },
  { coin: "ARB", nombre: "Arbitrum", precio: 0.54312, volumen: 1.1e7, dec: 1, vol: 0.065, var24: -1.9 },
  { coin: "OP", nombre: "Optimism", precio: 1.6122, volumen: 9.1e6, dec: 1, vol: 0.065, var24: -2.6 },
  { coin: "NEAR", nombre: "NEAR Protocol", precio: 4.8712, volumen: 8.2e6, dec: 1, vol: 0.06, var24: 1.6 },
];

const NIVELES = 20;
const MAX_OPERACIONES = 80;

interface OperacionInterna {
  seq: number;
  op: S["OperacionMercado"];
}

interface EstadoMoneda {
  def: DefMoneda;
  precio: number;
  hace24h: number;
  volumen24h: number;
  paso: number;
  separacion: number;
  decPrecio: number;
  compras: number[];
  ventas: number[];
  ordenesC: number[];
  ordenesV: number[];
  /** Diferencial en pasos de precio (1 o 2). */
  hueco: number;
  operaciones: OperacionInterna[];
  /** Velas por intervalo: el historico y, al final, la que esta en curso. */
  velas: Map<string, S["VelaVivo"][]>;
}

function redondearPrecio(valor: number, paso: number, dec: number): number {
  return Number((Math.round(valor / paso) * paso).toFixed(dec));
}

function tamanoNivel(rnd: () => number, m: EstadoMoneda, i: number): number {
  // Lo que suele haber en un nivel: mas cuanto mas lejos del precio, con mucha variedad.
  const nocional = (m.def.volumen / 1.2e5) * (0.6 + i * 0.12) * Math.exp(normal(rnd) * 0.7);
  return Math.max(10 ** -m.def.dec, truncar(nocional / m.precio, m.def.dec));
}

function nuevaMoneda(def: DefMoneda, rnd: () => number): EstadoMoneda {
  const paso = pasoPrecio(def.precio, def.dec);
  const decPrecio = decimalesPrecio(def.precio, def.dec);
  const separacion = Math.max(paso, Math.round((def.precio * 0.00003) / paso) * paso);
  const m: EstadoMoneda = {
    def,
    precio: def.precio,
    hace24h: def.precio / (1 + def.var24 / 100),
    volumen24h: def.volumen,
    paso,
    separacion,
    decPrecio,
    compras: [],
    ventas: [],
    ordenesC: [],
    ordenesV: [],
    hueco: 1,
    operaciones: [],
    velas: new Map(),
  };
  for (let i = 0; i < NIVELES; i++) {
    m.compras.push(tamanoNivel(rnd, m, i));
    m.ventas.push(tamanoNivel(rnd, m, i));
    m.ordenesC.push(1 + Math.floor(rnd() * (3 + i)));
    m.ordenesV.push(1 + Math.floor(rnd() * (3 + i)));
  }
  return m;
}

// -- Cuenta de practica y bots (estado) -----------------------------------------------------------

interface PosMock {
  cantidad: number;
  /** Lo pagado por lo que se tiene, comisiones incluidas. */
  coste: number;
}

interface OrdenMock {
  id: string;
  coin: string;
  lado: "compra" | "venta";
  cantidad: number;
  precio: number;
  /** USDC apartados (compras): importe + comision de creador. */
  apartado: number;
  creada: number;
}

interface CuentaMock {
  inicial: number;
  saldo: number;
  posiciones: Map<string, PosMock>;
  ordenes: OrdenMock[];
  historial: S["EjecucionPractica"][];
}

interface PuntoMock {
  t: number;
  v: number;
}

interface BotMock {
  id: string;
  nombre: string;
  plantilla: string;
  monedas: string[];
  estado: S["ResumenBot"]["estado"];
  motivo_error: string | null;
  desde: number;
  capital: number;
  efectivo: number;
  posiciones: Map<string, PosMock>;
  /** Precio de cada moneda al arrancar: lo que habria hecho "solo mantener". */
  precioInicio: Record<string, number>;
  curva: PuntoMock[];
  curvaMantener: PuntoMock[];
  operaciones: S["OperacionBot"][];
  eventos: S["EventoBot"][];
  parametros: Record<string, string>;
  aviso: string | null;
  ultimaActividad: number | null;
  /** Rejilla: el escalon (fino, ver FINO) en que estaba el precio la ultima vez. */
  escalon: number | null;
  /** Compra periodica: cuando toca la siguiente compra. */
  proxima: number | null;
}

interface MundoVivo {
  escenario: Escenario;
  rnd: () => number;
  monedas: Map<string, EstadoMoneda>;
  t: number;
  seq: number;
  conectado: boolean;
  /** Desde cuando llegan datos sin cortes (o desde cuando no llegan, si desconectado). */
  desde: number;
  cuenta: CuentaMock;
  bots: BotMock[];
  siguiente: number;
  ultimaCurva: number;
}

let mundo: MundoVivo | null = null;

const SIN_BOTS: readonly Escenario[] = ["sin-bots", "cuenta-vacia", "vacio", "primera-vez"];
const CUENTA_VACIA: readonly Escenario[] = ["cuenta-vacia", "vacio", "primera-vez"];

function elMundo(): MundoVivo {
  const e = escenarioActual("con-plan");
  if (mundo && mundo.escenario === e) return mundo;
  const rnd = mulberry32(semilla(`vivo:${e}`));
  const ahora = Date.now();
  const monedas = new Map<string, EstadoMoneda>();
  for (const d of DEFS) monedas.set(d.coin, nuevaMoneda(d, rnd));
  const m: MundoVivo = {
    escenario: e,
    rnd,
    monedas,
    t: ahora,
    seq: 0,
    conectado: e !== "desconectado",
    desde: e === "desconectado" ? ahora - 7 * 60_000 - 23_000 : ahora - 3 * 3_600_000 - 12 * 60_000,
    cuenta: CUENTA_VACIA.includes(e) ? cuentaNueva(10_000) : cuentaEjemplo(monedas, ahora),
    bots: [],
    siguiente: 1,
    ultimaCurva: ahora,
  };
  mundo = m;
  if (!SIN_BOTS.includes(e)) m.bots = botsEjemplo(m, ahora);
  // Unas cuantas operaciones de mercado para que la lista no empiece vacia.
  for (const mon of monedas.values()) {
    for (let i = 0; i < 30; i++) operacionMercado(m, mon, ahora - (30 - i) * 1700, rnd() < 0.5 ? "compra" : "venta");
  }
  return m;
}

// -- El paso del tiempo ---------------------------------------------------------------------------

function mejorCompra(m: EstadoMoneda): number {
  return redondearPrecio(m.precio - (m.hueco * m.paso) / 2, m.paso, m.decPrecio);
}

function mejorVenta(m: EstadoMoneda): number {
  return redondearPrecio(mejorCompra(m) + m.hueco * m.paso, m.paso, m.decPrecio);
}

function operacionMercado(mundo: MundoVivo, m: EstadoMoneda, t: number, lado: "compra" | "venta"): void {
  const rnd = mundo.rnd;
  const nocional = (m.def.volumen / 2.2e5) * Math.exp(normal(rnd) * 1.1);
  const cantidad = Math.max(10 ** -m.def.dec, truncar(nocional / m.precio, m.def.dec));
  const precio = lado === "compra" ? mejorVenta(m) : mejorCompra(m);
  mundo.seq += 1;
  m.operaciones.unshift({ seq: mundo.seq, op: { coin: m.def.coin, at: iso(t), precio, cantidad, lado } });
  if (m.operaciones.length > MAX_OPERACIONES) m.operaciones.length = MAX_OPERACIONES;
  m.volumen24h += cantidad * precio;
  for (const velas of m.velas.values()) {
    const ultima = velas[velas.length - 1];
    if (ultima && !ultima.cerrada) ultima.volumen = Number((ultima.volumen + cantidad).toFixed(m.def.dec));
  }
}

function moverMoneda(mundo: MundoVivo, m: EstadoMoneda, t: number): void {
  const rnd = mundo.rnd;
  // Volatilidad de 250 ms algo exagerada (x4) para que en la demostracion se vea moverse.
  const sigma = (m.def.vol / Math.sqrt(DIA_MS / PASO_MS)) * 4;
  const vuelta = -0.002 * Math.log(m.precio / m.def.precio);
  const antes = m.precio;
  m.precio = Math.max(m.paso * 10, m.precio * Math.exp(sigma * normal(rnd) + vuelta));
  m.hueco = rnd() < 0.75 ? 1 : 2;
  // El libro cambia a trozos: unos niveles crecen, otros se vacian y se rellenan.
  for (let i = 0; i < NIVELES; i++) {
    if (rnd() < 0.35) m.compras[i] = rnd() < 0.08 ? tamanoNivel(rnd, m, i) : truncar((m.compras[i] ?? 0) * Math.exp(normal(rnd) * 0.25), m.def.dec) || tamanoNivel(rnd, m, i);
    if (rnd() < 0.35) m.ventas[i] = rnd() < 0.08 ? tamanoNivel(rnd, m, i) : truncar((m.ventas[i] ?? 0) * Math.exp(normal(rnd) * 0.25), m.def.dec) || tamanoNivel(rnd, m, i);
    if (rnd() < 0.15) m.ordenesC[i] = 1 + Math.floor(rnd() * (3 + i));
    if (rnd() < 0.15) m.ordenesV[i] = 1 + Math.floor(rnd() * (3 + i));
  }
  // Operaciones: mas cuanto mas se negocia la moneda, y del lado hacia el que se movio.
  const lambda = Math.min(2.5, m.def.volumen / 8e8 + 0.15);
  const n = poisson(rnd, lambda);
  const sesgo = m.precio > antes ? 0.68 : m.precio < antes ? 0.32 : 0.5;
  for (let k = 0; k < n; k++) operacionMercado(mundo, m, t - Math.floor(rnd() * PASO_MS), rnd() < sesgo ? "compra" : "venta");
  // La vela en curso de cada intervalo que se esta mirando.
  for (const [intervalo, velas] of m.velas) actualizarVela(m, intervalo, velas, t);
}

function avanzar(m: MundoVivo, ahora = Date.now()): void {
  const pasos = Math.floor((ahora - m.t) / PASO_MS);
  if (pasos <= 0) return;
  // Tras dormir la pestana no se simulan horas: como mucho 10 s de golpe.
  const hechos = Math.min(pasos, 40);
  for (let k = hechos; k >= 1; k--) {
    const t = ahora - (k - 1) * PASO_MS;
    if (m.conectado) {
      for (const mon of m.monedas.values()) moverMoneda(m, mon, t);
      ejecutarLimites(m, t);
      botsEnVivo(m, t);
    }
  }
  m.t += pasos * PASO_MS;
  if (m.conectado && ahora - m.ultimaCurva >= 15_000) {
    m.ultimaCurva = ahora;
    for (const b of m.bots) anotarCurva(m, b, ahora);
  }
}

// -- Velas ----------------------------------------------------------------------------------------

function velaVacia(m: EstadoMoneda, intervalo: string, inicio: number, precio: number): S["VelaVivo"] {
  return { coin: m.def.coin, intervalo, inicio: iso(inicio), apertura: precio, maximo: precio, minimo: precio, cierre: precio, volumen: 0, cerrada: false };
}

function actualizarVela(m: EstadoMoneda, intervalo: string, velas: S["VelaVivo"][], t: number): void {
  const ms = msIntervalo(intervalo);
  const p = redondearPrecio(m.precio, m.paso, m.decPrecio);
  let ultima = velas[velas.length - 1];
  if (!ultima) return;
  const fin = Date.parse(ultima.inicio) + ms;
  if (t >= fin) {
    ultima.cerrada = true;
    ultima = velaVacia(m, intervalo, Math.floor(t / ms) * ms, ultima.cierre);
    velas.push(ultima);
    if (velas.length > 1200) velas.splice(0, velas.length - 1000);
  }
  ultima.cierre = p;
  if (p > ultima.maximo) ultima.maximo = p;
  if (p < ultima.minimo) ultima.minimo = p;
}

/** El historico de velas de una moneda: inventado hacia atras desde el precio de ahora. */
function velasDe(mundo: MundoVivo, m: EstadoMoneda, intervalo: string): S["VelaVivo"][] {
  const hechas = m.velas.get(intervalo);
  if (hechas) return hechas;
  const ms = msIntervalo(intervalo);
  const rnd = mulberry32(semilla(`${m.def.coin}:${intervalo}:${mundo.escenario}`));
  const n = 600;
  const sigma = m.def.vol * Math.sqrt(ms / DIA_MS);
  const cierres: number[] = new Array<number>(n);
  cierres[n - 1] = m.precio;
  // Una tendencia suave que acaba en la variacion de 24 h de la moneda (o algo parecido).
  const deriva = ((m.def.var24 / 100) * ms) / DIA_MS / 3;
  for (let i = n - 2; i >= 0; i--) cierres[i] = (cierres[i + 1] ?? m.precio) / Math.exp(sigma * normal(rnd) + deriva);
  const ahora = Math.floor(mundo.t / ms) * ms;
  const velas: S["VelaVivo"][] = [];
  const volBase = (m.def.volumen * ms) / DIA_MS / m.precio;
  for (let i = 0; i < n; i++) {
    const c = redondearPrecio(cierres[i] ?? m.precio, m.paso, m.decPrecio);
    const o = redondearPrecio(i === 0 ? c * Math.exp(sigma * normal(rnd) * 0.5) : (cierres[i - 1] ?? c), m.paso, m.decPrecio);
    const alto = redondearPrecio(Math.max(o, c) * Math.exp(Math.abs(normal(rnd)) * sigma * 0.45), m.paso, m.decPrecio);
    const bajo = redondearPrecio(Math.min(o, c) / Math.exp(Math.abs(normal(rnd)) * sigma * 0.45), m.paso, m.decPrecio);
    const ultima = i === n - 1;
    velas.push({
      coin: m.def.coin,
      intervalo,
      inicio: iso(ahora - (n - 1 - i) * ms),
      apertura: o,
      maximo: Math.max(alto, o, c),
      minimo: Math.min(bajo, o, c),
      cierre: c,
      volumen: Number((volBase * Math.exp(normal(rnd) * 0.5) * (ultima ? (mundo.t - ahora) / ms : 1)).toFixed(m.def.dec)),
      cerrada: !ultima,
    });
  }
  m.velas.set(intervalo, velas);
  return velas;
}

// -- Rutas de mercado -----------------------------------------------------------------------------

function estadoVivo(m: MundoVivo): S["EstadoVivo"] {
  if (!m.conectado) {
    return {
      conectado: false,
      fuente: "Hyperliquid",
      desde: null,
      aviso: `No llegan datos de Hyperliquid desde las ${horaCorta(m.desde)}. El panel reintenta solo; mientras, los precios son los de esa hora.`,
    };
  }
  return { conectado: true, fuente: "Hyperliquid", desde: iso(m.desde), aviso: null };
}

const HORA = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });
const DIA_HORA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
function horaCorta(ms: number): string {
  return HORA.format(new Date(ms));
}

function at(m: MundoVivo): string {
  return iso(m.conectado ? m.t : m.desde);
}

function monedas(m: MundoVivo): S["Monedas"] {
  return {
    estado: estadoVivo(m),
    at: at(m),
    monedas: [...m.monedas.values()].map(
      (x): S["MonedaVivo"] => ({
        coin: x.def.coin,
        nombre: x.def.nombre,
        precio: redondearPrecio(x.precio, x.paso, x.decPrecio),
        var_24h: Math.round((x.precio / x.hace24h - 1) * 10000) / 100,
        volumen_24h: Math.round(x.volumen24h),
        decimales_cantidad: x.def.dec,
      }),
    ),
  };
}

function libro(m: MundoVivo, x: EstadoMoneda): S["LibroVivo"] {
  const bid = mejorCompra(x);
  const ask = mejorVenta(x);
  const compras: S["NivelLibro"][] = [];
  const ventas: S["NivelLibro"][] = [];
  for (let i = 0; i < NIVELES; i++) {
    compras.push({ precio: redondearPrecio(bid - i * x.separacion, x.paso, x.decPrecio), cantidad: x.compras[i] ?? 0, ordenes: x.ordenesC[i] ?? 1 });
    ventas.push({ precio: redondearPrecio(ask + i * x.separacion, x.paso, x.decPrecio), cantidad: x.ventas[i] ?? 0, ordenes: x.ordenesV[i] ?? 1 });
  }
  return { coin: x.def.coin, at: at(m), compras, ventas, diferencial: Number((ask - bid).toFixed(x.decPrecio)) };
}

function operaciones(x: EstadoMoneda, limite = 50): S["Operaciones"] {
  return { coin: x.def.coin, operaciones: x.operaciones.slice(0, limite).map((o) => o.op) };
}

// -- Cuenta de practica ---------------------------------------------------------------------------

function cuentaNueva(inicial: number): CuentaMock {
  return { inicial, saldo: inicial, posiciones: new Map(), ordenes: [], historial: [] };
}

const usd = (v: number): string => v.toFixed(2);
const usdLargo = (v: number): string => v.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
function cant(v: number, dec: number): string {
  return v.toFixed(dec);
}

function cuentaEjemplo(monedas: Map<string, EstadoMoneda>, ahora: number): CuentaMock {
  const c = cuentaNueva(10_000);
  const compra = (coin: string, cantidad: number, precio: number, haceMin: number, tipo: S["EjecucionPractica"]["tipo"] = "mercado"): void => {
    const def = monedas.get(coin)?.def;
    if (!def) return;
    const importe = cantidad * precio;
    const comision = importe * (tipo === "mercado" ? COMISION_TOMADOR : COMISION_CREADOR);
    c.saldo -= importe + comision;
    const p = c.posiciones.get(coin) ?? { cantidad: 0, coste: 0 };
    p.cantidad += cantidad;
    p.coste += importe + comision;
    c.posiciones.set(coin, p);
    c.historial.unshift(ejecucion(`e-${c.historial.length + 1}`, def, "compra", tipo, cantidad, precio, comision, ahora - haceMin * 60_000));
  };
  const venta = (coin: string, cantidad: number, precio: number, haceMin: number): void => {
    const def = monedas.get(coin)?.def;
    const p = c.posiciones.get(coin);
    if (!def || !p) return;
    const importe = cantidad * precio;
    const comision = importe * COMISION_TOMADOR;
    c.saldo += importe - comision;
    p.coste *= (p.cantidad - cantidad) / p.cantidad;
    p.cantidad -= cantidad;
    c.historial.unshift(ejecucion(`e-${c.historial.length + 1}`, def, "venta", "mercado", cantidad, precio, comision, ahora - haceMin * 60_000));
  };
  compra("BTC", 0.0296, 66_812, 2 * 24 * 60 + 35);
  compra("ETH", 0.8, 2_412.6, 26 * 60 + 12);
  compra("SOL", 6.5, 155.31, 9 * 60 + 47, "limite");
  venta("BTC", 0.0148, 67_102, 3 * 60 + 5);
  compra("HYPE", 12, 36.948, 48);
  c.ordenes.push({ id: "o-1", coin: "BTC", lado: "compra", cantidad: 0.015, precio: 65_500, apartado: 0.015 * 65_500 * (1 + COMISION_CREADOR), creada: ahora - 95 * 60_000 });
  c.ordenes.push({ id: "o-2", coin: "ETH", lado: "venta", cantidad: 0.3, precio: 2_600, apartado: 0, creada: ahora - 40 * 60_000 });
  for (const o of c.ordenes) c.saldo -= o.apartado;
  return c;
}

function ejecucion(
  id: string,
  def: DefMoneda,
  lado: "compra" | "venta",
  tipo: S["EjecucionPractica"]["tipo"],
  cantidad: number,
  precio: number,
  comision: number,
  t: number,
): S["EjecucionPractica"] {
  const dp = decimalesPrecio(precio, def.dec);
  return {
    id,
    coin: def.coin,
    nombre: def.nombre,
    lado,
    tipo,
    cantidad: cant(cantidad, def.dec),
    precio: precio.toFixed(dp + 2),
    importe: usdLargo(cantidad * precio),
    comision: usdLargo(comision),
    at: iso(t),
  };
}

function posicionPractica(m: MundoVivo, coin: string, p: PosMock): S["PosicionPractica"] {
  const x = m.monedas.get(coin);
  const dec = x?.def.dec ?? 4;
  const precio = x ? redondearPrecio(x.precio, x.paso, x.decPrecio) : null;
  const valor = precio === null ? null : p.cantidad * precio;
  const dp = x?.decPrecio ?? 2;
  return {
    coin,
    nombre: x?.def.nombre ?? coin,
    cantidad: cant(p.cantidad, dec),
    precio_medio: (p.coste / p.cantidad).toFixed(dp + 2),
    precio: precio === null ? null : precio.toFixed(dp),
    valor: valor === null ? null : usd(valor),
    ganancia: valor === null ? null : usd(valor - p.coste),
    ganancia_pct: valor === null ? null : valor / p.coste - 1,
  };
}

function ordenPractica(m: MundoVivo, o: OrdenMock): S["OrdenPractica"] {
  const x = m.monedas.get(o.coin);
  return {
    id: o.id,
    coin: o.coin,
    nombre: x?.def.nombre ?? o.coin,
    lado: o.lado,
    cantidad: cant(o.cantidad, x?.def.dec ?? 4),
    precio_limite: o.precio.toFixed(x?.decPrecio ?? 2),
    creada: iso(o.creada),
  };
}

function cuenta(m: MundoVivo): S["CuentaPractica"] {
  const c = m.cuenta;
  const posiciones = [...c.posiciones.entries()].filter(([, p]) => p.cantidad > 0).map(([coin, p]) => posicionPractica(m, coin, p));
  const reservado = c.ordenes.reduce((s, o) => s + o.apartado, 0);
  const enPosiciones = posiciones.reduce((s, p) => s + Number(p.valor ?? 0), 0);
  const total = c.saldo + reservado + enPosiciones;
  return {
    inicial: usd(c.inicial),
    saldo: usd(c.saldo),
    reservado: usd(reservado),
    valor_total: usd(total),
    ganancia: usd(total - c.inicial),
    ganancia_pct: total / c.inicial - 1,
    posiciones,
    ordenes: c.ordenes.map((o) => ordenPractica(m, o)),
    historial: c.historial.slice(0, 100),
    at: at(m),
  };
}

function disponibleVenta(c: CuentaMock, coin: string): number {
  const tiene = c.posiciones.get(coin)?.cantidad ?? 0;
  const enOrdenes = c.ordenes.filter((o) => o.coin === coin && o.lado === "venta").reduce((s, o) => s + o.cantidad, 0);
  return tiene - enOrdenes;
}

interface Llenado {
  cantidad: number;
  importe: number;
  niveles: number;
}

/** Recorre el libro como invest_ll/vivo/ejecucion.py. `null` si el libro visible no da. */
function recorrer(lib: S["LibroVivo"], lado: "compra" | "venta", pedido: { cantidad: number } | { importe: number }, dec: number): Llenado | null {
  const niveles = lado === "compra" ? lib.ventas : lib.compras;
  let llevada = 0;
  let gastado = 0;
  let usados = 0;
  for (const n of niveles) {
    usados += 1;
    const toma = "cantidad" in pedido ? Math.min(n.cantidad, pedido.cantidad - llevada) : Math.min(n.cantidad, (pedido.importe - gastado) / n.precio);
    llevada += toma;
    gastado += toma * n.precio;
    const resto = "cantidad" in pedido ? pedido.cantidad - llevada : pedido.importe - gastado;
    if (resto <= 1e-9 * ("cantidad" in pedido ? pedido.cantidad : pedido.importe)) {
      // La cantidad se queda en los decimales que admite la moneda (hacia abajo).
      const cantidad = truncar(llevada, dec);
      return { cantidad, importe: gastado * (cantidad / llevada), niveles: usados };
    }
  }
  return null;
}

function nuevaOrden(m: MundoVivo, o: Objeto): Response {
  const coin = texto(o, "coin") ?? "";
  const x = m.monedas.get(coin);
  if (!x) return fallo(422, `No hay ninguna moneda «${coin}» en Hyperliquid.`);
  if (!m.conectado) return fallo(409, `Ahora no llegan precios de Hyperliquid: no se puede operar con ${x.def.nombre} hasta que vuelvan.`);
  const lado = texto(o, "lado");
  const tipo = texto(o, "tipo");
  if (lado !== "compra" && lado !== "venta") return fallo(422, "Di si quieres comprar o vender.");
  if (tipo !== "mercado" && tipo !== "limite") return fallo(422, "Di si la orden es a mercado o con límite.");
  const cantidadPedida = numero(o, "cantidad");
  const importePedido = numero(o, "importe");
  const limite = numero(o, "precio_limite");
  const c = m.cuenta;
  const nombre = x.def.nombre;
  const dec = x.def.dec;
  const ahora = m.t;

  if (tipo === "mercado") {
    if ((cantidadPedida === null) === (importePedido === null)) return fallo(422, "Di la cantidad en la moneda o el importe en USDC, no las dos.");
    if ((cantidadPedida ?? 1) <= 0 || (importePedido ?? 1) <= 0) return fallo(422, "La orden tiene que ser mayor que cero.");
    const lib = libro(m, x);
    const pedido: { cantidad: number } | { importe: number } =
      cantidadPedida !== null ? { cantidad: truncar(cantidadPedida, dec) } : { importe: importePedido ?? 0 };
    if ("cantidad" in pedido && pedido.cantidad <= 0) return fallo(422, `La cantidad es demasiado pequeña: ${nombre} admite como mucho ${dec} decimales.`);
    const ll = recorrer(lib, lado, pedido, dec);
    if (!ll) {
      const hay = (lado === "compra" ? lib.ventas : lib.compras).reduce((s, n) => s + n.cantidad, 0);
      return fallo(422, `El libro de ${coin} solo tiene ${hay.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${lado === "compra" ? "a la venta" : "pidiendo comprar"} en sus ${NIVELES} niveles visibles: prueba con una orden más pequeña.`);
    }
    if (ll.cantidad <= 0) return fallo(422, `La cantidad es demasiado pequeña: ${nombre} admite como mucho ${dec} decimales.`);
    const comision = ll.importe * COMISION_TOMADOR;
    const precioMedio = ll.importe / ll.cantidad;
    if (lado === "compra") {
      if (ll.importe + comision > c.saldo + 1e-9) {
        return fallo(422, `No tienes saldo bastante: la compra cuesta unos ${eur(ll.importe + comision)} USDC con la comisión y tienes ${eur(c.saldo)} USDC libres.`);
      }
      c.saldo -= ll.importe + comision;
      const p = c.posiciones.get(coin) ?? { cantidad: 0, coste: 0 };
      p.cantidad = Number((p.cantidad + ll.cantidad).toFixed(dec));
      p.coste += ll.importe + comision;
      c.posiciones.set(coin, p);
    } else {
      const libre = disponibleVenta(c, coin);
      if (ll.cantidad > libre + 1e-12) {
        return fallo(422, libre > 0 ? `Solo tienes ${libre.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${coin} libres para vender (lo demás está en órdenes con límite).` : `No tienes ${nombre} que vender.`);
      }
      const p = c.posiciones.get(coin);
      if (!p) return fallo(422, `No tienes ${nombre} que vender.`);
      c.saldo += ll.importe - comision;
      p.coste *= (p.cantidad - ll.cantidad) / p.cantidad;
      p.cantidad = Number((p.cantidad - ll.cantidad).toFixed(dec));
      if (p.cantidad <= 0) c.posiciones.delete(coin);
    }
    const ej = ejecucion(`e-${m.siguiente++}`, x.def, lado, "mercado", ll.cantidad, precioMedio, comision, ahora);
    c.historial.unshift(ej);
    const verbo = lado === "compra" ? "Compraste" : "Vendiste";
    const dinero = lado === "compra" ? `pagaste ${eur(ll.importe)} USDC` : `cobraste ${eur(ll.importe)} USDC`;
    const resumen = `${verbo} ${ll.cantidad.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${nombre} a ${precioMedio.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: x.decPrecio })} USDC de media: ${dinero} y ${eur(comision)} USDC de comisión${ll.niveles > 1 ? ` (se comió ${ll.niveles} niveles del libro)` : ""}.`;
    return json({ resumen, ejecucion: ej, orden: null, cuenta: cuenta(m) } satisfies S["ResultadoPractica"]);
  }

  // Con limite
  if (importePedido !== null) return fallo(422, "Con límite, di la cantidad en la moneda (el importe en USDC solo vale a mercado).");
  if (cantidadPedida === null || cantidadPedida <= 0) return fallo(422, "Di cuánto quieres comprar o vender.");
  if (limite === null || limite <= 0) return fallo(422, "Di el precio límite.");
  const cantidad = truncar(cantidadPedida, dec);
  if (cantidad <= 0) return fallo(422, `La cantidad es demasiado pequeña: ${nombre} admite como mucho ${dec} decimales.`);
  const precio = redondearPrecio(limite, x.paso, x.decPrecio);
  const importe = cantidad * precio;
  let apartado = 0;
  if (lado === "compra") {
    apartado = importe * (1 + COMISION_CREADOR);
    if (apartado > c.saldo + 1e-9) return fallo(422, `No tienes saldo bastante: la orden aparta ${eur(apartado)} USDC y tienes ${eur(c.saldo)} USDC libres.`);
    c.saldo -= apartado;
  } else if (cantidad > disponibleVenta(c, coin) + 1e-12) {
    const libre = disponibleVenta(c, coin);
    return fallo(422, libre > 0 ? `Solo tienes ${libre.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${coin} libres para vender.` : `No tienes ${nombre} que vender.`);
  }
  const orden: OrdenMock = { id: `o-${m.siguiente++}`, coin, lado, cantidad, precio, apartado, creada: ahora };
  c.ordenes.unshift(orden);
  const resumen =
    lado === "compra"
      ? `Orden con límite: comprar ${cantidad.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${nombre} a ${precio.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: x.decPrecio })} USDC o menos. Se apartan ${eur(apartado)} USDC de tu saldo hasta que se ejecute o la canceles.`
      : `Orden con límite: vender ${cantidad.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${nombre} a ${precio.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: x.decPrecio })} USDC o más. Se ejecutará cuando alguien pague ese precio.`;
  return json({ resumen, ejecucion: null, orden: ordenPractica(m, orden), cuenta: cuenta(m) } satisfies S["ResultadoPractica"]);
}

function ejecutarLimites(m: MundoVivo, t: number): void {
  const c = m.cuenta;
  for (const o of [...c.ordenes]) {
    const x = m.monedas.get(o.coin);
    if (!x) continue;
    const cruza = o.lado === "compra" ? mejorVenta(x) <= o.precio : mejorCompra(x) >= o.precio;
    if (!cruza) continue;
    const importe = o.cantidad * o.precio;
    const comision = importe * COMISION_CREADOR;
    if (o.lado === "compra") {
      const p = c.posiciones.get(o.coin) ?? { cantidad: 0, coste: 0 };
      p.cantidad = Number((p.cantidad + o.cantidad).toFixed(x.def.dec));
      p.coste += importe + comision;
      c.posiciones.set(o.coin, p);
      c.saldo += o.apartado - importe - comision;
    } else {
      const p = c.posiciones.get(o.coin);
      if (!p) continue;
      p.coste *= (p.cantidad - o.cantidad) / p.cantidad;
      p.cantidad = Number((p.cantidad - o.cantidad).toFixed(x.def.dec));
      if (p.cantidad <= 0) c.posiciones.delete(o.coin);
      c.saldo += importe - comision;
    }
    c.ordenes = c.ordenes.filter((y) => y.id !== o.id);
    c.historial.unshift(ejecucion(`e-${m.siguiente++}`, x.def, o.lado, "limite", o.cantidad, o.precio, comision, t));
  }
}

// -- Plantillas de bots ---------------------------------------------------------------------------

const PLANTILLAS: S["PlantillaBot"][] = [
  {
    clave: "btc-freno",
    nombre: "Bitcoin con freno",
    frase: "Dentro de Bitcoin mientras sube; fuera, en USDC, cuando deja de subir.",
    como_funciona: [
      "Una vez al día mira si Bitcoin vale más que hace 30 días.",
      "Si sube, tiene todo su capital en Bitcoin; si no, lo pasa a USDC y espera.",
      "Entre medias no hace nada: unas pocas operaciones al mes.",
    ],
    avisos: [
      "Pasa casi la mitad del tiempo fuera, en USDC: habrá épocas en que lo haga peor que tener Bitcoin quieto.",
      "En una caída rápida sale tarde: el freno mira 30 días, no minutos.",
    ],
    evidencia: { tipo: "prueba_real", texto: "Probada sobre el pasado; en prueba real desde el 15 oct 2026." },
    riesgo: 4,
    riesgo_texto: "Movida",
    operaciones_esperadas: "Unas pocas al mes",
    monedas: "una",
    monedas_sugeridas: ["BTC"],
    parametros: [
      {
        clave: "dias",
        nombre: "Días que mira hacia atrás",
        explicacion: "Para decidir si Bitcoin sube, compara su precio de hoy con el de hace estos días. Con menos días reacciona antes, pero entra y sale más veces y paga más comisiones.",
        tipo: "entero",
        defecto: "30",
        minimo: "7",
        maximo: "120",
        opciones: null,
      },
    ],
  },
  {
    clave: "tendencia",
    nombre: "Tendencia rápida",
    frase: "Compra cuando la media corta cruza por encima de la larga y vende cuando cruza por debajo.",
    como_funciona: [
      "En cada vela cerrada calcula dos medias del precio: una corta (20 velas) y una larga (50).",
      "Si la corta pasa por encima de la larga, compra con todo su capital.",
      "Si pasa por debajo, lo vende todo y espera en USDC.",
    ],
    avisos: [
      "No tiene ninguna prueba: es un experimento.",
      "Cuando el precio va de lado, entra y sale muchas veces y pierde en comisiones.",
    ],
    evidencia: { tipo: "ninguna", texto: "Ninguna prueba: es un experimento." },
    riesgo: 4,
    riesgo_texto: "Movida",
    operaciones_esperadas: "Varias a la semana",
    monedas: "una",
    monedas_sugeridas: ["ETH", "BTC", "SOL"],
    parametros: [
      {
        clave: "corta",
        nombre: "Media corta",
        explicacion: "Cuántas velas promedia la media rápida. Más pequeña: reacciona antes y se equivoca más.",
        tipo: "entero",
        defecto: "20",
        minimo: "5",
        maximo: "100",
        opciones: null,
      },
      {
        clave: "larga",
        nombre: "Media larga",
        explicacion: "Cuántas velas promedia la media lenta. Tiene que ser mayor que la corta.",
        tipo: "entero",
        defecto: "50",
        minimo: "20",
        maximo: "300",
        opciones: null,
      },
      {
        clave: "intervalo",
        nombre: "Velas de",
        explicacion: "Cada cuánto cierra una vela y el bot decide. Con velas cortas hace más operaciones (y paga más comisiones).",
        tipo: "intervalo",
        defecto: "1h",
        minimo: null,
        maximo: null,
        opciones: ["15m", "1h", "4h"],
      },
    ],
  },
  {
    clave: "rejilla",
    nombre: "Rejilla",
    frase: "Reparte compras escalonadas en un rango y vende cada escalón al subir.",
    como_funciona: [
      "Divide el rango de precios en escalones iguales.",
      "Cada vez que el precio baja un escalón, compra un trozo; cada vez que sube uno, vende lo comprado en el de abajo.",
      "Gana un poco en cada ida y vuelta.",
    ],
    avisos: [
      "Si el precio sale del rango por abajo, se queda con todo comprado y bajando.",
      "Si sale por arriba, se queda en USDC y deja de ganar.",
    ],
    evidencia: { tipo: "ninguna", texto: "Ninguna prueba: gana si el precio oscila dentro del rango, pierde si sale por abajo." },
    riesgo: 4,
    riesgo_texto: "Movida",
    operaciones_esperadas: "Decenas al día",
    monedas: "una",
    monedas_sugeridas: ["SOL", "ETH", "BTC"],
    parametros: [
      {
        clave: "abajo",
        nombre: "Rango por abajo (%)",
        explicacion: "Hasta cuánto por debajo del precio de ahora llega la rejilla. Más amplio: aguanta caídas mayores, pero cada escalón es más grande y gana menos veces.",
        tipo: "decimal",
        defecto: "8",
        minimo: "1",
        maximo: "50",
        opciones: null,
      },
      {
        clave: "arriba",
        nombre: "Rango por arriba (%)",
        explicacion: "Hasta cuánto por encima del precio de ahora llega la rejilla. Por encima de eso ya lo ha vendido todo.",
        tipo: "decimal",
        defecto: "8",
        minimo: "1",
        maximo: "50",
        opciones: null,
      },
      {
        clave: "escalones",
        nombre: "Escalones",
        explicacion: "En cuántos trozos reparte el capital. Más escalones: operaciones más pequeñas y más frecuentes.",
        tipo: "entero",
        defecto: "10",
        minimo: "3",
        maximo: "50",
        opciones: null,
      },
    ],
  },
  {
    clave: "periodica",
    nombre: "Compra periódica",
    frase: "Compra una cantidad fija cada cierto tiempo, sin elegir el momento.",
    como_funciona: [
      "Cada cierto número de horas compra la misma cantidad en USDC, repartida entre sus monedas.",
      "No vende nunca: va acumulando.",
      "Cuando se le acaba el capital, se para y lo dice.",
    ],
    avisos: ["Si el precio baja durante meses, sigue comprando y lo que tienes baja con él.", "Al final lo tiene todo en cripto, sin freno."],
    evidencia: { tipo: "pasado", texto: "Es la de «aportar y mantener», sin elegir momento: probada sobre el pasado." },
    riesgo: 5,
    riesgo_texto: "Muy movida",
    operaciones_esperadas: "Una cada pocas horas",
    monedas: "varias",
    monedas_sugeridas: ["BTC", "ETH"],
    parametros: [
      {
        clave: "cada_horas",
        nombre: "Cada cuántas horas",
        explicacion: "Cada cuánto compra. Más a menudo: compras más pequeñas y un precio medio más suave.",
        tipo: "entero",
        defecto: "24",
        minimo: "1",
        maximo: "168",
        opciones: null,
      },
      {
        clave: "importe",
        nombre: "USDC por compra",
        explicacion: "Cuánto compra cada vez, repartido a partes iguales entre sus monedas.",
        tipo: "decimal",
        defecto: "50",
        minimo: "5",
        maximo: "10000",
        opciones: null,
      },
    ],
  },
];

function plantilla(clave: string): S["PlantillaBot"] | undefined {
  return PLANTILLAS.find((p) => p.clave === clave);
}

// -- Bots: historia inventada pero coherente ------------------------------------------------------

/** Puente browniano en logaritmos: n puntos de `desde` a `hasta`. */
function puente(rnd: () => number, n: number, desde: number, hasta: number, sigma: number): number[] {
  const w: number[] = [0];
  for (let i = 1; i < n; i++) w.push((w[i - 1] ?? 0) + sigma * normal(rnd));
  const total = w[n - 1] ?? 0;
  const l0 = Math.log(desde);
  const l1 = Math.log(hasta);
  return w.map((x, i) => Math.exp(l0 + x - (i / (n - 1)) * total + (i / (n - 1)) * (l1 - l0)));
}

interface PlanBot {
  id: string;
  nombre: string;
  plantilla: string;
  monedas: string[];
  estado: S["ResumenBot"]["estado"];
  dias: number;
  capital: number;
  /** Lo que ha hecho cada moneda desde que arranco (fraccion). */
  movimiento: number[];
  parametros: Record<string, string>;
  motivo_error?: string;
  aviso?: string;
  hueco?: [number, number];
}

/** El porque de cada operacion, en llano (`OperacionBot.motivo`). */
function motivo(clave: string, lado: "compra" | "venta", nombre: string, parametros: Record<string, string>, extra = ""): string {
  switch (clave) {
    case "btc-freno":
      return lado === "compra"
        ? `${nombre} vale más que hace ${parametros.dias ?? "30"} días: el bot entra con todo su capital.`
        : `en ${parametros.dias ?? "30"} días ${nombre} ya no sube: el bot pasa a USDC hasta que vuelva a subir.`;
    case "tendencia":
      return lado === "compra"
        ? `la media de ${parametros.corta ?? "20"} velas cruzó por encima de la de ${parametros.larga ?? "50"}.`
        : `la media de ${parametros.corta ?? "20"} velas cruzó por debajo de la de ${parametros.larga ?? "50"}.`;
    case "rejilla":
      return lado === "compra" ? `el precio bajó al escalón ${extra}: compra un trozo.` : `el precio subió al escalón ${extra}: vende el trozo comprado en el de abajo.`;
    default:
      return `toca la compra de cada ${parametros.cada_horas ?? "24"} horas.`;
  }
}

function precioTexto(m: MundoVivo, coin: string, p: number): string {
  const x = m.monedas.get(coin);
  return p.toLocaleString("es-ES", { useGrouping: "always", minimumFractionDigits: x?.decPrecio ?? 2, maximumFractionDigits: x?.decPrecio ?? 2 });
}

function crearBot(m: MundoVivo, plan: PlanBot, ahora: number): BotMock {
  const rnd = mulberry32(semilla(`bot:${plan.id}`));
  const n = 100;
  const desde = ahora - plan.dias * DIA_MS;
  const tiempos = Array.from({ length: n }, (_, i) => desde + (i / (n - 1)) * (ahora - desde));
  const caminos = plan.monedas.map((coin, i) => {
    const x = m.monedas.get(coin);
    const ahoraP = x?.precio ?? 1;
    const vol = (x?.def.vol ?? 0.05) * Math.sqrt(plan.dias / (n - 1));
    return puente(rnd, n, ahoraP / (1 + (plan.movimiento[i] ?? 0)), ahoraP, vol);
  });
  const indice = tiempos.map((_, k) => caminos.reduce((s, c) => s + (c[k] ?? 0) / (c[0] ?? 1), 0) / caminos.length);

  // Cuanto tiene invertido en cada momento (0-1), segun la plantilla.
  const exp: number[] = [];
  const escalonDe: number[] = [];
  const abajo = Number(plan.parametros.abajo ?? "8") / 100;
  const arriba = Number(plan.parametros.arriba ?? "8") / 100;
  const escalones = Number(plan.parametros.escalones ?? "10");
  for (let k = 0; k < n; k++) {
    const p = indice[k] ?? 1;
    if (plan.plantilla === "btc-freno") exp.push(k / n > 0.36 && k / n < 0.58 ? 0 : 1);
    else if (plan.plantilla === "tendencia") {
      const media = (v: number) => {
        const tramo = indice.slice(Math.max(0, k - v), k + 1);
        return tramo.reduce((s, x) => s + x, 0) / tramo.length;
      };
      exp.push(k < 6 ? 0 : media(4) > media(11) ? 1 : 0);
    } else if (plan.plantilla === "rejilla") {
      const lo = 1 - abajo;
      const hi = 1 + arriba;
      const f = Math.min(1, Math.max(0, (hi - p) / (hi - lo)));
      const e = Math.round(f * escalones) / escalones;
      escalonDe.push(Math.round(f * escalones));
      exp.push(e);
    } else {
      const cada = Number(plan.parametros.cada_horas ?? "24") * 3_600_000;
      const importe = Number(plan.parametros.importe ?? "50");
      const compras = Math.floor(((tiempos[k] ?? 0) - desde) / cada) + 1;
      exp.push(Math.min(1, (compras * importe) / plan.capital));
    }
  }

  const b: BotMock = {
    id: plan.id,
    nombre: plan.nombre,
    plantilla: plan.plantilla,
    monedas: plan.monedas,
    estado: plan.estado,
    motivo_error: plan.motivo_error ?? null,
    desde,
    capital: plan.capital,
    efectivo: plan.capital,
    posiciones: new Map(),
    precioInicio: Object.fromEntries(plan.monedas.map((coin, i) => [coin, caminos[i]?.[0] ?? 1])),
    curva: [],
    curvaMantener: [],
    operaciones: [],
    eventos: [],
    parametros: plan.parametros,
    aviso: plan.aviso ?? null,
    ultimaActividad: null,
    escalon: plan.plantilla === "rejilla" ? (escalonDe[n - 1] ?? 0) * FINO : null,
    proxima: plan.plantilla === "periodica" ? ahora + Number(plan.parametros.cada_horas ?? "24") * 3_600_000 * 0.4 : null,
  };

  // Se recorre la historia: el valor sigue a lo invertido y cada cambio de exposicion es una
  // operacion con su porque. Los pasos dentro del hueco (panel cerrado) no operan.
  let anterior = 0;
  for (let k = 0; k < n; k++) {
    const t = tiempos[k] ?? ahora;
    const enHueco = plan.hueco && k / n >= plan.hueco[0] && k / n <= plan.hueco[1];
    const quiere = exp[k] ?? 0;
    const valorAntes = valorBot(b, (coin) => caminos[plan.monedas.indexOf(coin)]?.[k] ?? 0);
    if (!enHueco && Math.abs(quiere - anterior) > 1e-9 && !(plan.estado === "error" && k > n - 4)) {
      const lado = quiere > anterior ? "compra" : "venta";
      const parte = (Math.abs(quiere - anterior) * valorAntes) / plan.monedas.length;
      for (const [i, coin] of plan.monedas.entries()) {
        const x = m.monedas.get(coin);
        const precio = caminos[i]?.[k] ?? 1;
        const dec = x?.def.dec ?? 4;
        // Al comprar, la comision sale del mismo dinero: si no, "todo el capital" no llega.
        let cantidad = truncar(lado === "compra" ? parte / precio / (1 + COMISION_TOMADOR) : parte / precio, dec);
        const pos = b.posiciones.get(coin) ?? { cantidad: 0, coste: 0 };
        if (lado === "venta") cantidad = Math.min(cantidad, pos.cantidad);
        if (cantidad <= 0) continue;
        const importe = cantidad * precio;
        const comision = importe * COMISION_TOMADOR;
        if (lado === "compra") {
          if (importe + comision > b.efectivo) continue;
          b.efectivo -= importe + comision;
          pos.cantidad = Number((pos.cantidad + cantidad).toFixed(dec));
          pos.coste += importe + comision;
        } else {
          b.efectivo += importe - comision;
          pos.coste *= (pos.cantidad - cantidad) / pos.cantidad;
          pos.cantidad = Number((pos.cantidad - cantidad).toFixed(dec));
        }
        b.posiciones.set(coin, pos);
        const extra = plan.plantilla === "rejilla" ? `${escalones - (escalonDe[k] ?? 0) + 1} de ${escalones} (${precioTexto(m, coin, precio)})` : "";
        b.operaciones.unshift(operacionBot(m, coin, lado, cantidad, precio, comision, t, motivo(plan.plantilla, lado, x?.def.nombre ?? coin, plan.parametros, extra)));
        b.ultimaActividad = t;
      }
      anterior = quiere;
    }
    b.curva.push({ t, v: valorBot(b, (coin) => caminos[plan.monedas.indexOf(coin)]?.[k] ?? 0) });
    b.curvaMantener.push({ t, v: plan.capital * (indice[k] ?? 1) });
  }

  b.eventos.push({ at: iso(desde), tipo: "arranque", texto: `Desplegado con ${eur(plan.capital)} USDC ficticios.` });
  if (plan.hueco) {
    const a = desde + plan.hueco[0] * (ahora - desde);
    const z = desde + plan.hueco[1] * (ahora - desde);
    b.eventos.unshift({ at: iso(z), tipo: "hueco", texto: `Panel cerrado de ${DIA_HORA.format(new Date(a))} a ${HORA.format(new Date(z))}: no pudo operar.` });
  }
  if (plan.dias > 2) b.eventos.unshift({ at: iso(ahora - plan.dias * 0.3 * DIA_MS), tipo: "info", texto: "Hyperliquid cortó la conexión 40 s; el panel se reconectó solo y el bot siguió." });
  if (plan.estado === "parado") b.eventos.unshift({ at: iso(ahora - 2 * 3_600_000), tipo: "parada", texto: "Parado a mano. Conserva lo que tiene, que sigue valorándose a precios de ahora." });
  if (plan.estado === "error" && plan.motivo_error) b.eventos.unshift({ at: iso(ahora - 50 * 60_000), tipo: "error", texto: plan.motivo_error });
  return b;
}

function operacionBot(m: MundoVivo, coin: string, lado: "compra" | "venta", cantidad: number, precio: number, comision: number, t: number, porque: string): S["OperacionBot"] {
  const x = m.monedas.get(coin);
  const dec = x?.def.dec ?? 4;
  const verbo = lado === "compra" ? "Compré" : "Vendí";
  return {
    at: iso(t),
    coin,
    nombre: x?.def.nombre ?? coin,
    lado,
    cantidad: cant(cantidad, dec),
    precio: precio.toFixed(x?.decPrecio ?? 2),
    importe: usdLargo(cantidad * precio),
    comision: usdLargo(comision),
    motivo: `${verbo} ${cantidad.toLocaleString("es-ES", { useGrouping: "always", maximumFractionDigits: dec })} ${coin} a ${precioTexto(m, coin, precio)}: ${porque}`,
  };
}

function valorBot(b: BotMock, precioDe: (coin: string) => number): number {
  let v = b.efectivo;
  for (const [coin, p] of b.posiciones) v += p.cantidad * precioDe(coin);
  return v;
}

function precioVivo(m: MundoVivo, coin: string): number {
  return m.monedas.get(coin)?.precio ?? 0;
}

function botsEjemplo(m: MundoVivo, ahora: number): BotMock[] {
  const planes: PlanBot[] = [
    { id: "freno-btc", nombre: "Bitcoin con freno", plantilla: "btc-freno", monedas: ["BTC"], estado: "en_marcha", dias: 12.4, capital: 5000, movimiento: [0.061], parametros: { dias: "30" } },
    {
      id: "tendencia-eth",
      nombre: "Tendencia ETH 1 h",
      plantilla: "tendencia",
      monedas: ["ETH"],
      estado: "en_marcha",
      dias: 6.3,
      capital: 2000,
      movimiento: [-0.018],
      parametros: { corta: "20", larga: "50", intervalo: "1h" },
      hueco: [0.55, 0.585],
      aviso: "Panel cerrado unas horas el 14 oct: en ese hueco no pudo operar.",
    },
    { id: "rejilla-sol", nombre: "Rejilla SOL ±8 %", plantilla: "rejilla", monedas: ["SOL"], estado: "en_marcha", dias: 3.2, capital: 1500, movimiento: [-0.012], parametros: { abajo: "8", arriba: "8", escalones: "10" } },
    { id: "periodica-btc-eth", nombre: "Compra diaria BTC y ETH", plantilla: "periodica", monedas: ["BTC", "ETH"], estado: "parado", dias: 21, capital: 3000, movimiento: [0.072, 0.031], parametros: { cada_horas: "24", importe: "100" } },
    {
      id: "tendencia-hype",
      nombre: "Tendencia HYPE 15 min",
      plantilla: "tendencia",
      monedas: ["HYPE"],
      estado: "error",
      dias: 1.6,
      capital: 1000,
      movimiento: [0.094],
      parametros: { corta: "20", larga: "50", intervalo: "15m" },
      motivo_error: "El libro de HYPE no tenía bastante para vender 26,4 HYPE a mercado: el bot se ha parado para no inventarse un precio. Revísalo y reanúdalo.",
    },
  ];
  // Los ids nuevos siguen a los del ejemplo.
  m.siguiente = 100;
  return planes.map((p) => crearBot(m, p, ahora));
}

function anotarCurva(m: MundoVivo, b: BotMock, t: number): void {
  b.curva.push({ t, v: valorBot(b, (coin) => precioVivo(m, coin)) });
  b.curvaMantener.push({ t, v: valorMantener(m, b) });
  // Unos 100 puntos: se aclara la parte vieja cuando crece.
  for (const serie of [b.curva, b.curvaMantener]) {
    if (serie.length > 130) {
      const viejos = serie.splice(0, 60);
      serie.unshift(...viejos.filter((_, i) => i % 2 === 0));
    }
  }
}

function valorMantener(m: MundoVivo, b: BotMock): number {
  const n = b.monedas.length || 1;
  return b.monedas.reduce((s, coin) => s + (b.capital / n) * (precioVivo(m, coin) / (b.precioInicio[coin] ?? 1)), 0);
}

/** En vivo, la rejilla de ejemplo opera en escalones 6 veces mas finos: asi se la ve operar. */
const FINO = 6;

/** Lo que hacen los bots en marcha con cada precio: la rejilla opera, la periodica compra. */
function botsEnVivo(m: MundoVivo, t: number): void {
  for (const b of m.bots) {
    if (b.estado !== "en_marcha") continue;
    const coin = b.monedas[0];
    if (!coin) continue;
    const x = m.monedas.get(coin);
    if (!x) continue;
    if (b.plantilla === "rejilla" && b.escalon !== null) {
      const ref = b.precioInicio[coin] ?? x.precio;
      const abajo = Number(b.parametros.abajo ?? "8") / 100;
      const arriba = Number(b.parametros.arriba ?? "8") / 100;
      const escalones = Number(b.parametros.escalones ?? "10");
      const lo = ref * (1 - abajo);
      const hi = ref * (1 + arriba);
      const fino = escalones * FINO;
      const f = Math.min(1, Math.max(0, (hi - x.precio) / (hi - lo)));
      const ahoraEsc = Math.round(f * fino);
      const antes = b.escalon;
      if (ahoraEsc !== antes) {
        const lado = ahoraEsc > antes ? "compra" : "venta";
        const parte = b.capital / fino;
        const precio = lado === "compra" ? mejorVenta(x) : mejorCompra(x);
        const pos = b.posiciones.get(coin) ?? { cantidad: 0, coste: 0 };
        let cantidad = truncar(parte / precio, x.def.dec);
        if (lado === "venta") cantidad = Math.min(cantidad, pos.cantidad);
        if (cantidad > 0 && (lado === "venta" || cantidad * precio * (1 + COMISION_TOMADOR) <= b.efectivo)) {
          const importe = cantidad * precio;
          const comision = importe * COMISION_TOMADOR;
          if (lado === "compra") {
            b.efectivo -= importe + comision;
            pos.cantidad = Number((pos.cantidad + cantidad).toFixed(x.def.dec));
            pos.coste += importe + comision;
          } else {
            b.efectivo += importe - comision;
            pos.coste *= (pos.cantidad - cantidad) / pos.cantidad;
            pos.cantidad = Number((pos.cantidad - cantidad).toFixed(x.def.dec));
          }
          b.posiciones.set(coin, pos);
          const extra = `${fino - ahoraEsc + 1} de ${fino} (${precioTexto(m, coin, precio)})`;
          b.operaciones.unshift(operacionBot(m, coin, lado, cantidad, precio, comision, t, motivo("rejilla", lado, x.def.nombre, b.parametros, extra)));
          b.ultimaActividad = t;
        }
      }
      b.escalon = ahoraEsc;
    }
    if (b.plantilla === "periodica" && b.proxima !== null && t >= b.proxima) {
      const importe = Number(b.parametros.importe ?? "50") / b.monedas.length;
      for (const c of b.monedas) {
        const y = m.monedas.get(c);
        if (!y || b.efectivo < importe) continue;
        const precio = mejorVenta(y);
        const cantidad = truncar(importe / precio, y.def.dec);
        const comision = cantidad * precio * COMISION_TOMADOR;
        b.efectivo -= cantidad * precio + comision;
        const pos = b.posiciones.get(c) ?? { cantidad: 0, coste: 0 };
        pos.cantidad = Number((pos.cantidad + cantidad).toFixed(y.def.dec));
        pos.coste += cantidad * precio + comision;
        b.posiciones.set(c, pos);
        b.operaciones.unshift(operacionBot(m, c, "compra", cantidad, precio, comision, t, motivo("periodica", "compra", y.def.nombre, b.parametros)));
      }
      b.ultimaActividad = t;
      b.proxima = t + Number(b.parametros.cada_horas ?? "24") * 3_600_000;
    }
  }
}

function peorCaida(curva: readonly PuntoMock[]): number | null {
  if (curva.length < 2) return null;
  let max = -Infinity;
  let peor = 0;
  for (const p of curva) {
    max = Math.max(max, p.v);
    peor = Math.min(peor, p.v / max - 1);
  }
  return peor;
}

function valorEn(curva: readonly PuntoMock[], t: number): number | null {
  let anterior: PuntoMock | null = null;
  for (const p of curva) {
    if (p.t >= t) return anterior ? anterior.v : p.v;
    anterior = p;
  }
  return anterior?.v ?? null;
}

function curvaConAhora(curva: readonly PuntoMock[], ahora: PuntoMock): S["PuntoBot"][] {
  const ultimo = curva[curva.length - 1];
  const puntos = ultimo && ahora.t - ultimo.t < 1000 ? curva.slice(0, -1) : curva;
  return [...puntos, ahora].map((p) => ({ at: iso(p.t), valor: Math.round(p.v * 100) / 100 }));
}

function resumenBot(m: MundoVivo, b: BotMock): S["ResumenBot"] {
  const ahora = m.conectado ? m.t : m.desde;
  const valor = valorBot(b, (coin) => precioVivo(m, coin));
  const curva = curvaConAhora(b.curva, { t: ahora, v: valor });
  const hace24 = valorEn(b.curva, ahora - DIA_MS) ?? b.capital;
  const p = plantilla(b.plantilla);
  const avisoDesconexion = m.conectado ? null : "Sin datos de Hyperliquid: el bot no opera hasta que vuelvan.";
  return {
    id: b.id,
    nombre: b.nombre,
    plantilla: b.plantilla,
    nombre_plantilla: p?.nombre ?? b.plantilla,
    monedas: b.monedas,
    estado: b.estado,
    motivo_error: b.motivo_error,
    desde: iso(b.desde),
    dias: Math.round(((ahora - b.desde) / DIA_MS) * 10) / 10,
    capital: usd(b.capital),
    valor: usd(valor),
    ganancia: usd(valor - b.capital),
    ganancia_pct: valor / b.capital - 1,
    ganancia_24h_pct: valor / hace24 - 1,
    mantener_pct: valorMantener(m, b) / b.capital - 1,
    peor_caida: peorCaida([...b.curva, { t: ahora, v: valor }]),
    operaciones: b.operaciones.length,
    evidencia: p?.evidencia ?? { tipo: "ninguna", texto: "Ninguna prueba." },
    riesgo: p?.riesgo ?? 3,
    curva,
    ultima_actividad: b.ultimaActividad === null ? null : iso(b.ultimaActividad),
    aviso: avisoDesconexion ?? b.aviso,
  };
}

function detalleBot(m: MundoVivo, b: BotMock): S["DetalleBot"] {
  const r = resumenBot(m, b);
  const ahora = m.conectado ? m.t : m.desde;
  return {
    ...r,
    parametros: b.parametros,
    efectivo: usd(b.efectivo),
    posiciones: [...b.posiciones.entries()].filter(([, p]) => p.cantidad > 0).map(([coin, p]) => posicionPractica(m, coin, p)),
    lista_operaciones: b.operaciones.slice(0, 200),
    eventos: b.eventos,
    curva_mantener: curvaConAhora(b.curvaMantener, { t: ahora, v: valorMantener(m, b) }),
  };
}

function bots(m: MundoVivo): S["Bots"] {
  const lista = m.bots.map((b) => resumenBot(m, b));
  const capital = m.bots.reduce((s, b) => s + b.capital, 0);
  const valor = m.bots.reduce((s, b) => s + valorBot(b, (coin) => precioVivo(m, coin)), 0);
  return {
    bots: lista,
    capital: usd(capital),
    valor: usd(valor),
    ganancia: usd(valor - capital),
    ganancia_pct: capital > 0 ? valor / capital - 1 : null,
    at: at(m),
    nota: "Dinero ficticio. Los bots solo funcionan mientras el panel está abierto.",
  };
}

function desplegar(m: MundoVivo, o: Objeto): Response {
  const clave = texto(o, "plantilla") ?? "";
  const p = plantilla(clave);
  if (!p) return fallo(422, `No hay ninguna plantilla «${clave}».`);
  const nombre = (texto(o, "nombre") ?? "").trim();
  if (!nombre) return fallo(422, "Ponle un nombre al bot.");
  if (nombre.length > 60) return fallo(422, "El nombre puede tener como mucho 60 letras.");
  const lista = Array.isArray(o.monedas) ? o.monedas.filter((x): x is string => typeof x === "string") : [];
  if (!lista.length) return fallo(422, "Elige al menos una moneda.");
  if (p.monedas === "una" && lista.length > 1) return fallo(422, `«${p.nombre}» opera con una sola moneda.`);
  const rara = lista.find((c) => !m.monedas.has(c));
  if (rara) return fallo(422, `No hay ninguna moneda «${rara}» en Hyperliquid.`);
  const capital = numero(o, "capital");
  if (capital === null || capital <= 0) return fallo(422, "El capital tiene que ser mayor que cero.");
  if (capital < 10) return fallo(422, "Con menos de 10 USDC el bot no llega ni a pagar las comisiones: pon al menos 10.");
  const pedidos = typeof o.parametros === "object" && o.parametros !== null ? (o.parametros as Record<string, unknown>) : {};
  const parametros: Record<string, string> = {};
  for (const def of p.parametros) {
    const bruto = pedidos[def.clave];
    const valor = typeof bruto === "string" && bruto.trim() !== "" ? bruto.trim() : def.defecto;
    if (def.tipo === "entero" || def.tipo === "decimal") {
      const n = Number(valor.replace(",", "."));
      if (!Number.isFinite(n) || (def.tipo === "entero" && !Number.isInteger(n))) return fallo(422, `«${def.nombre}» tiene que ser un número${def.tipo === "entero" ? " entero" : ""}.`);
      if (def.minimo !== null && n < Number(def.minimo)) return fallo(422, `«${def.nombre}» no puede ser menor que ${def.minimo}.`);
      if (def.maximo !== null && n > Number(def.maximo)) return fallo(422, `«${def.nombre}» no puede ser mayor que ${def.maximo}.`);
      parametros[def.clave] = String(n);
    } else {
      if (def.opciones && !def.opciones.includes(valor)) return fallo(422, `«${def.nombre}» tiene que ser una de: ${def.opciones.join(", ")}.`);
      parametros[def.clave] = valor;
    }
  }
  if (clave === "tendencia" && Number(parametros.corta) >= Number(parametros.larga)) return fallo(422, "La media corta tiene que tener menos velas que la larga.");

  const ahora = m.t;
  const b: BotMock = {
    id: `bot-${m.siguiente++}`,
    nombre,
    plantilla: clave,
    monedas: lista,
    estado: "en_marcha",
    motivo_error: null,
    desde: ahora,
    capital,
    efectivo: capital,
    posiciones: new Map(),
    precioInicio: Object.fromEntries(lista.map((c) => [c, precioVivo(m, c)])),
    curva: [{ t: ahora, v: capital }],
    curvaMantener: [{ t: ahora, v: capital }],
    operaciones: [],
    eventos: [{ at: iso(ahora), tipo: "arranque", texto: `Desplegado con ${eur(capital)} USDC ficticios.` }],
    parametros,
    aviso: null,
    ultimaActividad: null,
    escalon: null,
    proxima: clave === "periodica" ? ahora : null,
  };
  // Lo primero que hace cada plantilla al arrancar.
  const primera = b.monedas[0] ?? "BTC";
  const x = m.monedas.get(primera);
  if (x && (clave === "btc-freno" || clave === "rejilla")) {
    const sube = x.precio > x.hace24h;
    const fraccion = clave === "rejilla" ? 0.5 : sube ? 1 : 0;
    if (fraccion > 0) {
      const precio = mejorVenta(x);
      const cantidad = truncar((capital * fraccion) / precio / (1 + COMISION_TOMADOR), x.def.dec);
      const comision = cantidad * precio * COMISION_TOMADOR;
      b.efectivo -= cantidad * precio + comision;
      b.posiciones.set(primera, { cantidad, coste: cantidad * precio + comision });
      const porque =
        clave === "rejilla"
          ? "al arrancar, el precio está en mitad de la rejilla: compra la mitad de los escalones."
          : motivo("btc-freno", "compra", x.def.nombre, parametros);
      b.operaciones.unshift(operacionBot(m, primera, "compra", cantidad, precio, comision, ahora, porque));
      b.ultimaActividad = ahora;
    } else {
      b.eventos.unshift({ at: iso(ahora), tipo: "info", texto: `${x.def.nombre} no sube en ${parametros.dias ?? "30"} días: el bot espera en USDC.` });
    }
    if (clave === "rejilla") b.escalon = Math.round((Number(parametros.escalones) * FINO) / 2);
  }
  if (clave === "tendencia") b.eventos.unshift({ at: iso(ahora), tipo: "info", texto: `Esperando la primera señal: decide en cada vela de ${parametros.intervalo ?? "1h"} cerrada.` });
  m.bots.unshift(b);
  if (clave === "periodica") botsEnVivo(m, ahora);
  return json(detalleBot(m, b) satisfies S["DetalleBot"], 201);
}

// -- Utilidades de respuesta ----------------------------------------------------------------------

type Objeto = Record<string, unknown>;

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

function fallo(status: number, detail: string): Response {
  return json({ detail }, status);
}

async function cuerpo(p: Request): Promise<Objeto> {
  try {
    const v: unknown = await p.json();
    return typeof v === "object" && v !== null ? (v as Objeto) : {};
  } catch {
    return {};
  }
}

function texto(o: Objeto, campo: string): string | null {
  const v = o[campo];
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return null;
}

function numero(o: Objeto, campo: string): number | null {
  const v = o[campo];
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v.replace(",", ".")) : NaN;
  return Number.isFinite(n) ? n : null;
}

function eur(v: number): string {
  return v.toLocaleString("es-ES", { useGrouping: "always", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function esperar(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// -- Enrutador REST -------------------------------------------------------------------------------

/** ¿Es una ruta del panel v3? (las enruta `responderVivo`). */
export function esRutaVivo(ruta: string): boolean {
  return /^\/api\/(vivo|practica|bots)(\/|$)/.test(ruta);
}

export async function responderVivo(peticion: Request, url: URL): Promise<Response> {
  const m = elMundo();
  avanzar(m);
  await esperar(60 + Math.random() * 120);
  const ruta = url.pathname;
  const metodo = peticion.method.toUpperCase();
  const coin = url.searchParams.get("coin") ?? "";

  switch (`${metodo} ${ruta}`) {
    case "GET /api/vivo/estado":
      return json(estadoVivo(m) satisfies S["EstadoVivo"]);
    case "GET /api/vivo/monedas":
      return json(monedas(m) satisfies S["Monedas"]);
    case "GET /api/vivo/libro": {
      const x = m.monedas.get(coin);
      return x ? json(libro(m, x) satisfies S["LibroVivo"]) : fallo(404, `No hay ninguna moneda «${coin}» en Hyperliquid.`);
    }
    case "GET /api/vivo/operaciones": {
      const x = m.monedas.get(coin);
      return x ? json(operaciones(x) satisfies S["Operaciones"]) : fallo(404, `No hay ninguna moneda «${coin}» en Hyperliquid.`);
    }
    case "GET /api/vivo/velas": {
      const x = m.monedas.get(coin);
      if (!x) return fallo(404, `No hay ninguna moneda «${coin}» en Hyperliquid.`);
      const intervalo = url.searchParams.get("intervalo") ?? "1h";
      if (!esIntervalo(intervalo)) return fallo(422, `El intervalo «${intervalo}» no existe: usa 1m, 5m, 15m, 1h, 4h o 1d.`);
      const limite = Math.min(5000, Math.max(1, Number(url.searchParams.get("limite") ?? "300") || 300));
      const velas = velasDe(m, x, intervalo).slice(-limite);
      return json({ coin, intervalo, velas: velas.map((v) => ({ ...v })) } satisfies S["Velas"]);
    }
    case "GET /api/vivo/stream":
      return fallo(404, "En el modo de ejemplo el stream lo simula web/mocks/vivo.ts (abrirStream), no esta ruta.");
    case "GET /api/practica":
      return json(cuenta(m) satisfies S["CuentaPractica"]);
    case "POST /api/practica/ordenes":
      return nuevaOrden(m, await cuerpo(peticion));
    case "POST /api/practica/reiniciar": {
      const o = await cuerpo(peticion);
      const inicial = numero(o, "inicial") ?? 10_000;
      if (inicial <= 0) return fallo(422, "El saldo inicial tiene que ser mayor que cero.");
      m.cuenta = cuentaNueva(inicial);
      return json(cuenta(m) satisfies S["CuentaPractica"]);
    }
    case "GET /api/bots/plantillas":
      return json({ plantillas: PLANTILLAS } satisfies S["Plantillas"]);
    case "GET /api/bots":
      return json(bots(m) satisfies S["Bots"]);
    case "POST /api/bots":
      return desplegar(m, await cuerpo(peticion));
    default:
      break;
  }

  const cancelar = /^\/api\/practica\/ordenes\/([^/]+)$/.exec(ruta);
  if (cancelar && metodo === "DELETE") {
    const id = decodeURIComponent(cancelar[1] ?? "");
    const o = m.cuenta.ordenes.find((x) => x.id === id);
    if (!o) return fallo(404, "Esa orden ya no está pendiente: puede que se haya ejecutado o que ya la cancelaras.");
    m.cuenta.saldo += o.apartado;
    m.cuenta.ordenes = m.cuenta.ordenes.filter((x) => x.id !== id);
    return json(cuenta(m) satisfies S["CuentaPractica"]);
  }

  const accion = /^\/api\/bots\/([^/]+)(?:\/(parar|reanudar))?$/.exec(ruta);
  if (accion) {
    const id = decodeURIComponent(accion[1] ?? "");
    const b = m.bots.find((x) => x.id === id);
    if (!b) return fallo(404, "No hay ningún bot con ese id: puede que lo hayas borrado.");
    const que = accion[2];
    if (metodo === "GET" && !que) return json(detalleBot(m, b) satisfies S["DetalleBot"]);
    if (metodo === "DELETE" && !que) {
      m.bots = m.bots.filter((x) => x.id !== id);
      return new Response(null, { status: 204 });
    }
    if (metodo === "POST" && que === "parar") {
      if (b.estado === "parado") return fallo(409, "Ese bot ya estaba parado.");
      b.estado = "parado";
      b.eventos.unshift({ at: iso(m.t), tipo: "parada", texto: "Parado a mano. Conserva lo que tiene, que sigue valorándose a precios de ahora." });
      return json(detalleBot(m, b) satisfies S["DetalleBot"]);
    }
    if (metodo === "POST" && que === "reanudar") {
      if (b.estado === "en_marcha") return fallo(409, "Ese bot ya estaba en marcha.");
      b.estado = "en_marcha";
      b.motivo_error = null;
      b.eventos.unshift({ at: iso(m.t), tipo: "arranque", texto: "Reanudado a mano: vuelve a operar en su próxima decisión." });
      return json(detalleBot(m, b) satisfies S["DetalleBot"]);
    }
  }

  return fallo(404, `Ruta de ejemplo no definida: ${metodo} ${ruta}`);
}

// -- Stream simulado ------------------------------------------------------------------------------

export interface ManejadoresStream {
  abierto: () => void;
  /** `datos` es el JSON en texto, como llega por SSE. */
  evento: (nombre: string, datos: string) => void;
  /** `cerrado`: la conexion no se va a reintentar sola (como un EventSource en CLOSED). */
  error: (cerrado: boolean) => void;
}

/**
 * Lo mismo que emitiria `GET /api/vivo/stream?coin=&intervalo=&canales=`: libro, operaciones y vela
 * cada 250 ms (hasta 4 veces por segundo, para probar que la interfaz no da tirones), monedas y
 * cuenta cada segundo, bots cada dos y el estado al abrir y al cambiar.
 */
export function abrirStream(params: URLSearchParams, h: ManejadoresStream): () => void {
  const m = elMundo();
  const coin = params.get("coin");
  const intervalo = params.get("intervalo") ?? "1h";
  const canales = new Set((params.get("canales") ?? "monedas,libro,operaciones,vela,cuenta,bots,estado").split(",").map((c) => c.trim()));
  const temporizadores: number[] = [];
  let vivo = true;
  let ultimoSeq = m.seq;
  let tic = 0;

  const emitir = (nombre: string, datos: unknown) => {
    if (vivo && canales.has(nombre)) h.evento(nombre, JSON.stringify(datos));
  };

  if (m.escenario === "sin-stream") {
    // Como la API de antes: la ruta responde con error y el EventSource se cierra.
    temporizadores.push(window.setTimeout(() => vivo && h.error(true), 400));
    return () => {
      vivo = false;
      temporizadores.forEach((t) => window.clearTimeout(t));
    };
  }

  let cortado = false;
  const abrir = () => {
    if (!vivo) return;
    cortado = false;
    h.abierto();
    emitir("estado", estadoVivo(m));
    emitir("monedas", monedas(m));
    emitir("cuenta", cuenta(m));
    emitir("bots", bots(m));
  };
  temporizadores.push(window.setTimeout(abrir, 200));

  const ciclo = window.setInterval(() => {
    if (!vivo || cortado) return;
    avanzar(m);
    tic += 1;
    const x = coin ? m.monedas.get(coin) : undefined;
    if (x && m.conectado) {
      emitir("libro", libro(m, x));
      const nuevas = x.operaciones.filter((o) => o.seq > ultimoSeq).map((o) => o.op);
      if (nuevas.length) emitir("operaciones", nuevas);
      if (canales.has("vela") && esIntervalo(intervalo)) {
        const velas = velasDe(m, x, intervalo);
        const ultima = velas[velas.length - 1];
        const penultima = velas[velas.length - 2];
        // Si acaba de cerrar una vela, primero la cerrada y luego la nueva.
        if (penultima && ultima && Date.parse(ultima.inicio) > m.t - 300) emitir("vela", penultima);
        if (ultima) emitir("vela", ultima);
      }
    }
    ultimoSeq = m.seq;
    if (tic % 4 === 0) {
      if (m.conectado) emitir("monedas", monedas(m));
      emitir("cuenta", cuenta(m));
    }
    if (tic % 8 === 0) emitir("bots", bots(m));
  }, PASO_MS);
  temporizadores.push(ciclo);

  if (m.escenario === "intermitente") {
    // Se corta cada ~20 s; el navegador reintentaria solo a los ~3 s.
    const corte = window.setInterval(() => {
      if (!vivo) return;
      cortado = true;
      h.error(false);
      temporizadores.push(window.setTimeout(abrir, 3000));
    }, 20_000);
    temporizadores.push(corte);
  }

  return () => {
    vivo = false;
    temporizadores.forEach((t) => {
      window.clearTimeout(t);
      window.clearInterval(t);
    });
  };
}
