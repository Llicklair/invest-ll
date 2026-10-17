/**
 * Las rutas del panel v2 en el modo de ejemplo (docs/panel-v2.md, seccion 9): inicio, plan y
 * "que toca hoy", movimientos, conexion con Binance y modo. Guarda un estado de sesion para que
 * los flujos se puedan recorrer de punta a punta: guardar un plan hace que "hoy" tenga compras,
 * anotar una la quita, una orden de pruebas ejecutada marca la etapa 2 de la conexion...
 *
 * Todo cuerpo va tipado con el contrato: si `web/openapi.json` cambia, `tsc` falla aqui.
 */
import type { components } from "@/api/esquema";

import { DEFS, catalogo, definicion, recomendar, simular, simularCombinado, type Escasez } from "./estrategias";
import { monedaDe, nombreDe, serie } from "./series";

type S = components["schemas"];
type ModoPanel = S["Conexion"]["modo"];
type Origen = S["EstadoRed"]["origen"];

export { DESCRIPCION_ESCENARIOS, ESCENARIOS, type Escenario } from "./escenarios";
import type { Escenario } from "./escenarios";

interface Pos {
  simbolo: string;
  cantidad: number;
  coste: number;
  abierta: string;
  /**
   * Compra del broker hecha desde el plan: `cantidad` son unidades del fondo de EE.UU. de
   * referencia (no tus participaciones) y `coste`, lo que pagaste en euros (contrato v2.1).
   */
  referencia?: boolean;
}

interface CarteraMock {
  posiciones: Pos[];
  retiradas: S["PosicionRetirada"][];
  movimientos: S["Movimiento"][];
  /** Lo ingresado y aun sin invertir. */
  efectivo: number;
}

interface Claves {
  origen: Origen;
  clave: string | null;
}

export interface EstadoPanel {
  escenario: Escenario;
  plan: S["Plan"] | null;
  primeraAportacion: boolean;
  modo: ModoPanel;
  modoOrigen: "panel" | "entorno";
  claves: { pruebas: Claves; real: Claves };
  verificada: boolean;
  hechas: Set<string>;
  carteras: { real: CarteraMock; pruebas: CarteraMock };
  escasez: Escasez;
  falloRed: boolean;
  /** La API recien arrancada: el primer catalogo tarda (~25 s en la de verdad; aqui, 9). */
  frio: boolean;
  siguiente: number;
  datos: DatosMock;
}

/** `/api/datos` del ejemplo: de cuando es cada fuente y la ultima actualizacion (en curso o hecha). */
interface DatosMock {
  hasta: Record<ClaveFuente, string>;
  /** `Date.now()` al pulsar "Actualizar ahora"; `null` si no se ha actualizado en esta sesion. */
  empezado: number | null;
  /** La actualizacion falla al bajar los fondos (para ver como se ensena un paso que sale mal). */
  fallaFondos: boolean;
  aplicada: boolean;
}

type ClaveFuente = "historicos" | "fondos" | "cripto";

const HOY = "2026-10-17";

// -- Utilidades -----------------------------------------------------------------------------------

export function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

export function fallo(status: number, detail: string): Response {
  return json({ detail }, status);
}

/** Contrato v2.1: tambien los errores de validacion llegan como `{"detail": "texto en llano"}`. */
export function validacion(texto: string): Response {
  return fallo(422, texto);
}

