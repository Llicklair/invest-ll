/**
 * Formato de lo que llega como `float`: variaciones, puntos de grafica, pesos. Son cifras que
 * solo se dibujan (el dinero va como cadena y se formatea en `decimal.ts`). `null` siempre se
 * pinta como "—": falta el dato, que no es lo mismo que un 0%.
 */

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

export function numero(valor: number | null | undefined, decimales = 2): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return formateador(decimales, decimales, false).format(valor);
}

/** Un valor que YA viene en porcentaje (2.3 = 2,3%), con signo. */
export function porcentaje(valor: number | null | undefined, decimales = 1): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return `${formateador(decimales, decimales, true).format(valor)}%`;
}

/** Una fraccion (0.023 = 2,3%). Multiplicar un float que solo se dibuja es legitimo. */
export function fraccion(valor: number | null | undefined, decimales = 1, conSigno = true): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  return `${formateador(decimales, decimales, conSigno).format(valor * 100)}%`;
}

/** Precio de una cotizacion: mas cifras cuanto mas pequeno, para que 0,000012 no salga 0,00. */
export function precio(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return SIN_DATO;
  const abs = Math.abs(valor);
  if (abs >= 100) return formateador(2, 2, false).format(valor);
  if (abs >= 1) return formateador(2, 4, false).format(valor);
  return new Intl.NumberFormat("es-ES", { maximumSignificantDigits: 4 }).format(valor);
}

/** -1, 0, 1 o null, para decidir el color de una celda de variacion. */
export function signo(valor: number | null | undefined): -1 | 0 | 1 | null {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return null;
  return valor > 0 ? 1 : valor < 0 ? -1 : 0;
}

/** Fecha ISO tal cual (AAAA-MM-DD): corta, ordenable e inequivoca. */
export function fecha(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  return valor.slice(0, 10);
}

/** Momento con hora, siempre en UTC y diciendolo. */
export function momento(valor: string | null | undefined, conSegundos = false): string {
  if (!valor) return SIN_DATO;
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  const iso = d.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, conSegundos ? 19 : 16)} UTC`;
}

/** Solo la hora UTC (para la foto de cotizaciones). */
export function horaUtc(valor: string): string {
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return d.toISOString().slice(11, 19);
}

/** Fecha de hoy en la zona del navegador, como AAAA-MM-DD (para el formulario del ledger). */
export function hoyLocal(): string {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
}
