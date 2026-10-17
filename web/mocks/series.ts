/**
 * Historicos de ejemplo para el modo `NEXT_PUBLIC_MOCK=1`. Son INVENTADOS, pero anclados a los
 * cierres reales que tenia el repo el 2026-10-15 (ultimo cierre, y hace 1, 5, 21, 63, 252 y 1.260
 * sesiones), asi que las variaciones de la mesa salen con ordenes de magnitud creibles. Entre
 * ancla y ancla, un paseo aleatorio con semilla: siempre el mismo dibujo.
 */

export interface DefSerie {
  id: string;
  simbolo: string;
  proveedor: string;
  cripto: boolean;
  desde: string;
  hasta: string;
  /**
   * [sesiones antes del final, cierre] (la sesion 0 es el ultimo cierre; -1, el primero) o
   * [fecha AAAA-MM-DD, cierre]: los hitos reales (marzo de 2020, el invierno cripto de 2018 y
   * 2022...) van por fecha para que las curvas tengan sus caidas donde las tuvieron.
   */
  anclas: [number | string, number][];
  volatilidad: number;
  queEs: string;
  descargado: string | null;
}

export const DEFINICIONES: DefSerie[] = [
  def("IEF", false, "2015-01-02", "2026-10-15", "Bonos EE.UU. 7-10 años", 0.065, [[0, 96.42], [1, 96.31], [5, 96.05], [21, 95.6], [63, 94.9], [252, 94.12], [700, 92.8], [1260, 104.2], [1700, 112.5], [-1, 104.9]]),
  def("GLD", false, "2015-01-02", "2026-10-15", "Oro", 0.15, [[0, 382.71], [1, 375.99], [5, 378.62], [21, 391.74], [63, 368.41], [120, 495.9], [252, 380.79], [1260, 164.16], ["2020-08-06", 194.4], ["2018-08-16", 113.0], ["2015-12-17", 100.5], [-1, 114.08]]),
  def("TLT", false, "2015-01-02", "2026-10-15", "Bonos EE.UU. largo plazo", 0.14, [[0, 79.97], [1, 78.89], [5, 77.87], [21, 80.56], [63, 83.52], [252, 86.83], [1260, 119.45], [1560, 141.02], [-1, 127.3]]),
  def("SPY", false, "2015-01-02", "2026-10-15", "S&P 500", 0.17, [[0, 771.79], [1, 769.6], [3, 779.09], [5, 773.93], [21, 752.18], [63, 741.45], [252, 655.16], [1260, 410.28], ["2022-10-12", 357.7], ["2022-01-03", 477.7], ["2020-03-23", 222.9], ["2020-02-19", 338.3], ["2018-12-24", 234.3], ["2018-09-20", 293.6], ["2016-02-11", 182.9], [-1, 205.43]]),
  def("QQQ", false, "2015-01-02", "2026-10-15", "Nasdaq 100", 0.21, [[0, 728.0], [1, 728.95], [5, 747.58], [9, 759.66], [21, 703.99], [63, 694.61], [252, 595.2], [1260, 352.28], [-1, 102.94]]),
  def("XLE", false, "2015-01-02", "2026-10-15", "Energia", 0.26, [[0, 66.56], [1, 67.63], [5, 65.24], [21, 63.65], [63, 57.34], [252, 41.99], [1260, 23.02], [-1, 39.5]]),
  def("XLF", false, "2015-01-02", "2026-10-15", "Finanzas", 0.2, [[0, 55.27], [1, 54.52], [5, 54.23], [21, 55.73], [40, 58.35], [63, 56.06], [252, 52.41], [1260, 35.63], [-1, 20.31]]),
  def("XLK", false, "2015-01-02", "2026-10-15", "Tecnologia", 0.23, [[0, 189.19], [1, 190.43], [5, 197.78], [8, 202.0], [21, 183.72], [63, 175.39], [252, 140.04], [1260, 73.5], [-1, 21.3]]),
  def("XLV", false, "2015-01-02", "2026-10-15", "Salud", 0.15, [[0, 177.19], [1, 173.96], [5, 168.16], [21, 167.13], [63, 160.48], [252, 140.0], [1260, 117.61], [-1, 68.2]]),
  def("XLU", false, "2015-01-02", "2025-11-28", "Servicios publicos", 0.16, [[0, 41.65], [1, 41.72], [5, 41.07], [21, 41.02], [63, 44.84], [100, 46.75], [252, 44.58], [1260, 28.07], [-1, 22.1]], "2025-11-29"),
  def("AAPL", false, "2015-01-02", "2026-10-15", "Apple", 0.28, [[0, 342.0], [1, 342.96], [5, 340.42], [21, 332.41], [63, 333.45], [252, 246.86], [1260, 139.76], [-1, 24.86]], null),
  def("BTC/USDT", true, "2017-09-01", "2026-10-15", "Bitcoin", 0.55, [[0, 82245.93], [1, 81682.01], [5, 82988.36], [21, 84410.24], [63, 63490.86], [160, 124658.54], [252, 62909.86], ["2025-10-06", 124100], ["2025-04-08", 76300], ["2024-12-17", 106100], ["2024-08-05", 54000], ["2024-03-14", 73100], ["2023-09-11", 25100], [1260, 28838.16], ["2022-11-21", 15780], ["2022-03-28", 47100], ["2021-11-10", 68700], ["2021-07-20", 29800], ["2021-04-14", 64900], ["2021-01-02", 32200], ["2020-03-13", 4800], ["2020-02-13", 10350], ["2019-06-26", 12900], ["2018-12-15", 3200], ["2018-02-06", 6900], ["2017-12-17", 19500], [-1, 4700.0]]),
  def("ETH/USDT", true, "2017-09-01", "2026-10-15", "—", 0.7, [[0, 2442.08], [1, 2421.6], [5, 2506.52], [21, 2688.05], [63, 1886.15], [150, 4832.07], [252, 1826.83], ["2024-03-12", 4060], ["2023-06-15", 1640], [1260, 1877.07], ["2022-06-18", 990], ["2021-11-10", 4810], ["2021-05-12", 4170], ["2020-03-13", 110], ["2018-12-15", 85], ["2018-01-13", 1390], [-1, 387.0]]),
  def("SOL/USDT", true, "2020-08-11", "2026-10-15", "—", 0.9, [[0, 142.3], [1, 140.1], [5, 148.9], [21, 161.2], [63, 118.4], [252, 131.6], [400, 259.0], ["2024-03-18", 203], ["2023-12-25", 120], [1260, 22.4], ["2022-12-29", 9.8], ["2021-11-06", 258], ["2021-01-01", 1.5], [-1, 3.0]]),
];

