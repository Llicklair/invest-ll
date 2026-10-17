/**
 * RESPALDO. Desde el contrato v2.1 la API trae `nombre` y `moneda` en rendimiento, posiciones,
 * ordenes y movimientos, y eso es lo que se ensena. Esto solo cubre lo que todavia llega con el
 * simbolo a secas (las cotizaciones al momento, los frenos, los activos de `GET /api/estado`).
 * Si un simbolo no esta, se ensena tal cual: mejor el simbolo que un nombre inventado.
 */
const NOMBRES: Record<string, string> = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  SOL: "Solana",
  BNB: "BNB",
  XRP: "XRP",
  ADA: "Cardano",
  DOGE: "Dogecoin",
  USDT: "Dólares digitales (USDT)",
  SPY: "Bolsa de EE.UU.",
  QQQ: "Tecnológicas de EE.UU. (Nasdaq 100)",
  IEF: "Bonos de EE.UU. a 7-10 años",
  TLT: "Bonos de EE.UU. a largo plazo",
  SHY: "Bonos de EE.UU. a corto plazo",
  GLD: "Oro",
  EEM: "Bolsa de países emergentes",
  EFA: "Bolsa de países desarrollados",
  VNQ: "Inmobiliario de EE.UU.",
  DBC: "Materias primas",
  XLE: "Energía de EE.UU.",
  XLF: "Bancos de EE.UU.",
  XLK: "Tecnología de EE.UU.",
  XLV: "Salud de EE.UU.",
  XLU: "Eléctricas de EE.UU.",
  XLP: "Consumo básico de EE.UU.",
  AAPL: "Apple",
  MSFT: "Microsoft",
  NVDA: "Nvidia",
  "IBE.MC": "Iberdrola",
  "SAN.MC": "Banco Santander",
  "BBVA.MC": "BBVA",
  "ITX.MC": "Inditex",
  "TEF.MC": "Telefónica",
};

/** La moneda base de un par ("BTC/USDT" -> "BTC") o el simbolo tal cual. */
export function base(simbolo: string): string {
  return simbolo.split("/")[0]?.trim().toUpperCase() ?? simbolo;
}

export function nombreLlano(simbolo: string, porDefecto?: string | null): string {
  const s = simbolo.trim().toUpperCase();
  return NOMBRES[s] ?? NOMBRES[base(s)] ?? (porDefecto && porDefecto !== "—" ? porDefecto : simbolo);
}

/** Lo que se tiene, en llano: "0,012 BTC" para cripto, "10 participaciones" para fondos. */
export function unidad(simbolo: string): string {
  return simbolo.includes("/") ? base(simbolo) : "participaciones";
}

/**
 * La moneda del precio cuando la API no la dice (activos de `GET /api/estado`): la del par en
 * cripto ("BTC/USDT" -> USDT), euros en las bolsas europeas y dolares en las de EE.UU.
 */
export function monedaSupuesta(simbolo: string): string {
  const s = simbolo.trim().toUpperCase();
  if (s.includes("/")) return s.split("/")[1] ?? "USDT";
  if (/\.(MC|PA|DE|AS|MI|LS|BR)$/.test(s)) return "EUR";
  if (s.endsWith(".SW")) return "CHF";
  if (s.endsWith(".L")) return "GBP";
  return "USD";
}

/**
 * El nombre de un exchange por su id ("binance" -> "Binance"). `ResumenBot.exchange` trae solo el
 * id; la lista buena es `GET /api/conexiones/disponibles`, y esto es su respaldo para las tarjetas.
 */
const EXCHANGES: Record<string, string> = {
  binance: "Binance",
  hyperliquid: "Hyperliquid",
  bybit: "Bybit",
  okx: "OKX",
  kraken: "Kraken",
  coinbase: "Coinbase",
};

export function nombreExchange(id: string | null | undefined): string {
  if (!id) return "";
  return EXCHANGES[id] ?? id.charAt(0).toUpperCase() + id.slice(1);
}

/** "en dólares (USD)", "en euros", "en dólares digitales (USDT)". */
export function enLaMoneda(moneda: string): string {
  const m = moneda.toUpperCase();
  if (m === "EUR") return "en euros";
  if (m === "USD") return "en dólares (USD)";
  if (m === "USDT" || m === "USDC") return `en dólares digitales (${m})`;
  return `en ${m}`;
}
