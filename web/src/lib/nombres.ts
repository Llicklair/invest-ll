/**
 * Nombres llanos de los activos ("Bitcoin", "Bolsa de EE.UU.", "Oro") para las rutas que solo
 * devuelven el simbolo (`GET /api/cartera`, `GET /api/ordenes`, el mercado). Las rutas v2 ya
 * traen el nombre llano; esto es el puente para las de antes. Si un simbolo no esta, se ensena
 * tal cual: mejor el simbolo que un nombre inventado.
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