/** Nombres llanos del ejemplo, como los devuelve la API v2.1 (`nombre`). */
const NOMBRES: Record<string, string> = {
  IEF: "Bonos de EE.UU. a 7-10 años",
  GLD: "Oro",
  TLT: "Bonos de EE.UU. a largo plazo",
  SPY: "Bolsa de EE.UU.",
  QQQ: "Tecnológicas de EE.UU. (Nasdaq 100)",
  XLE: "Energía de EE.UU.",
  XLF: "Bancos de EE.UU.",
  XLK: "Tecnología de EE.UU.",
  XLV: "Salud de EE.UU.",
  XLU: "Eléctricas de EE.UU.",
  XLP: "Consumo básico de EE.UU.",
  AAPL: "Apple",
  NVDA: "Nvidia",
  MSFT: "Microsoft",
  "IBE.MC": "Iberdrola",
  "SAN.MC": "Banco Santander",
  "BTC/USDT": "Bitcoin",
  "ETH/USDT": "Ethereum",
  "SOL/USDT": "Solana",
  "BNB/USDT": "BNB",
  "XRP/USDT": "XRP",
};

export function nombreDe(simbolo: string): string {
  return NOMBRES[simbolo] ?? simbolo;
}

/** La moneda del precio: la del par en cripto; euros en Madrid; dolares en EE.UU. */
export function monedaDe(simbolo: string): string {
  if (simbolo.includes("/")) return simbolo.split("/")[1] ?? "USDT";
  if (/\.(MC|PA|DE|AS|MI)$/.test(simbolo)) return "EUR";
  if (simbolo.endsWith(".SW")) return "CHF";
  return "USD";
}

