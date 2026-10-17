/**
 * Formato en castellano (docs/panel-v2.md, seccion 8): `1.234,56 €`, `+4,6 %`, "16 oct 2026".
 *
 * - El dinero que llega como cadena (Decimal) se formatea con `decimal.ts`, sin pasar por float.
 * - Lo que llega como `float` (variaciones, puntos de grafica, simulaciones) solo se dibuja: se
 *   formatea aqui.
 * - `null` siempre se pinta como "—": falta el dato, que no es lo mismo que un 0.
 * - El signo negativo es el menos tipografico (−), no el guion: se lee mejor junto a la cifra.
 */
import { formatoImporte, signoDecimal, type OpcionesFormato } from "./decimal";

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

/**
 * Un porcentaje (fraccion) que acompana a un importe con signo: el signo es SIEMPRE el del
 * importe ("Pierdes −2,00 € (−0,06 %)"), y si redondeado a un decimal saldria "0,0 %" se dan dos
 * decimales o "menos del 0,01 %": nunca un cero pelado junto a una perdida.
 */
export function fraccionCoherente(valor: number | null | undefined, signoImporte: -1 | 0 | 1): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  if (signoImporte === 0) return `0${NBSP}%`;
  const abs = Math.abs(valor * 100);
  const marca = signoImporte > 0 ? "+" : "−";
  for (const decimales of [1, 2]) {
    const factor = 10 ** decimales;
    if (Math.round(abs * factor) > 0) return `${marca}${formateador(decimales, decimales, false).format(abs)}${NBSP}%`;
  }
  return `menos del 0,01${NBSP}%`;
}

/** ¿Este texto formateado dice algo distinto de cero? ("+0,0 %" y "0,00" no). */
export function noEsCero(texto: string): boolean {
  return /[1-9]/.test(texto);
}

/**
 * El signo de lo que SE VE, para el color: si la cifra redondeada sale "0,0 %", es neutra aunque
 * el dato fuera −0,0004 (un "Hoy 0,0 %" en rojo dice "pierdes" sin que se vea ninguna perdida).
 */
export function signoVisible(valor: number | null | undefined, texto: string): -1 | 0 | 1 | null {
  const s = signo(valor);
  if (s === null) return null;
  return noEsCero(texto) ? s : 0;
}

/** Lo mismo para un importe exacto (Decimal en cadena) que se ensena con `decimales` cifras. */
export function signoImporteVisible(importe: string | null | undefined, decimales = 2): -1 | 0 | 1 | null {
  if (importe === null || importe === undefined) return null;
  const s = signoDecimal(importe);
  if (s === null) return null;
  return noEsCero(formatoImporte(importe, { decimales })) ? s : 0;
}

/** El simbolo de una moneda para ponerlo detras de la cifra: "€", "$" o el codigo ("USDT"). */
export function simboloMoneda(moneda: string | null | undefined): string {
  const m = (moneda ?? "").toUpperCase();
  return m === "EUR" ? "€" : m === "USD" ? "$" : m || "€";
}

/** Un importe exacto (cadena Decimal) en euros: "1.234,56 €". */
export function euros(texto: string | null | undefined, opciones: OpcionesFormato = {}): string {
  if (texto === null || texto === undefined) return SIN_DATO;
  return `${menos(formatoImporte(texto, opciones))}${NBSP}€`;
}

/** Un importe exacto en otra moneda ("100 USDT", "12,50 $"). */
export function enMoneda(texto: string | null | undefined, moneda: string, opciones: OpcionesFormato = {}): string {
  if (texto === null || texto === undefined) return SIN_DATO;
  return `${menos(formatoImporte(texto, opciones))}${NBSP}${simboloMoneda(moneda)}`;
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
// Los momentos (cuando se puso un freno, se envio una orden, se leyo un saldo) van en la hora de
// quien mira: "11:37 UTC" obligaba a hacer la cuenta. Las fechas de cierre siguen siendo dias.
const FECHA_LOCAL = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric" });
const HORA_LOCAL = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });

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

/**
 * Cuanto hace, en llano y corto: "hace 12 s", "hace 3 min", "hace 2 h", "hace 3 días". Para lo que
 * se mueve en directo (la ultima operacion de un bot); `ahora` lo pasa quien repinta cada segundo.
 */
export function haceCuanto(valor: string | null | undefined, ahora: number): string {
  if (!valor) return SIN_DATO;
  const t = Date.parse(valor);
  if (Number.isNaN(t)) return SIN_DATO;
  const s = Math.max(0, Math.round((ahora - t) / 1000));
  if (s < 5) return "ahora mismo";
  if (s < 60) return `hace ${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `hace ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.floor(h / 24);
  return `hace ${d} ${d === 1 ? "día" : "días"}`;
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

/** Momento con hora, en la hora local de quien mira: "17 oct 2026, 13:37". */
export function momento(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return `${sinPunto(FECHA_LOCAL.format(d))}, ${HORA_LOCAL.format(d)}`;
}

/** Solo la hora local (la foto de cotizaciones, el progreso de una actualizacion): "13:37". */
export function hora(valor: string): string {
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return HORA_LOCAL.format(d);
}

/** Un momento que en realidad es un dia (medianoche UTC): solo la fecha. */
export function esSoloDia(valor: string): boolean {
  return /^\d{4}-\d{2}-\d{2}(T00:00:00(\.0+)?(Z|\+00:00)?)?$/.test(valor);
}

/** Fecha de hoy en la zona del navegador, como AAAA-MM-DD (para los formularios). */
export function hoyLocal(): string {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
}

/**
 * Varias frases de la API en una sola ("Falta: a; b."): cada una pierde su punto final y la
 * frase entera lleva uno. Las de la API ya acaban en punto: sin esto salia "HMAC-SHA256)..".
 */
export function enUnaFrase(frases: readonly string[]): string {
  const limpias = frases.map((f) => f.trim().replace(/[.;\s]+$/, "")).filter(Boolean);
  return limpias.length ? `${limpias.join("; ")}.` : "";
}

/**
 * Cada cuanto le toca hacer algo a quien sigue una estrategia, ademas de aportar
 * (`cambios_al_anio`, contrato v2.1). Las operaciones del motor son otra cosa (Laboratorio).
 */
export function frecuenciaCambios(alAnio: number | null | undefined): string {
  if (alAnio === null || alAnio === undefined || !Number.isFinite(alAnio)) return SIN_DATO;
  const n = Math.round(alAnio);
  if (alAnio < 0.5) return "Casi nunca te tocará hacer nada, además de aportar.";
  if (n === 1) return "Te tocará hacer algo una vez al año, además de aportar.";
  return `Te tocará hacer algo unas ${n} veces al año, además de aportar.`;
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