const d2 = (v: number) => v.toFixed(2);
function cant(v: number): string {
  return v.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

function ultimoCierre(simbolo: string): { precio: number; fecha: string } | null {
  const s = serie(simbolo);
  const precio = s?.cierres[s.cierres.length - 1];
  const fecha = s?.fechas[s.fechas.length - 1];
  return precio !== undefined && fecha ? { precio, fecha } : null;
}

function variacionMes(simbolo: string): number | null {
  const s = serie(simbolo);
  if (!s) return null;
  const k = simbolo.includes("/") ? 30 : 21;
  const a = s.cierres[s.cierres.length - 1 - k];
  const b = s.cierres[s.cierres.length - 1];
  return a && b ? Math.round((b / a - 1) * 1000) / 10 : null;
}

const nombre = nombreDe;

/** "5,437" o "650,00": las cifras de la `nota` van en castellano, como las diria el broker. */
function es(v: number, decimales: number): string {
  return v.toLocaleString("es-ES", { minimumFractionDigits: decimales, maximumFractionDigits: decimales, useGrouping: true });
}

/** La `nota` de una compra del broker anotada en unidades del fondo de referencia. */
function notaBroker(participaciones: number, precioEuros: number): string {
  return `Compraste ${es(participaciones, 3).replace(/,?0+$/, "")} participaciones a ${es(precioEuros, 2)} € en tu bróker.`;
}

// -- Estado inicial de cada escenario --------------------------------------------------------------

function mov(
  id: string,
  fecha: string,
  tipo: S["Movimiento"]["tipo"],
  simbolo: string | null,
  cantidad: number,
  precio: number | null,
  origen: string,
  comision = 0,
  referencia: { participaciones: number; precio: number } | null = null,
): S["Movimiento"] {
  return {
    id,
    fecha: `${fecha}T09:30:00Z`,
    tipo,
    activo: simbolo ? nombre(simbolo) : null,
    simbolo,
    cantidad: cant(cantidad),
    precio: precio === null ? null : d2(precio),
    comision: d2(comision),
    importe: d2(precio === null ? cantidad : cantidad * precio),
    origen,
    // Lo del broker se paga en euros; el efectivo, tambien.
    moneda: referencia || !simbolo ? "EUR" : monedaDe(simbolo),
    es_referencia: referencia !== null,
    nota: referencia ? notaBroker(referencia.participaciones, referencia.precio) : null,
  };
}

/**
 * Una compra del broker desde el plan, como la guarda la API v2.1: pagaste `participaciones` a
 * `precioEuros` y se apunta en unidades del fondo de EE.UU. `simbolo` al cierre `precioRef`.
 */
function compraBroker(id: string, fecha: string, simbolo: string, participaciones: number, precioEuros: number, precioRef: number, comision: number): { pos: Pos; mov: S["Movimiento"] } {
  const pagado = participaciones * precioEuros;
  const unidades = pagado / precioRef;
  return {
    pos: { simbolo, cantidad: unidades, coste: pagado + comision, abierta: fecha, referencia: true },
    mov: mov(id, fecha, "compra", simbolo, unidades, precioRef, "plan", comision, { participaciones, precio: precioEuros }),
  };
}

function carteraReal(e: Escenario): CarteraMock {
  if (e === "primera-vez" || e === "vacio" || e === "en-frio") return { posiciones: [], retiradas: [], movimientos: [], efectivo: 0 };
  const spy = compraBroker("m-5", "2026-04-01", "SPY", 5.437, 650, 719.5, 3);
  const ief = compraBroker("m-6", "2026-04-01", "IEF", 30.6, 93, 94.9, 3);
  const posiciones: Pos[] = [spy.pos, ief.pos, { simbolo: "BTC/USDT", cantidad: 0.0075, coste: 450, abierta: "2026-05-04" }];
  const movimientos: S["Movimiento"][] = [
    mov("m-7", "2026-05-04", "compra", "BTC/USDT", 0.0075, 59880, "panel", 0.9),
    ief.mov,
    spy.mov,
    mov("m-0", "2026-03-30", "ingreso", null, 6300, null, "manual"),
    mov("m-4", "2026-03-20", "venta", "GLD", 6, 331.67, "manual", 2),
    mov("m-3", "2026-01-12", "compra", "GLD", 6, 300, "manual", 2),
    mov("m-2", "2025-09-30", "venta", "TLT", 20, 80.62, "csv:broker-2025.csv", 0),
    mov("m-1", "2024-05-02", "compra", "TLT", 20, 90.16, "csv:broker-2025.csv", 0),
  ];
  if (e === "real") {
    posiciones.push({ simbolo: "BTC/USDT", cantidad: 0.0005, coste: 40.96, abierta: "2026-10-16" });
    movimientos.unshift(mov("m-8", "2026-10-16", "compra", "BTC/USDT", 0.0005, 81920.04, "panel", 0.04));
  }
  if (e === "sin-datos") {
    posiciones.push({ simbolo: "IBE.MC", cantidad: 120, coste: 1720.4, abierta: "2026-06-22" });
    movimientos.unshift(mov("m-9", "2026-06-22", "compra", "IBE.MC", 120, 14.3367, "manual", 0));
  }
  return {
    posiciones,
    retiradas: [
      { activo: "GLD", nombre: nombre("GLD"), moneda: "USD", abierta: "2026-01-12", retirada: "2026-03-20", dias: 67, invertido: "1802.00", recuperado: "1988.02", pnl_realizado: "186.02" },
      { activo: "TLT", nombre: nombre("TLT"), moneda: "USD", abierta: "2024-05-02", retirada: "2025-09-30", dias: 516, invertido: "1803.20", recuperado: "1612.40", pnl_realizado: "-190.80" },
    ],
    movimientos,
    efectivo: 236.4,
  };
}

function carteraPruebas(e: Escenario): CarteraMock {
  if (!["pruebas", "listo-para-real", "real", "entorno", "fallo-red"].includes(e)) {
    return { posiciones: [], retiradas: [], movimientos: [], efectivo: 0 };
  }
  const conOrden = e !== "pruebas" && e !== "fallo-red";
  return {
    posiciones: conOrden ? [{ simbolo: "BTC/USDT", cantidad: 0.001, coste: 82.09, abierta: "2026-10-14" }] : [],
    retiradas: [],
    movimientos: conOrden ? [mov("p-1", "2026-10-14", "compra", "BTC/USDT", 0.001, 82011.5, "panel", 0.08)] : [],
    efectivo: 0,
  };
}

const PLAN_EJEMPLO: S["Plan"] = {
  partes: [
    { estrategia: "bolsa-equilibrada", inicial: "5400.00", mensual: "180.00" },
    { estrategia: "btc-freno", inicial: "600.00", mensual: "20.00" },
  ],
  dia_del_mes: 1,
  creado: "2026-04-01T09:00:00Z",
  actualizado: "2026-04-01T09:00:00Z",
};

export function nuevoEstado(e: Escenario): EstadoPanel {
  const conPruebas = ["pruebas", "listo-para-real", "real", "fallo-red"].includes(e);
  const conReal = e === "listo-para-real" || e === "real";
  return {
    escenario: e,
    plan: e === "primera-vez" || e === "vacio" || e === "en-frio" ? null : PLAN_EJEMPLO,
    primeraAportacion: false,
    modo: e === "real" ? "real" : conPruebas || e === "entorno" ? "pruebas" : "simulacion",
    modoOrigen: e === "entorno" ? "entorno" : "panel",
    claves: {
      pruebas: e === "entorno" ? { origen: "entorno", clave: "entorno" } : conPruebas ? { origen: "panel", clave: "pruebas-clave-ejemplo" } : { origen: "ninguno", clave: null },
      real: conReal ? { origen: "panel", clave: "real-clave-ejemplo" } : { origen: "ninguno", clave: null },
    },
    verificada: ["listo-para-real", "real", "entorno"].includes(e),
    hechas: new Set(e === "nada-que-hacer" ? ["a-BTC/USDT", "b-SPY", "b-IEF"] : []),
    carteras: { real: carteraReal(e), pruebas: carteraPruebas(e) },
    escasez: e === "sin-datos" ? "sin-cripto" : "ninguna",
    falloRed: e === "fallo-red",
    frio: e === "en-frio",
    siguiente: 100,
    datos: {
      hasta:
        e === "datos-viejos"
          ? { historicos: "2026-09-30", fondos: "2026-09-30", cripto: "2026-10-02" }
          : e === "sin-datos"
            ? { historicos: "2026-10-15", fondos: "2026-10-15", cripto: "2026-10-02" }
            : { historicos: "2026-10-15", fondos: "2026-10-15", cripto: "2026-10-15" },
      // "datos-actualizando": se abre con una actualizacion ya en marcha (empezada hace 3 s).
      empezado: e === "datos-actualizando" ? Date.now() - 3000 : null,
      fallaFondos: e === "datos-viejos",
      aplicada: false,
    },
  };
}

// -- Datos: de cuando son y actualizarlos (contrato v2.1) ------------------------------------------

const FUENTES: { clave: ClaveFuente; nombre: string; paso: string; hecho: string }[] = [
  { clave: "historicos", nombre: "Precios de bolsa, oro y cripto (Mercado)", paso: "Precios de bolsa, oro y cripto", hecho: "14 históricos al día" },
  { clave: "fondos", nombre: "Fondos de las estrategias de bolsa", paso: "Fondos de bolsa", hecho: "8 fondos al día" },
  { clave: "cripto", nombre: "Criptomonedas de Binance (estrategias de cripto)", paso: "Criptomonedas de Binance", hecho: "Bitcoin y otras 29 monedas al día" },
];

/** Cada paso de la actualizacion de ejemplo tarda esto. */
const PASO_MS = 4000;
const AYER = "2026-10-16";

function dias(desde: string): number {
  return Math.round((Date.parse(`${HOY}T00:00:00Z`) - Date.parse(`${desde}T00:00:00Z`)) / 86_400_000);
}

export function estadoDatos(p: EstadoPanel): S["EstadoDatos"] {
  const d = p.datos;
  let trabajo: S["TrabajoDatos"] | null = null;
  if (d.empezado !== null) {
    const pasado = Date.now() - d.empezado;
    const pasos: S["PasoDatos"][] = FUENTES.map((f, i) => {
      const mal = f.clave === "fondos" && d.fallaFondos;
      if (pasado < i * PASO_MS) return { nombre: f.paso, estado: "pendiente", detalle: null };
      if (pasado < (i + 1) * PASO_MS) return { nombre: f.paso, estado: "en_marcha", detalle: "Descargando…" };
      return mal
        ? { nombre: f.paso, estado: "mal", detalle: "Yahoo Finance no respondió tras 3 intentos. Lo demás sí se ha actualizado; vuelve a intentarlo más tarde." }
        : { nombre: f.paso, estado: "bien", detalle: `${f.hecho} hasta el 16 oct.` };
    });
    const terminado = pasado >= FUENTES.length * PASO_MS;
    trabajo = {
      en_marcha: !terminado,
      empezado: new Date(d.empezado).toISOString(),
      terminado: terminado ? new Date(d.empezado + FUENTES.length * PASO_MS).toISOString() : null,
      pasos,
    };
    if (terminado && !d.aplicada) {
      d.aplicada = true;
      for (const f of FUENTES) if (!(f.clave === "fondos" && d.fallaFondos)) d.hasta[f.clave] = AYER;
      if (d.hasta.cripto === AYER) p.escasez = "ninguna";
    }
  }
  const fuentes: S["FuenteDatos"][] = FUENTES.map((f) => {
    const hasta = d.hasta[f.clave];
    const n = dias(hasta);
    return { clave: f.clave, nombre: f.nombre, hasta, dias: n, al_dia: n <= 4 };
  });
  const viejas = fuentes.filter((f) => !f.al_dia);
  const masVieja = viejas.map((f) => f.hasta ?? HOY).sort()[0];
  return {
    fuentes,
    al_dia: viejas.length === 0,
    aviso: masVieja
      ? `Hay precios del ${Number(masVieja.slice(8))} de ${MESES[Number(masVieja.slice(5, 7)) - 1] ?? ""}: lo que depende de ellos (estrategias, tu plan, el mercado) no es de hoy.`
      : null,
    trabajo,
  };
}

export function actualizarDatos(p: EstadoPanel): Response {
  if (estadoDatos(p).trabajo?.en_marcha) return fallo(409, "Ya hay una actualización en marcha: espera a que termine.");
  p.datos.empezado = Date.now();
  p.datos.aplicada = false;
  return json(estadoDatos(p), 202);
}

// -- Cartera del modo activo -----------------------------------------------------------------------

function deModo(p: EstadoPanel): "real" | "pruebas" {
  return p.modo === "pruebas" ? "pruebas" : "real";
}

function abierta(pos: Pos): S["PosicionAbierta"] {
  const c = ultimoCierre(pos.simbolo);
  const valor = c ? pos.cantidad * c.precio : null;
  return {
    activo: pos.simbolo,
    nombre: nombre(pos.simbolo),
    // Lo del broker se apunta con lo que pagaste en euros (y se valora sin contar el cambio).
    moneda: pos.referencia ? "EUR" : monedaDe(pos.simbolo),
    es_referencia: pos.referencia === true,
    cantidad: cant(pos.cantidad),
    coste_medio: d2(pos.coste / pos.cantidad),
    invertido: d2(pos.coste),
    abierta: `${pos.abierta}T00:00:00Z`,
    precio: c ? d2(c.precio) : null,
    precio_fecha: c?.fecha ?? null,
    valor: valor === null ? null : d2(valor),
    pnl_no_realizado: valor === null ? null : d2(valor - pos.coste),
  };
}

/** Las posiciones del mismo activo se agrupan (coste medio), como hace el ledger. */
function agrupadas(c: CarteraMock): Pos[] {
  const porSimbolo = new Map<string, Pos>();
  for (const p of c.posiciones) {
    const previa = porSimbolo.get(p.simbolo);
    porSimbolo.set(
      p.simbolo,
      previa
        ? { ...previa, cantidad: previa.cantidad + p.cantidad, coste: previa.coste + p.coste, referencia: previa.referencia || p.referencia }
        : { ...p },
    );
  }
  return [...porSimbolo.values()];
}

export function carteraV1(p: EstadoPanel, avisosBase: string[]): S["Cartera"] {
  const c = p.carteras[deModo(p)];
  const abiertas = agrupadas(c).map(abierta);
  const vacia = abiertas.length === 0 && c.retiradas.length === 0;
  const sinPrecio = abiertas.filter((a) => a.valor === null).map((a) => a.activo);
  const invertido = agrupadas(c).reduce((s, x) => s + x.coste, 0);
  const valor = abiertas.reduce((s, a) => s + (a.valor === null ? 0 : Number(a.valor)), 0);
  return {
    cartera: deModo(p),
    moneda: deModo(p) === "pruebas" ? "USDT" : "EUR",
    nota_moneda: deModo(p) === "pruebas" ? null : "Aproximado: sin contar el cambio euro-dólar.",
    vacia,
    error: null,
    avisos: [
      ...avisosBase,
      ...sinPrecio.map(
        (s) => `${nombre(s)} no tiene precios descargados: no se puede saber cuánto vale y el total queda incompleto. Actualiza los datos en Ajustes · Datos.`,
      ),
    ],
    abiertas,
    retiradas: c.retiradas,
    invertido_abiertas: d2(invertido),
    valor_total: sinPrecio.length ? null : d2(valor),
    efectivo: d2(c.efectivo),
    realizado_total: d2(c.retiradas.reduce((s, r) => s + Number(r.pnl_realizado), 0)),
  };
}

/**
 * Tu dinero hoy (contrato v2.1): `valor` incluye el efectivo y `puesto` tambien, asi que
 * "has puesto X, ganas Y" suma justo `valor`. Bolsa y cripto se suman sin convertir: se dice.
 */
function patrimonio(p: EstadoPanel): S["Patrimonio"] {
  const c = p.carteras[deModo(p)];
  const abiertas = agrupadas(c).map(abierta);
  const sinPrecio = abiertas.some((a) => a.valor === null);
  const efectivo = Math.max(0, c.efectivo);
  const puesto = agrupadas(c).reduce((s, x) => s + x.coste, 0) + efectivo;
  const valor = abiertas.reduce((s, a) => s + (a.valor === null ? 0 : Number(a.valor)), 0) + efectivo;
  const ganancia = abiertas.reduce((s, a) => s + (a.pnl_no_realizado === null ? 0 : Number(a.pnl_no_realizado)), 0);
  const fechas = abiertas.map((a) => a.precio_fecha).filter((f): f is string => f !== null).sort();
  const enDolares = abiertas.some((a) => a.moneda !== "EUR") || abiertas.some((a) => a.es_referencia);
  return {
    valor: sinPrecio ? null : d2(valor),
    puesto: d2(puesto),
    ganancia: sinPrecio ? null : d2(ganancia),
    ganancia_pct: sinPrecio || puesto === 0 ? null : ganancia / puesto,
    realizado: d2(c.retiradas.reduce((s, r) => s + Number(r.pnl_realizado), 0)),
    fecha_precios: fechas[0] ?? null,
    incompleto: sinPrecio,
    cartera: deModo(p),
    efectivo: d2(efectivo),
    moneda: "EUR",
    nota_moneda: enDolares ? "Aproximado: sin contar el cambio euro-dólar." : null,
  };
}

// -- Que toca hoy (docs/panel-v2.md, seccion 7, en juguete) -----------------------------------------

const PESOS: Record<string, [string, number][]> = {
  "bolsa-equilibrada": [["SPY", 0.6], ["IEF", 0.4]],
  "bolsa-prudente": [["IEF", 0.45], ["GLD", 0.3], ["SPY", 0.25]],
  "bolsa-eeuu": [["SPY", 1]],
  "btc-freno": [["BTC/USDT", 1]],
  "btc-mantener": [["BTC/USDT", 1]],
  "cripto-cesta-freno": [["BTC/USDT", 0.6], ["ETH/USDT", 0.4]],
};

const A_DONDE: Record<string, string> = {
  SPY: "la bolsa de EE.UU.",
  IEF: "los bonos del Tesoro de EE.UU.",
  GLD: "el oro.",
};

const COMPRA_BROKER: Record<string, { de: string; equivalente: string }> = {
  SPY: { de: "un ETF del S&P 500", equivalente: "un ETF UCITS del S&P 500 (p. ej. iShares Core S&P 500, ISIN IE00B5BMR087)" },
  IEF: { de: "un ETF de bonos del Tesoro de EE.UU.", equivalente: "un ETF UCITS de bonos del Tesoro de EE.UU. a 7-10 años" },
  GLD: { de: "un ETC de oro", equivalente: "un ETC de oro físico (p. ej. iShares Physical Gold, ISIN IE00B4ND3602)" },
};

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export function proximaFecha(plan: S["Plan"]): string {
  const [a, m] = HOY.split("-").map(Number) as [number, number];
  const siguiente = m === 12 ? `${a + 1}-01` : `${a}-${String(m + 1).padStart(2, "0")}`;
  return `${siguiente}-${String(plan.dia_del_mes).padStart(2, "0")}`;
}

export function hoy(p: EstadoPanel): S["Hoy"] {
  if (!p.plan) {
    return {
      sin_plan: true,
      modo: p.modo,
      acciones: [],
      resumen: "Todavía no tienes un plan. Responde cinco preguntas en Estrategias y te diremos qué hacer.",
      proxima_fecha: null,
      avisos: [],
    };
  }
  const acciones: S["Accion"][] = [];
  const avisos: string[] = [];
  const mesTexto = MESES[Number(HOY.slice(5, 7)) - 1] ?? "";
  for (const parte of p.plan.partes) {
    const d = definicion(parte.estrategia);
    if (!d) continue;
    const dinero = Number(parte.mensual) + (p.primeraAportacion ? Number(parte.inicial) : 0);
    if (d.mercado === "cripto" && p.escasez === "sin-cripto") {
      avisos.push(`Faltan los datos de Binance: no se puede calcular qué toca en ${d.nombre}. Actualízalos en Ajustes · Datos.`);
      continue;
    }
    for (const [simbolo, peso] of PESOS[parte.estrategia] ?? []) {
      const c = ultimoCierre(simbolo);
      const importe = d.mercado === "cripto" && !p.primeraAportacion ? 101.16 * peso : dinero * peso;
      if (d.mercado === "cripto") {
        const id = `a-${simbolo}`;
        if (p.hechas.has(id) || importe < 10 || !c) continue;
        const cantidad = Math.floor((importe / c.precio) * 1e5) / 1e5;
        acciones.push({
          id,
          donde: "binance",
          estrategia: parte.estrategia,
          titulo: `Comprar ${nombre(simbolo)}`,
          explicacion:
            parte.estrategia === "btc-mantener"
              ? `Tu aportación de ${mesTexto} a ${d.nombre}.`
              : `${nombre(simbolo)} lleva un mes por encima de su media: tu estrategia dice estar dentro, y te faltan unos ${Math.round(importe)} USDT para llegar a tu parte.`,
          activo: nombre(simbolo),
          simbolo: simbolo.split("/")[0] ?? simbolo,
          par: simbolo,
          lado: "buy",
          cantidad: cant(cantidad),
          importe: d2(cantidad * c.precio),
          moneda: "USDT",
          precio_ref: d2(c.precio),
          precio_ref_moneda: "USDT",
          referencia: null,
          precio_fecha: c.fecha,
          equivalente: null,
        });
      } else {
        const id = `b-${simbolo}`;
        if (p.hechas.has(id) || !c) continue;
        const compra = COMPRA_BROKER[simbolo];
        acciones.push({
          id,
          donde: "broker",
          estrategia: parte.estrategia,
          titulo: `Compra unos ${Math.round(importe)} € de ${compra?.de ?? nombre(simbolo)}`,
          explicacion: p.primeraAportacion
            ? `Tu primera aportación a ${d.nombre}: el ${Math.round(peso * 100)} % de lo que empiezas poniendo va aquí.`
            : `Tu aportación de ${mesTexto}: el ${Math.round(peso * 100)} % de ${Math.round(Number(parte.mensual))} € va a ${A_DONDE[simbolo] ?? nombre(simbolo)}`,
          activo: nombre(simbolo),
          simbolo,
          par: null,
          lado: "buy",
          cantidad: (importe / c.precio).toFixed(4),
          importe: d2(importe),
          moneda: "EUR",
          precio_ref: d2(c.precio),
          precio_ref_moneda: monedaDe(simbolo),
          referencia: simbolo,
          precio_fecha: c.fecha,
          equivalente: compra?.equivalente ?? null,
        });
      }
    }
  }
  // Ventas antes que compras; aqui solo hay compras.
  const proxima = proximaFecha(p.plan);
  const [, mm, dd] = proxima.split("-");
  const proximaTexto = `${Number(dd)} de ${MESES[Number(mm) - 1] ?? ""}`;
  return {
    sin_plan: false,
    modo: p.modo,
    acciones,
    resumen: acciones.length
      ? `Hoy toca tu aportación de ${mesTexto}: ${acciones.length === 1 ? "una compra" : `${acciones.length} compras`}.`
      : `No toca hacer nada. Tu próxima aportación es el ${proximaTexto}.`,
    proxima_fecha: proxima,
    avisos,
  };
}

// -- Inicio -----------------------------------------------------------------------------------------

export function inicio(p: EstadoPanel, pausa: string | null): S["Inicio"] {
  const c = p.carteras[deModo(p)];
  const pat = patrimonio(p);
  const h = hoy(p);
  let plan: S["ParteResumen"][] | null = null;
  if (p.plan) {
    plan = p.plan.partes.map((parte) => {
      const d = definicion(parte.estrategia);
      const simbolos = (PESOS[parte.estrategia] ?? []).map(([s]) => s);
      const pos = agrupadas(c).filter((x) => simbolos.includes(x.simbolo));
      const abiertas = pos.map(abierta);
      const valor = abiertas.some((a) => a.valor === null) ? null : d2(abiertas.reduce((s, a) => s + Number(a.valor ?? 0), 0));
      return {
        estrategia: parte.estrategia,
        nombre: d?.nombre ?? parte.estrategia,
        mercado: d?.mercado ?? "bolsa",
        moneda: (d?.mercado ?? "bolsa") === "cripto" ? "USDT" : "EUR",
        valor: pos.length ? valor : "0.00",
        puesto: d2(pos.reduce((s, x) => s + x.coste, 0)),
      };
    });
  }
  // Como la API: la pausa una vez (arriba), y los avisos de "hoy" que no son de la pausa.
  const avisos: string[] = [];
  if (pausa) avisos.push(`Las compras están en pausa: ${pausa}.`);
  if (pat.incompleto) avisos.push("Iberdrola no tiene precio descargado: lo que vale tu dinero hoy no se puede sumar entero.");
  avisos.push(...h.avisos.filter((a) => !a.startsWith("Las compras están en pausa")));
  const mercado: S["MiniMercado"][] = [
    ["Bitcoin", "BTC/USDT"],
    ["Bolsa de EE.UU.", "SPY"],
    ["Oro", "GLD"],
    ["Bonos de EE.UU.", "IEF"],
  ].flatMap(([n, s]) => {
    const cierre = ultimoCierre(s ?? "");
    if (!cierre || !n || !s) return [];
    if (p.escasez === "sin-cripto" && s.includes("/")) return [];
    return [{ nombre: n, symbol: s, precio: cierre.precio, var_1m: variacionMes(s), fecha: cierre.fecha }];
  });
  return {
    patrimonio: pat,
    hay_movimientos: c.movimientos.length > 0 || c.posiciones.length > 0,
    plan,
    acciones_pendientes: pausa ? 0 : h.acciones.length,
    proxima_fecha: p.plan ? proximaFecha(p.plan) : null,
    avisos: [...new Set(avisos)],
    mercado,
  };
}

/** El aviso de la pausa en "que toca hoy", con el texto de la API (src/invest_ll/plan/hoy.py). */
export function avisoPausa(pausa: string): string {
  return `Las compras están en pausa: ${pausa}. Mientras dure no se propone ninguna compra; quítala en Cartera · Protección cuando quieras seguir.`;
}

// -- Plan ---------------------------------------------------------------------------------------------

export function guardarPlan(p: EstadoPanel, o: Record<string, unknown>): Response {
  const partes = Array.isArray(o.partes) ? o.partes : [];
  const dia = Number(o.dia_del_mes);
  if (!partes.length) return validacion("Tu plan necesita al menos una estrategia.");
  if (partes.length > 2) return validacion("Un plan lleva como mucho dos estrategias: una de bolsa y una de cripto.");
  if (!Number.isInteger(dia) || dia < 1 || dia > 28) return validacion("El día del mes para aportar tiene que estar entre el 1 y el 28.");
  const limpias: S["ParteDelPlan-Output"][] = [];
  const mercados: string[] = [];
  for (const x of partes) {
    const parte = typeof x === "object" && x !== null ? (x as Record<string, unknown>) : {};
    const clave = String(parte.estrategia ?? "");
    const d = definicion(clave);
    if (!d) return fallo(422, `No hay ninguna estrategia «${clave}».`);
    if (d.laboratorio) return fallo(422, `${d.nombre} es de Laboratorio: no se puede poner en un plan.`);
    if (mercados.includes(d.mercado)) {
      return fallo(422, `Un plan lleva como mucho una estrategia de bolsa y una de cripto: has elegido dos de ${d.mercado}.`);
    }
    mercados.push(d.mercado);
    const inicial = Number(parte.inicial);
    const mensual = Number(parte.mensual);
    if (!(inicial >= 0) || !(mensual >= 0)) return validacion("Los importes del plan no pueden ser negativos.");
    limpias.push({ estrategia: clave, inicial: d2(inicial), mensual: d2(mensual) });
  }
  const ahora = new Date().toISOString();
  p.plan = { partes: limpias, dia_del_mes: dia, creado: p.plan?.creado ?? ahora, actualizado: ahora };
  p.primeraAportacion = true;
  p.hechas.clear();
  return json({ plan: p.plan } satisfies S["PlanGuardado"]);
}

export function anotarHecha(p: EstadoPanel, id: string, o: Record<string, unknown>): Response {
  const accion = hoy(p).acciones.find((a) => a.id === id);
  if (!accion) return fallo(404, `No hay ninguna acción pendiente con id ${id}: puede que ya esté anotada.`);
  if (accion.donde !== "broker") return fallo(422, "Las compras de Binance se hacen desde el panel, no se anotan a mano.");
  const cantidad = Number(o.cantidad);
  const precio = Number(o.precio);
  const comision = Number(o.comision ?? 0);
  if (!(cantidad > 0)) return validacion("Las participaciones que compraste tienen que ser más que 0.");
  if (!(precio > 0)) return validacion("El precio por participación tiene que ser más que 0.");
  const fecha = String(o.fecha ?? HOY);
  if (fecha > HOY) return fallo(422, `La fecha de la compra (${fecha}) es posterior a hoy.`);
  if (fecha < "2026-10-01") return fallo(422, `La fecha de la compra (${fecha}) es anterior a la aportación de octubre: anótala como un movimiento suelto en Cartera.`);
  p.hechas.add(id);
  p.siguiente += 1;
  // Lo del broker va a la cartera real en cualquier modo, y en unidades del fondo de referencia.
  const c = p.carteras.real;
  const ref = Number(accion.precio_ref ?? precio);
  const compra = compraBroker(`m-${p.siguiente}`, fecha, accion.referencia ?? accion.simbolo, cantidad, precio, ref, comision);
  c.posiciones.push(compra.pos);
  c.movimientos.unshift(compra.mov);
  return json({ activity_id: `act-${p.siguiente}` } satisfies S["MovimientoRegistrado"], 201);
}

/** Lo que hace una orden ejecutada: pasa a la cartera del modo y, en pruebas, cuenta como etapa 2. */
export function ordenEjecutada(p: EstadoPanel, par: string, lado: string, cantidad: number, precio: number): void {
  const c = p.carteras[deModo(p)];
  p.siguiente += 1;
  if (lado === "buy") {
    c.posiciones.push({ simbolo: par, cantidad, coste: cantidad * precio * 1.001, abierta: HOY });
  }
  c.movimientos.unshift(mov(`m-${p.siguiente}`, HOY, lado === "buy" ? "compra" : "venta", par, cantidad, precio, "panel", cantidad * precio * 0.001));
  p.hechas.add(`a-${par}`);
  if (p.modo === "pruebas") p.verificada = true;
}

export function registrarMovimientoV1(p: EstadoPanel, tipo: S["NuevoMovimiento"]["tipo"], simbolo: string | null, cantidad: number, precio: number | null, fecha: string, comision: number): string {
  const c = p.carteras[deModo(p)];
  p.siguiente += 1;
  if (tipo === "compra" && simbolo && precio !== null) {
    c.posiciones.push({ simbolo, cantidad, coste: cantidad * precio + comision, abierta: fecha });
  }
  if (tipo === "ingreso") c.efectivo += cantidad;
  if (tipo === "retirada") c.efectivo -= cantidad;
  c.movimientos.unshift(mov(`m-${p.siguiente}`, fecha, tipo, simbolo, cantidad, precio, "manual", comision));
  return `act-${p.siguiente}`;
}

export function movimientos(p: EstadoPanel): S["Movimientos"] {
  return { cartera: deModo(p), movimientos: p.carteras[deModo(p)].movimientos };
}

// -- Conexion -----------------------------------------------------------------------------------------

function cerrojos(p: EstadoPanel): S["Cerrojo"][] {
  const reales = p.claves.real.origen !== "ninguno";
  return [
    {
      nombre: "El modo",
      ok: p.modo === "real",
      detalle: p.modo === "real" ? "Dinero real activado" : `Estás en ${p.modo === "pruebas" ? "pruebas" : "simulación"}: el dinero real no está activado`,
    },
    {
      nombre: "Las claves de dinero real",
      ok: reales,
      detalle: reales ? "Guardadas en el almacén de credenciales de Windows" : "Todavía no has guardado claves de dinero real",
    },
    {
      nombre: "Haber operado en pruebas",
      ok: p.verificada,
      detalle: p.verificada ? "Hay una orden de pruebas ejecutada en tu registro (14 oct 2026)" : "No hay ninguna orden de pruebas ejecutada en tu registro",
    },
    {
      nombre: "Claves distintas en cada red",
      ok: reales,
      detalle: reales ? "Las claves reales son distintas de las de pruebas" : "Se comprueba al guardar las claves reales",
    },
  ];
}

export function conexion(p: EstadoPanel): S["Conexion"] {
  const pruebas = p.claves.pruebas.origen !== "ninguno";
  const cerr = cerrojos(p);
  const faltaReal = cerr.slice(1).filter((c) => !c.ok).map((c) => c.detalle);
  return {
    modo: p.modo,
    modo_origen: p.modoOrigen,
    redes: [
      { red: "pruebas", claves_guardadas: pruebas, origen: p.claves.pruebas.origen, verificada: p.verificada },
      { red: "real", claves_guardadas: p.claves.real.origen !== "ninguno", origen: p.claves.real.origen, verificada: false },
    ],
    modos: [
      { modo: "simulacion", disponible: true, que_falta: [] },
      {
        modo: "pruebas",
        disponible: pruebas,
        // El texto de la API acaba en punto (src/invest_ll/api/conexion.py): el panel no le pone otro.
        que_falta: pruebas ? [] : ["Guarda las claves de la red de pruebas (testnet.binance.vision, tipo HMAC-SHA256)."],
      },
      { modo: "real", disponible: faltaReal.length === 0, que_falta: faltaReal },
    ],
    cerrojos_real: cerr,
  };
}

export function guardarClaves(p: EstadoPanel, red: string, o: Record<string, unknown>): Response {
  if (red !== "pruebas" && red !== "real") return validacion(`No hay ninguna red «${red}»: son «pruebas» o «real».`);
  const clave = String(o.clave ?? "").trim();
  const secreto = String(o.secreto ?? "").trim();
  if (clave.length < 8) return validacion("La clave es demasiado corta: cópiala entera de Binance.");
  if (secreto.length < 8) return validacion("El secreto es demasiado corto: cópialo entero de Binance.");
  if (p.claves[red].origen === "entorno") {
    return fallo(409, "Estas claves vienen del entorno (INVEST_LL_TESTNET_KEY): cámbialas allí.");
  }
  const otra = red === "real" ? p.claves.pruebas.clave : p.claves.real.clave;
  if (otra && otra === clave) {
    return fallo(422, "La clave de dinero real coincide con la de pruebas. Tienen que ser distintas: si son la misma, no hay separación real entre modos.");
  }
  p.claves[red] = { origen: "panel", clave };
  return new Response(null, { status: 204 });
}

export function borrarClaves(p: EstadoPanel, red: string): Response {
  if (red !== "pruebas" && red !== "real") return fallo(422, `Red desconocida: ${red}`);
  if (p.claves[red].origen === "ninguno") return fallo(404, `No había claves guardadas para ${red}.`);
  if (p.claves[red].origen === "entorno") return fallo(409, "Estas claves vienen del entorno: bórralas allí (variables INVEST_LL_*).");
  p.claves[red] = { origen: "ninguno", clave: null };
  if (red === "real" && p.modo === "real") p.modo = "simulacion";
  if (red === "pruebas" && p.modo === "pruebas") p.modo = "simulacion";
  return new Response(null, { status: 204 });
}

/** Claves que Binance rechazaria en el ejemplo: las que dicen ser Ed25519 o RSA, o "mala". */
function rechazadas(clave: string | null): boolean {
  return clave !== null && /ed25519|rsa|mala/i.test(clave);
}

export function probar(p: EstadoPanel, red: string): Response {
  if (red !== "pruebas" && red !== "real") return fallo(422, `Red desconocida: ${red}`);
  const c = p.claves[red];
  if (c.origen === "ninguno") return fallo(422, `No hay claves de ${red === "pruebas" ? "pruebas" : "dinero real"} guardadas: pégalas primero.`);
  if (rechazadas(c.clave)) {
    return json({
      ok: false,
      detalle: "Binance ha rechazado la firma. ¿Creaste la clave de tipo HMAC-SHA256? Las de tipo Ed25519 o RSA no sirven aquí: crea otra y pégala.",
      saldo: [],
    } satisfies S["PruebaConexion"]);
  }
  const saldo: S["SaldoMoneda"][] =
    red === "pruebas"
      ? [
          { moneda: "USDT", cantidad: "9917.91" },
          { moneda: "BTC", cantidad: "1.001" },
          { moneda: "ETH", cantidad: "1" },
          { moneda: "BNB", cantidad: "1" },
        ]
      : [
          { moneda: "USDT", cantidad: "412.50" },
          { moneda: "BTC", cantidad: "0.0005" },
        ];
  return json({
    ok: true,
    detalle:
      red === "pruebas"
        ? "Conexión correcta con la red de pruebas de Binance. Este es tu saldo ficticio. No se ha enviado ninguna orden."
        : "Conexión correcta con Binance. Solo se ha leído tu saldo: no se ha enviado ninguna orden.",
    saldo,
  } satisfies S["PruebaConexion"]);
}

export function cambiarModo(p: EstadoPanel, o: Record<string, unknown>): Response {
  const modo = String(o.modo ?? "");
  if (modo !== "simulacion" && modo !== "pruebas" && modo !== "real") {
    return validacion(`No hay ningún modo «${modo}»: son simulación, pruebas o dinero real.`);
  }
  if (p.modoOrigen === "entorno") {
    return fallo(409, "El modo lo fija el entorno (INVEST_LL_MODE=testnet): cámbialo allí y vuelve a arrancar el panel.");
  }
  const disponible = conexion(p).modos.find((m) => m.modo === modo);
  if (disponible && !disponible.disponible) return fallo(422, `Todavía no se puede: ${disponible.que_falta.join("; ")}.`);
  // v2.1: antes de pasar a pruebas o a real, la API prueba las claves; si Binance las rechaza, no cambia.
  if ((modo === "pruebas" || modo === "real") && rechazadas(p.claves[modo].clave)) {
    return fallo(
      422,
      `Binance ha rechazado tus claves de ${modo === "pruebas" ? "pruebas" : "dinero real"}. ¿Creaste la clave de tipo HMAC-SHA256? Bórralas, crea otras y vuelve a probar.`,
    );
  }
  if (modo === "real" && o.confirmacion !== "DINERO REAL") {
    return fallo(422, "Para activar el dinero real escribe exactamente DINERO REAL.");
  }
  p.modo = modo;
  return json(conexion(p));
}

export function saldo(p: EstadoPanel): Response {
  if (p.modo === "simulacion") return fallo(409, "En simulación no hay saldo de Binance: el panel no está conectado a nada.");
  const s: S["Saldo"] = {
    modo: p.modo,
    saldo:
      p.modo === "pruebas"
        ? [
            { moneda: "USDT", cantidad: "9917.91" },
            { moneda: "BTC", cantidad: "1.001" },
          ]
        : [
            { moneda: "USDT", cantidad: "412.50" },
            { moneda: "BTC", cantidad: "0.0005" },
          ],
    at: new Date().toISOString(),
  };
  return json(s);
}

// -- Estrategias ---------------------------------------------------------------------------------------

export async function rutaCatalogo(p: EstadoPanel): Promise<Response> {
  if (p.frio) {
    p.frio = false;
    await new Promise((r) => setTimeout(r, 9000));
  }
  return json(catalogo(p.escasez));
}

export function rutaSimular(p: EstadoPanel, o: Record<string, unknown>): Response {
  const claves = Array.isArray(o.estrategias) ? o.estrategias.map(String) : [];
  if (claves.length < 1) return validacion("Elige al menos una estrategia.");
  if (claves.length > 4) return validacion("Como mucho cuatro estrategias a la vez.");
  const inicial = Number(o.inicial);
  const mensual = Number(o.mensual);
  const anio = Number(o.desde_anio);
  if (!(inicial >= 0)) return validacion("Lo que pones para empezar no puede ser negativo.");
  if (!(mensual >= 0)) return validacion("Lo que pones cada mes no puede ser negativo.");
  if (!(anio >= 2008)) return validacion("El año de inicio tiene que ser 2008 o posterior.");
  const resultados: S["ResultadoSimulado"][] = [];
  for (const clave of claves) {
    const d = definicion(clave);
    if (!d) return fallo(404, `No hay ninguna estrategia «${clave}».`);
    if (p.escasez === "sin-cripto" && d.mercado === "cripto") {
      return fallo(422, `No se puede calcular ${d.nombre}: faltan los datos de Binance. Actualízalos en Ajustes · Datos.`);
    }
    const r = simular(clave, inicial, mensual, anio);
    if (r) resultados.push(r);
  }
  // v2.1: con `reparto` (porcentajes que suman 100), tambien la curva de tu reparto entero.
  let combinado: S["ResultadoSimulado"] | null = null;
  if (Array.isArray(o.reparto)) {
    const reparto = o.reparto.map((x) => {
      const r = typeof x === "object" && x !== null ? (x as Record<string, unknown>) : {};
      return { estrategia: String(r.estrategia ?? ""), porcentaje: Number(r.porcentaje) };
    });
    if (reparto.reduce((s, r) => s + r.porcentaje, 0) !== 100) return validacion("El reparto tiene que sumar 100 %.");
    for (const r of reparto) {
      if (!definicion(r.estrategia)) return fallo(404, `No hay ninguna estrategia «${r.estrategia}».`);
    }
    combinado = simularCombinado(reparto, inicial, mensual, anio);
  }
  return json({
    resultados,
    combinado,
    nota: "Simulación sobre el pasado con comisiones incluidas. Aportación el primer día con datos de cada mes.",
  } satisfies S["Simulacion"]);
}

export function rutaRecomendar(o: Record<string, unknown>): Response {
  const h = String(o.horizonte ?? "");
  const c = String(o.ante_caida ?? "");
  const q = String(o.cripto ?? "");
  if (!["menos-2", "2-5", "5-10", "mas-10"].includes(h)) return validacion("Falta decir cuándo vas a necesitar este dinero.");
  if (!["vender", "esperar", "comprar"].includes(c)) return validacion("Falta decir qué harías si lo que inviertes cae a la mitad.");
  if (!["no", "poco", "si"].includes(q)) return validacion("Falta decir si quieres algo de criptomonedas.");
  const inicial = Number(o.inicial);
  const mensual = Number(o.mensual);
  if (!(inicial >= 0)) return validacion("Lo que pones para empezar no puede ser negativo.");
  if (!(mensual >= 0)) return validacion("Lo que pones cada mes no puede ser negativo.");
  const perfil: S["Perfil"] = {
    inicial: String(inicial),
    mensual: String(mensual),
    horizonte: h as S["Perfil"]["horizonte"],
    ante_caida: c as S["Perfil"]["ante_caida"],
    cripto: q as S["Perfil"]["cripto"],
  };
  return json(recomendar(perfil));
}

export const CLAVES_CATALOGO = DEFS.map((d) => d.clave);
