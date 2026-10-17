/**
 * Importes exactos. La API manda el dinero como cadena (`Decimal` de Python) para que 0,1 + 0,2
 * no acabe en 0,30000000000000004. Aqui NUNCA se convierten a `number`: se leen como entero
 * `bigint` + escala, se redondean y se formatean con aritmetica entera. Si alguna pantalla
 * necesitara sumar importes, la suma la tiene que dar la API.
 */

export interface DecimalExacto {
  /** Valor absoluto escalado: valor = digitos / 10^escala. */
  readonly digitos: bigint;
  readonly escala: number;
  readonly negativo: boolean;
}

const PATRON = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/;

/** Lee una cadena decimal ("-12.50", "1E+3", "0E-8"). `null` si no es un numero. */
export function leerDecimal(texto: string): DecimalExacto | null {
  const m = PATRON.exec(texto.trim());
  if (!m) return null;
  const signo = m[1] ?? "";
  const entera = m[2] ?? "";
  const fraccion = m[3] ?? "";
  const exponente = m[4] === undefined ? 0 : Number.parseInt(m[4], 10);
  if (entera === "" && fraccion === "") return null;
  let digitos = BigInt(`${entera || "0"}${fraccion}`);
  let escala = fraccion.length - exponente;
  if (escala < 0) {
    digitos *= 10n ** BigInt(-escala);
    escala = 0;
  }
  return { digitos, escala, negativo: signo === "-" && digitos !== 0n };
}

export function esDecimal(texto: string): boolean {
  return leerDecimal(texto) !== null;
}

function aEscala(d: DecimalExacto, escala: number): bigint {
  const valor = escala >= d.escala ? d.digitos * 10n ** BigInt(escala - d.escala) : d.digitos;
  return d.negativo ? -valor : valor;
}

/** -1, 0 o 1, comparando dos decimales sin pasar por float. Lanza si alguno no es un numero. */
export function compararDecimal(a: string, b: string): -1 | 0 | 1 {
  const x = leerDecimal(a);
  const y = leerDecimal(b);
  if (x === null || y === null) throw new Error(`No es un numero: ${x === null ? a : b}`);
  const escala = Math.max(x.escala, y.escala);
  const vx = aEscala(x, escala);
  const vy = aEscala(y, escala);
  return vx < vy ? -1 : vx > vy ? 1 : 0;
}

/** Signo de un decimal: -1, 0 o 1. `null` si no es un numero. */
export function signoDecimal(texto: string): -1 | 0 | 1 | null {
  const d = leerDecimal(texto);
  if (d === null) return null;
  if (d.digitos === 0n) return 0;
  return d.negativo ? -1 : 1;
}

/** Redondeo a `decimales` cifras, la mitad se aleja del cero (ROUND_HALF_UP). */
function redondear(d: DecimalExacto, decimales: number): bigint {
  if (d.escala <= decimales) return d.digitos * 10n ** BigInt(decimales - d.escala);
  const divisor = 10n ** BigInt(d.escala - decimales);
  const cociente = d.digitos / divisor;
  const resto = d.digitos % divisor;
  return resto * 2n >= divisor ? cociente + 1n : cociente;
}

function agrupar(entera: string): string {
  return entera.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export interface OpcionesFormato {
  /** Cifras decimales que se muestran (se redondea). */
  decimales?: number;
  /** Poner "+" delante de los positivos (variaciones, P&L). */
  conSigno?: boolean;
}

/**
 * Un importe para leer, en castellano: "1.234,57". `null`/`undefined` -> "—" (no hay dato, que
 * no es lo mismo que cero). Si la cadena no es un numero se devuelve tal cual: mejor ver el
 * texto raro que un numero inventado.
 */
export function formatoImporte(
  texto: string | null | undefined,
  { decimales = 2, conSigno = false }: OpcionesFormato = {},
): string {
  if (texto === null || texto === undefined) return "—";
  const d = leerDecimal(texto);
  if (d === null) return texto;
  return formatear(d, decimales, conSigno);
}

function formatear(d: DecimalExacto, decimales: number, conSigno: boolean): string {
  const valor = redondear(d, decimales).toString().padStart(decimales + 1, "0");
  const entera = valor.slice(0, valor.length - decimales);
  const fraccion = decimales > 0 ? valor.slice(valor.length - decimales) : "";
  const esCero = /^0*$/.test(entera + fraccion);
  const signo = esCero ? "" : d.negativo ? "-" : conSigno ? "+" : "";
  return `${signo}${agrupar(entera)}${fraccion ? `,${fraccion}` : ""}`;
}

/**
 * Una cantidad (acciones, monedas) sin perder cifras: se muestran todas las que trae la API,
 * sin ceros sobrantes a la derecha, con separador de miles.
 */
export function formatoCantidad(texto: string | null | undefined): string {
  if (texto === null || texto === undefined) return "—";
  const d = leerDecimal(texto);
  if (d === null) return texto;
  const valor = d.digitos.toString().padStart(d.escala + 1, "0");
  const entera = valor.slice(0, valor.length - d.escala);
  const fraccion = d.escala > 0 ? valor.slice(valor.length - d.escala).replace(/0+$/, "") : "";
  return `${d.negativo ? "-" : ""}${agrupar(entera)}${fraccion ? `,${fraccion}` : ""}`;
}

/**
 * Una fraccion decimal ("0.001") como porcentaje ("0,1%"), moviendo la coma -- exacto.
 */
export function fraccionComoPorcentaje(texto: string, decimalesMax = 4): string | null {
  const d = leerDecimal(texto);
  if (d === null) return null;
  const pct: DecimalExacto =
    d.escala >= 2
      ? { ...d, escala: d.escala - 2 }
      : { ...d, digitos: d.digitos * 10n ** BigInt(2 - d.escala), escala: 0 };
  const fijo = formatear(pct, Math.min(pct.escala, decimalesMax), false);
  const limpio = fijo.includes(",") ? fijo.replace(/0+$/, "").replace(/,$/, "") : fijo;
  return `${limpio}%`;
}

/** Comprueba que una fraccion de coste esta en [0, max]. Devuelve el motivo si no. */
export function motivoFraccionInvalida(texto: string, nombre: string, max = "0.05"): string | null {
  const limpio = texto.trim();
  if (limpio === "") return `Falta ${nombre}: los costes son obligatorios.`;
  if (!esDecimal(limpio)) return `${mayuscula(nombre)} no es un número: "${limpio}". Usa punto decimal: 0.001`;
  if (compararDecimal(limpio, "0") < 0) return `${mayuscula(nombre)} no puede ser negativo.`;
  if (compararDecimal(limpio, max) > 0)
    return `${mayuscula(nombre)} es una fracción entre 0 y ${max} (0.001 = 0,1%); recibido ${limpio}.`;
  return null;
}

function mayuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
