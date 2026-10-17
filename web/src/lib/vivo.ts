/**
 * Lo comun del panel v3 en vivo (docs/panel-v3-vivo.md): intervalos de vela, precision de precios
 * y cantidades al estilo de Hyperliquid, y la vista previa de una orden contra el libro.
 *
 * Todo lo de aqui es para DIBUJAR o ADELANTAR una cifra aproximada: el precio y la comision de
 * verdad los calcula la API al ejecutar (invest_ll/vivo/ejecucion.py). Por eso se trabaja con
 * `number` y no con los decimales exactos de lib/decimal.ts.
 */
import type { LibroVivo, NivelLibro } from "@/api/tipos";

import { SIN_DATO, menos } from "./formato";

/** Los intervalos que ofrece la pantalla de Operar (Hyperliquid tiene mas; estos bastan). */
export const INTERVALOS = [
  { clave: "1m", texto: "1m", largo: "1 minuto", ms: 60_000 },
  { clave: "5m", texto: "5m", largo: "5 minutos", ms: 300_000 },
  { clave: "15m", texto: "15m", largo: "15 minutos", ms: 900_000 },
  { clave: "1h", texto: "1h", largo: "1 hora", ms: 3_600_000 },
  { clave: "4h", texto: "4h", largo: "4 horas", ms: 14_400_000 },
  { clave: "1d", texto: "1d", largo: "1 día", ms: 86_400_000 },
] as const;
export type Intervalo = (typeof INTERVALOS)[number]["clave"];

export function esIntervalo(v: string): v is Intervalo {
  return INTERVALOS.some((i) => i.clave === v);
}

export function msIntervalo(intervalo: string): number {
  return INTERVALOS.find((i) => i.clave === intervalo)?.ms ?? 3_600_000;
}

export function nombreIntervalo(intervalo: string): string {
  return INTERVALOS.find((i) => i.clave === intervalo)?.largo ?? intervalo;
}

/**
 * Las comisiones de la cuenta de practica (docs/panel-v3-vivo.md, seccion 2: las de Hyperliquid
 * de nivel base). El contrato v3 no las manda (`CuentaPractica` no lleva comisiones): se usan para
 * la vista previa, y la cifra de verdad es la que devuelve la API al ejecutar.
 */
export const COMISION_TOMADOR = 0.00045;
export const COMISION_CREADOR = 0.00015;

/**
 * El paso de precio de una moneda, con la regla de Hyperliquid para perpetuos: como mucho 5
 * cifras significativas y `6 - decimales_cantidad` decimales. (El contrato no trae el paso de
 * precio; `MonedaVivo.decimales_cantidad` si.)
 */
export function pasoPrecio(precio: number, decimalesCantidad: number): number {
  if (!Number.isFinite(precio) || precio <= 0) return 0.01;
  const porCifras = 10 ** (Math.floor(Math.log10(precio)) - 4);
  const porDecimales = 10 ** -Math.max(0, 6 - decimalesCantidad);
  return Math.max(porCifras, porDecimales);
}

/** Cuantos decimales se pintan en los precios de una moneda (los de su paso de precio). */
export function decimalesPrecio(precio: number, decimalesCantidad: number): number {
  const paso = pasoPrecio(precio, decimalesCantidad);
  return Math.max(0, Math.min(8, Math.round(-Math.log10(paso))));
}

const cache = new Map<string, Intl.NumberFormat>();
function fmt(decimales: number, signo = false): Intl.NumberFormat {
  const clave = `${decimales}:${signo}`;
  let f = cache.get(clave);
  if (!f) {
    f = new Intl.NumberFormat("es-ES", {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
      useGrouping: "always",
      signDisplay: signo ? "exceptZero" : "auto",
    });
    cache.set(clave, f);
  }
  return f;
}

/** Un precio con un numero FIJO de decimales (las columnas del libro se alinean). */
export function precioFijo(valor: number | null | undefined, decimales: number): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return menos(fmt(decimales).format(valor));
}

/** Una cantidad de moneda con sus decimales como mucho, sin ceros de sobra a la derecha. */
export function cantidadMoneda(valor: number | null | undefined, decimales: number): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  const texto = fmt(decimales).format(valor);
  return menos(texto.includes(",") ? texto.replace(/0+$/, "").replace(/,$/, "") : texto);
}