function def(
  simbolo: string,
  cripto: boolean,
  desde: string,
  hasta: string,
  queEs: string,
  volatilidad: number,
  anclas: [number | string, number][],
  descargado: string | null = "2026-10-16",
): DefSerie {
  const proveedor = cripto ? "ccxt-binance" : "yfinance";
  return { id: `${proveedor}:${simbolo}:DAY_1`, simbolo, proveedor, cripto, desde, hasta, anclas, volatilidad, queEs, descargado };
}

function semilla(texto: string): number {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** mulberry32: aleatorio con semilla, para que el dibujo no cambie entre recargas. */
function aleatorio(s: number): () => number {
  let a = s;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(r: () => number): number {
  const u = Math.max(r(), 1e-12);
  const v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function fechas(desde: string, hasta: string, cripto: boolean): string[] {
  const salida: string[] = [];
  const fin = Date.parse(`${hasta}T00:00:00Z`);
  for (let t = Date.parse(`${desde}T00:00:00Z`); t <= fin; t += 86_400_000) {
    const dia = new Date(t).getUTCDay();
    if (cripto || (dia !== 0 && dia !== 6)) salida.push(new Date(t).toISOString().slice(0, 10));
  }
  return salida;
}

export interface SerieGenerada {
  def: DefSerie;
  fechas: string[];
  cierres: number[];
}

const cache = new Map<string, SerieGenerada>();

export function serie(simbolo: string): SerieGenerada | null {
  const d = DEFINICIONES.find((x) => x.simbolo === simbolo || x.id === simbolo);
  if (!d) return null;
  const guardada = cache.get(d.id);
  if (guardada) return guardada;

  const dias = fechas(d.desde, d.hasta, d.cripto);
  const n = dias.length;
  const r = aleatorio(semilla(d.id));
  const sd = d.volatilidad / Math.sqrt(d.cripto ? 365 : 252);
  const camino: number[] = [0];
  for (let i = 1; i < n; i++) camino.push((camino[i - 1] ?? 0) + sd * normal(r));

  // Correccion en log por tramos para pasar exactamente por cada ancla.
  const anclas = d.anclas
    .map(([atras, valor]) => {
      if (typeof atras === "string") {
        const i = dias.findIndex((f) => f >= atras);
        return [i < 0 ? n - 1 : i, valor] as const;
      }
      return [atras < 0 ? 0 : n - 1 - atras, valor] as const;
    })
    .filter(([i]) => i >= 0 && i < n)
    .sort((a, b) => a[0] - b[0]);
  const correccion = (i: number): number => {
    const primera = anclas[0];
    const ultima = anclas[anclas.length - 1];
    if (!primera || !ultima) return 0;
    const err = (k: number, v: number) => Math.log(v) - (camino[k] ?? 0);
    if (i <= primera[0]) return err(primera[0], primera[1]);
    if (i >= ultima[0]) return err(ultima[0], ultima[1]);
    for (let a = 0; a < anclas.length - 1; a++) {
      const [i0, v0] = anclas[a] ?? [0, 1];
      const [i1, v1] = anclas[a + 1] ?? [0, 1];
      if (i >= i0 && i <= i1) {
        const f = i1 === i0 ? 0 : (i - i0) / (i1 - i0);
        return err(i0, v0) * (1 - f) + err(i1, v1) * f;
      }
    }
    return 0;
  };
  const cierres = camino.map((c, i) => Math.round(Math.exp(c + correccion(i)) * 100) / 100);
  const generada = { def: d, fechas: dias, cierres };
  cache.set(d.id, generada);
  return generada;
}
