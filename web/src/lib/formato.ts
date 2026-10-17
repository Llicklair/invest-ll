/**
 * Formato en castellano (docs/panel-v2.md, seccion 8): `1.234,56 €`, `+4,6 %`, "16 oct 2026".
 *
 * - El dinero que llega como cadena (Decimal) se formatea con `decimal.ts`, sin pasar por float.
 * - Lo que llega como `float` (variaciones, puntos de grafica, simulaciones) solo se dibuja: se
 *   formatea aqui.
 * - `null` siempre se pinta como "—": falta el dato, que no es lo mismo que un 0.
 * - El signo negativo es el menos tipografico (−), no el guion: se lee mejor junto a la cifra.
 */
import { formatoImporte, type OpcionesFormato } from "./decimal";

const cacheFormatos = new Map<string, Intl.NumberFormat>();

function formateador(min: number, max: number, signo: boolean): Intl.NumberFormat {
  const clave = `${min}:${max}:${signo}`;
  let f = cacheFormatos.get(clave);
  if (!f) {
    f = new Intl.NumberFormat("es-ES", {
      minimumFractionDigits: min,
      maximumFractionDigits: max,
      useGrouping: "always",
      signDisplay: signo ? "exceptZero" : "auto",
    });
    cacheFormatos.set(clave, f);
  }
  return f;
}

export const SIN_DATO = "—";
const NBSP = " ";

/** Cambia el guion del signo por el menos tipografico. */
export function menos(texto: string): string {
  return texto.replace(/^-/, "−").replace(/^\+-/, "−");
}

export function numero(valor: number | null | undefined, decimales = 2): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return menos(formateador(decimales, decimales, false).format(valor));
}

/** Un valor que YA viene en porcentaje (2.3 = +2,3 %), con signo. */
export function porcentaje(valor: number | null | undefined, decimales = 1): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return `${menos(formateador(decimales, decimales, true).format(valor))}${NBSP}%`;
}

/** Una fraccion (0.023 = +2,3 %). Multiplicar un float que solo se dibuja es legitimo. */
export function fraccion(valor: number | null | undefined, decimales = 1, conSigno = true): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return `${menos(formateador(decimales, decimales, conSigno).format(valor * 100))}${NBSP}%`;
}

/** Un importe exacto (cadena Decimal) en euros: "1.234,56 €". */
export function euros(texto: string | null | undefined, opciones: OpcionesFormato = {}): string {
  if (texto === null || texto === undefined) return SIN_DATO;
  return `${menos(formatoImporte(texto, opciones))}${NBSP}€`;
}

/** Un importe exacto en otra moneda ("100 USDT"). */
export function enMoneda(texto: string | null | undefined, moneda: string, opciones: OpcionesFormato = {}): string {
  if (texto === null || texto === undefined) return SIN_DATO;
  const simbolo = moneda.toUpperCase() === "EUR" ? "€" : moneda.toUpperCase() === "USD" ? "$" : moneda;
  return `${menos(formatoImporte(texto, opciones))}${NBSP}${simbolo}`;
}

/** Un float que solo se dibuja, en euros y sin decimales por defecto: "14.200 €". */
export function eurosNum(valor: number | null | undefined, decimales = 0, conSigno = false): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return `${menos(formateador(decimales, decimales, conSigno).format(valor))}${NBSP}€`;
}

/** Precio de una cotizacion: mas cifras cuanto mas pequeno, para que 0,000012 no salga 0,00. */
export function precio(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  const abs = Math.abs(valor);
  if (abs >= 100) return formateador(2, 2, false).format(valor);
  if (abs >= 1) return formateador(2, 4, false).format(valor);
  return new Intl.NumberFormat("es-ES", { maximumSignificantDigits: 4 }).format(valor);
}

/** -1, 0, 1 o null, para decidir el color de una variacion. */
export function signo(valor: number | null | undefined): -1 | 0 | 1 | null {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return null;
  return valor > 0 ? 1 : valor < 0 ? -1 : 0;
}

const FECHA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const FECHA_SIN_ANIO = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", timeZone: "UTC" });
const FECHA_LARGA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", timeZone: "UTC" });
const MES_ANIO = new Intl.DateTimeFormat("es-ES", { month: "long", year: "numeric", timeZone: "UTC" });
const MES_ANIO_CORTO = new Intl.DateTimeFormat("es-ES", { month: "short", year: "numeric", timeZone: "UTC" });
const HORA = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

function aFecha(valor: string): Date | null {
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(valor) ? `${valor}T00:00:00Z` : valor;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Quita el punto que algunas versiones de ICU ponen a los meses abreviados ("oct."). */
function sinPunto(texto: string): string {
  return texto.replace(/\.(?=\s|$)/g, "");
}

/** "16 oct 2026". */
export function fecha(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = aFecha(valor);
  return d ? sinPunto(FECHA.format(d)) : valor;
}

/** "16 oct" (cuando el año se sobreentiende). */
export function fechaCorta(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = aFecha(valor);
  return d ? sinPunto(FECHA_SIN_ANIO.format(d)) : valor;
}

/** "1 de noviembre". */
export function diaYMes(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = aFecha(valor);
  return d ? FECHA_LARGA.format(d) : valor;
}

/** "marzo de 2020". */
export function mesYAnio(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = aFecha(valor);
  return d ? MES_ANIO.format(d) : valor;
}

/** "mar 2020". */
export function mesYAnioCorto(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = aFecha(valor);
  return d ? sinPunto(MES_ANIO_CORTO.format(d)) : valor;
}

/** Momento con hora, siempre en UTC y diciendolo: "16 oct 2026, 11:02 UTC". */
export function momento(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return `${sinPunto(FECHA.format(d))}, ${HORA.format(d)} UTC`;
}

/** Solo la hora UTC (para la foto de cotizaciones). */
export function horaUtc(valor: string): string {
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return d.toISOString().slice(11, 16);
}

/** Fecha de hoy en la zona del navegador, como AAAA-MM-DD (para los formularios). */
export function hoyLocal(): string {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
}

/** Años, en llano: "1,8 años", "8 meses". */
export function duracion(anios: number | null | undefined): string {
  if (anios === null || anios === undefined || !Number.isFinite(anios)) return SIN_DATO;
  if (anios < 1) {
    const meses = Math.max(1, Math.round(anios * 12));
    return `${meses} ${meses === 1 ? "mes" : "meses"}`;
  }
  return `${numero(anios, 1)} años`;
}