/** Un numero con signo y decimales fijos: "+12,40". */
export function conSigno(valor: number | null | undefined, decimales = 2): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return menos(fmt(decimales, true).format(valor));
}

/** Volumenes: "1.862 M", "312,4 M", "84,2 mil", "950". */
export function compacto(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  const abs = Math.abs(valor);
  if (abs >= 1e6) return menos(`${fmt(abs >= 1e8 ? 0 : 1).format(valor / 1e6)} M`);
  if (abs >= 1e4) return menos(`${fmt(abs >= 1e5 ? 0 : 1).format(valor / 1e3)} mil`);
  return menos(fmt(abs >= 100 ? 0 : 2).format(valor));
}

const HORA_SEG = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** La hora local con segundos ("14:32:05"): la de los datos en vivo. */
export function horaSegundos(valor: string | number | Date | null | undefined): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  const d = valor instanceof Date ? valor : new Date(valor);
  return Number.isNaN(d.getTime()) ? SIN_DATO : HORA_SEG.format(d);
}

/** Lo que se tarda en leer bien un nombre de moneda: sin tildes ni mayusculas. */
export function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/** Redondea hacia abajo a `decimales` (una cantidad nunca se pasa de lo que hay). */
export function truncar(valor: number, decimales: number): number {
  const f = 10 ** decimales;
  return Math.floor(valor * f + 1e-9) / f;
}

// -- Vista previa de una orden ------------------------------------------------------------------

export interface Previa {
  /** En la moneda. */
  cantidad: number;
  /** Cantidad por precio medio, SIN comision (como `Ejecucion.importe` de la API). */
  importe: number;
  precioMedio: number;
  comision: number;
  /** Niveles del libro que se comerian. */
  niveles: number;
  /** El libro visible no tiene bastante: la API diria que no. */
  insuficiente: boolean;
}

/**
 * Lo que pasaria a mercado con el libro que se ve AHORA: se recorre nivel a nivel, como hace la
 * API, con la comision de tomador. Se da la cantidad (en la moneda) o el importe (en USDC, sin
 * comision).
 */
export function previaMercado(
  libro: Pick<LibroVivo, "compras" | "ventas">,
  lado: "compra" | "venta",
  pedido: { cantidad: number } | { importe: number },
): Previa | null {
  const niveles: readonly NivelLibro[] = lado === "compra" ? libro.ventas : libro.compras;
  const objetivo = "cantidad" in pedido ? pedido.cantidad : pedido.importe;
  if (!(objetivo > 0) || !niveles.length) return null;
  let llevada = 0;
  let gastado = 0;
  let usados = 0;
  for (const n of niveles) {
    if (!(n.cantidad > 0)) continue;
    usados += 1;
    const toma = "cantidad" in pedido ? Math.min(n.cantidad, pedido.cantidad - llevada) : Math.min(n.cantidad, (pedido.importe - gastado) / n.precio);
    llevada += toma;
    gastado += toma * n.precio;
    const resto = "cantidad" in pedido ? pedido.cantidad - llevada : pedido.importe - gastado;
    if (resto <= objetivo * 1e-9) {
      return { cantidad: llevada, importe: gastado, precioMedio: gastado / llevada, comision: gastado * COMISION_TOMADOR, niveles: usados, insuficiente: false };
    }
  }
  if (llevada <= 0) return null;
  return { cantidad: llevada, importe: gastado, precioMedio: gastado / llevada, comision: gastado * COMISION_TOMADOR, niveles: usados, insuficiente: true };
}

/** Con limite: a su precio y con comision de creador, cuando se ejecute. */
export function previaLimite(cantidad: number, precioLimite: number): Previa | null {
  if (!(cantidad > 0) || !(precioLimite > 0)) return null;
  const importe = cantidad * precioLimite;
  return { cantidad, importe, precioMedio: precioLimite, comision: importe * COMISION_CREADOR, niveles: 1, insuficiente: false };
}

/** Mejor compra, mejor venta y precio medio del libro. */
export function extremos(libro: Pick<LibroVivo, "compras" | "ventas"> | null): {
  compra: number | null;
  venta: number | null;
  medio: number | null;
} {
  const compra = libro?.compras[0]?.precio ?? null;
  const venta = libro?.ventas[0]?.precio ?? null;
  return { compra, venta, medio: compra !== null && venta !== null ? (compra + venta) / 2 : (compra ?? venta) };
}
