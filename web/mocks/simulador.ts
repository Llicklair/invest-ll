/**
 * La API de mentira para `npm run dev:mock` (NEXT_PUBLIC_MOCK=1). Responde a las mismas rutas,
 * con los mismos codigos (409 con pausa, 403 sin modo que envie, 404 al desarmar lo que no
 * existe, 422 con `detail`) y cuerpos tipados con el contrato: si `web/openapi.json` cambia y
 * estos ejemplos dejan de cumplirlo, `tsc` falla.
 *
 * Escenarios, con `?escenario=` en la URL (se recuerda en la pestana del navegador):
 *   simulacion (por defecto) · pruebas · real · vacio (cartera, seguimiento y estudio vacios)
 *   · pausa (pausa de entradas activa) · modo-roto (INVEST_LL_MODE mal puesto: /estado da 422)
 */
import type { components } from "@/api/esquema";
import { compararDecimal, leerDecimal } from "@/lib/decimal";

import { correlacion, dinero, informe, media, rendimientos, simular } from "./calculo";
import { DEFINICIONES, serie, type SerieGenerada } from "./series";

type S = components["schemas"];

const ESCENARIOS = ["simulacion", "pruebas", "real", "vacio", "pausa", "modo-roto"] as const;
type Escenario = (typeof ESCENARIOS)[number];

function esEscenario(v: string): v is Escenario {
  return (ESCENARIOS as readonly string[]).includes(v);
}

function escenario(): Escenario {
  try {
    const pedido = new URLSearchParams(window.location.search).get("escenario");
    if (pedido && esEscenario(pedido)) window.sessionStorage.setItem("invest-ll.mock.escenario", pedido);
    const guardado = window.sessionStorage.getItem("invest-ll.mock.escenario") ?? "simulacion";
    return esEscenario(guardado) ? guardado : "simulacion";
  } catch {
    return "simulacion";
  }
}

const RESERVA_DESDE = "2025-01-01";
const RESERVA =
  "Hay datos reservados desde 2025-01-01: los backtests se recortan ahi para que ese tramo siga sirviendo como validacion. Las cotizaciones y el rendimiento por periodo si usan el historico completo. Motivo: validacion fuera de muestra de las estrategias de rotacion";

const NADA_QUE_CONTAR =
  "Ninguna regla ha saltado.\n  Eso no significa que todo vaya bien: significa que nada ha cruzado un umbral de los que\n  se miran aqui. No se vigila la solvencia de las empresas, ni las noticias, ni tu\n  situacion personal.";

const ADVERTENCIA_CONTAMINACION =
  "[!] Sobre el resultado del LLM: el modelo fue entrenado con datos que incluyen lo que paso\n    despues del periodo simulado. Eso no se puede eliminar, solo acotar -- aqui se le ocultan\n    fechas y nombres, pero un modelo que reconozca un patron sabe en que epoca esta.\n    Un buen resultado del LLM sobre el pasado NO es evidencia de que funcione hacia adelante.\n    La unica prueba limpia es registrar lo que estima y comparar con lo que pase despues.\n";

// -- Estado mutable de la sesion de ejemplo ----------------------------------------------------

interface Mundo {
  escenario: Escenario;
  pausa: string | null;
  triggers: S["TriggerArmado"][];
  siguienteTrigger: number;
  abiertasExtra: S["PosicionAbierta"][];
  ordenes: S["FilaOrden"][];
  descargados: Set<string>;
  chats: Map<string, S["MensajeChat"][]>;
  movimientos: number;
}

let mundo: Mundo | null = null;

function elMundo(): Mundo {
  const e = escenario();
  if (mundo && mundo.escenario === e) return mundo;
  const conDatos = e !== "vacio";
  mundo = {
    escenario: e,
    pausa: e === "pausa" ? "caida brusca de BTC: revisar el plan antes de seguir (2026-10-16 08:12 UTC)" : null,
    triggers: conDatos
      ? [
          trigger("t1", "GLD", "drop-from-peak", "0.15", "2026-09-02T10:00:00Z"),
          trigger("t2", "BTC/USDT", "loss-from-entry", "0.2", "2026-09-20T18:30:00Z"),
          trigger("t3", "IBE.MC", "drop-from-peak", "0.1", "2026-10-01T07:45:00Z"),
        ]
      : [],
    siguienteTrigger: 4,
    abiertasExtra: [],
    ordenes: conDatos ? ordenesIniciales(e) : [],
    descargados: new Set(DEFINICIONES.map((d) => d.simbolo)),
    chats: new Map(),
    movimientos: 0,
  };
  return mundo;
}

function trigger(id: string, symbol: string, regla: string, umbral: string, armado: string): S["TriggerArmado"] {
  const pct = String(Number(umbral) * 100);
  const condicion =
    regla === "loss-from-entry"
      ? `pierde mas del ${pct}% desde tu entrada (coste medio con comisiones)`
      : `cae mas del ${pct}% desde el cierre maximo de los datos descargados`;
  return { trigger_id: id, symbol, regla, umbral, armado, descripcion: `${symbol}: proponer la venta si ${condicion}` };
}

function ordenesIniciales(e: Escenario): S["FilaOrden"][] {
  const filas: S["FilaOrden"][] = [
    {
      cuando: "2026-10-15T16:40:10Z",
      modo: "pruebas",
      activo: "SOL/USDT",
      lado: "sell",
      pedida: "1",
      ejecutada: "0",
      precio: null,
      comision: null,
      estado: "rejected",
      referencia: "",
    },
    {
      cuando: "2026-10-14T09:15:02Z",
      modo: "pruebas",
      activo: "ETH/USDT",
      lado: "buy",
      pedida: "0.05",
      ejecutada: "0.032",
      precio: "2431.10",
      comision: "0.0778",
      estado: "partial",
      referencia: "testnet-5512460",
    },
    {
      cuando: "2026-10-14T09:12:33Z",
      modo: "pruebas",
      activo: "BTC/USDT",
      lado: "buy",
      pedida: "0.001",
      ejecutada: "0.001",
      precio: "82011.50",
      comision: "0.08201150",
      estado: "filled",
      referencia: "testnet-5512399",
    },
  ];
  if (e === "real") {
    filas.unshift({
      cuando: "2026-10-16T11:02:47Z",
      modo: "REAL",
      activo: "BTC/USDT",
      lado: "buy",
      pedida: "0.0005",
      ejecutada: "0.0005",
      precio: "81920.04",
      comision: null,
      estado: "filled",
      referencia: "8829301144",
    });
  }
  return filas;
}

function modo(e: Escenario): S["Modo"] {
  if (e === "real") return { nombre: "REAL", envia_ordenes: true, es_real: true };
  if (e === "pruebas") return { nombre: "pruebas", envia_ordenes: true, es_real: false };
  return { nombre: "simulacion", envia_ordenes: false, es_real: false };
}

// -- Utilidades de respuesta ----------------------------------------------------------------------

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

/** Los errores del dominio: `{"detail": "texto"}` (el modelo `Error` de schemas.py). */
function fallo(status: number, detail: string): Response {
  return json({ detail }, status);
}

function sinCuerpo(): Response {
  return new Response(null, { status: 204 });
}

function esperar(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

type Objeto = Record<string, unknown>;

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

function numeroDe(o: Objeto, campo: string, porDefecto: number): number {
  const v = o[campo];
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : porDefecto;
}

function listaTextos(o: Objeto, campo: string): string[] {
  const v = o[campo];
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function costeDe(o: Objeto): number | Response {
  const c = texto(o, "comision");
  const s = texto(o, "slippage");
  if (c === null || s === null) {
    return json(
      {
        detail: [
          ...(c === null ? [{ loc: ["body", "comision"], msg: "Field required", type: "missing" }] : []),
          ...(s === null ? [{ loc: ["body", "slippage"], msg: "Field required", type: "missing" }] : []),
        ],
      },
      422,
    );
  }
  return Number(c) + Number(s);
}

const ultimo = <T,>(xs: readonly T[]): T | undefined => xs[xs.length - 1];

function recortarReserva(s: SerieGenerada): { fechas: string[]; cierres: number[] } {
  const fin = s.fechas.findIndex((f) => f >= RESERVA_DESDE);
  if (fin < 0) return { fechas: s.fechas, cierres: s.cierres };
  return { fechas: s.fechas.slice(0, fin), cierres: s.cierres.slice(0, fin) };
}

function variacion(c: readonly number[], k: number): number | null {
  if (c.length <= k) return null;
  const antes = c[c.length - 1 - k];
  const ahora = ultimo(c);
  if (!antes || ahora === undefined) return null;
  return Math.round((ahora / antes - 1) * 1000) / 10;
}

// -- Rutas ---------------------------------------------------------------------------------------

function estado(m: Mundo): S["Estado"] {
  return {
    modo: modo(m.escenario),
    reserva: m.escenario === "vacio" ? null : RESERVA,
    pausa: m.pausa,
    activos: DEFINICIONES.map((d) => ({
      id: d.id,
      symbol: d.simbolo,
      provider: d.proveedor,
      interval: "DAY_1",
      is_crypto: d.cripto,
      label: `${d.simbolo} (DAY_1)`,
      desde: d.desde,
      hasta: d.hasta,
    })),
  };
}

function rendimiento(): S["Rendimiento"] {
  const filas = DEFINICIONES.map((d): [boolean, S["FilaRendimiento"]] => {
    const s = serie(d.simbolo);
    const c = s?.cierres ?? [];
    const f = s?.fechas ?? [];
    const ult = ultimo(c) ?? 0;
    const maximo = Math.max(...c);
    const anho = (ultimo(f) ?? "").slice(0, 4);
    let ytd: number | null = null;
    for (let i = f.length - 1; i >= 0; i--) {
      if ((f[i] ?? "").slice(0, 4) < anho) {
        ytd = Math.round((ult / (c[i] ?? ult) - 1) * 1000) / 10;
        break;
      }
    }
    return [
      d.cripto,
      {
        activo: d.simbolo,
        que_es: d.queEs,
        ultimo: ult,
        var_1d: variacion(c, 1),
        var_1s: variacion(c, 5),
        var_1m: variacion(c, 21),
        var_3m: variacion(c, 63),
        ytd,
        var_1a: variacion(c, 252),
        var_5a: variacion(c, 1260),
        desde_maximo: maximo ? Math.round((ult / maximo - 1) * 1000) / 10 : null,
        sparkline: c.slice(-63),
        desde: f[0] ?? d.desde,
        datos_hasta: ultimo(f) ?? d.hasta,
      },
    ];
  });
  return { bolsa: filas.filter(([c]) => !c).map(([, f]) => f), cripto: filas.filter(([c]) => c).map(([, f]) => f) };
}

const SESIONES: Record<string, number | undefined> = { "3m": 63, "1a": 252, "5a": 1260, todo: undefined };
const VENTANAS: Record<string, number> = { "1 mes": 21, "3 meses": 63, "1 año": 252, "5 años": 1260 };

function serieRuta(url: URL): Response {
  const simbolo = url.searchParams.get("symbol") ?? "";
  const tramo = url.searchParams.get("tramo") ?? "1a";
  if (!(tramo in SESIONES)) {
    return json({ detail: [{ loc: ["query", "tramo"], msg: "Input should be '3m', '1a', '5a' or 'todo'", type: "literal_error" }] }, 422);
  }
  const s = serie(simbolo);
  if (!s) return fallo(404, `No hay historico descargado de ${simbolo}`);
  const k = SESIONES[tramo];
  const desde = k ? Math.max(0, s.fechas.length - k) : 0;
  const cuerpoSerie: S["Serie"] = {
    symbol: s.def.simbolo,
    tramo: tramo as S["Serie"]["tramo"],
    puntos: s.fechas.slice(desde).map((f, i) => ({ fecha: `${f}T00:00:00Z`, valor: s.cierres[desde + i] ?? 0 })),
    sesiones: s.fechas.length - desde,
    hasta: ultimo(s.fechas) ?? s.def.hasta,
  };
  return json(cuerpoSerie);
}

function comparacion(url: URL): Response {
  const ids = url.searchParams.getAll("activos");
  if (!ids.length) {
    return json({ detail: [{ loc: ["query", "activos"], msg: "Field required", type: "missing" }] }, 422);
  }
  const ventana = url.searchParams.get("ventana");
  const series = ids.map((id) => serie(id)).filter((s): s is SerieGenerada => s !== null);
  const comun = series.reduce((max, s) => ((s.fechas[0] ?? "") > max ? (s.fechas[0] ?? "") : max), "");
  const puntos: S["PuntoComparado"][] = [];
  for (const s of series) {
    let desde = 0;
    if (ventana && VENTANAS[ventana]) desde = Math.max(0, s.fechas.length - (VENTANAS[ventana] ?? 0));
    else desde = Math.max(0, s.fechas.findIndex((f) => f >= comun));
    const base = s.cierres[desde] ?? 1;
    for (let i = desde; i < s.fechas.length; i++) {
      puntos.push({
        fecha: `${s.fechas[i]}T00:00:00Z`,
        activo: s.def.simbolo,
        valor: Math.round(((s.cierres[i] ?? 0) / base) * 10000) / 100,
      });
    }
  }
  const c: S["Comparacion"] = { puntos };
  return json(c);
}

function datos(): S["DatosDescargados"] {
  const filas = DEFINICIONES.map((d): S["FilaDatos"] => {
    const s = serie(d.simbolo);
    const c = s?.cierres ?? [];
    const ult = ultimo(c) ?? 0;
    const previo = c[c.length - 2] ?? ult;
    return {
      activo: d.simbolo,
      ultimo_cierre: ult,
      variacion: previo ? ult / previo - 1 : 0,
      fecha: ultimo(s?.fechas ?? []) ?? d.hasta,
      velas: c.length,
      descargado: d.descargado,
    };
  });
  return { filas, desfasados: DEFINICIONES.filter((d) => d.hasta < "2026-10-01").map((d) => d.simbolo) };
}

const BOLSA_CATALOGO: [string, number][] = [
  ["NVDA", 211.4], ["AAPL", 342.0], ["MSFT", 548.2], ["AMZN", 241.8], ["TSLA", 402.5], ["META", 812.3],
  ["GOOGL", 268.9], ["AMD", 233.1], ["AVGO", 381.7], ["JPM", 318.4], ["V", 362.2], ["BRK-B", 512.6],
  ["SPY", 771.79], ["QQQ", 728.0], ["GLD", 382.71], ["TLT", 79.97], ["XLE", 66.56], ["XLF", 55.27],
  ["XLK", 189.19], ["XLV", 177.19], ["XLU", 43.12], ["XLP", 86.68], ["SAN.MC", 9.84], ["BBVA.MC", 17.62],
  ["ITX.MC", 51.3], ["IBE.MC", 18.95], ["TEF.MC", 4.61], ["REP.MC", 15.12], ["CABK.MC", 9.07], ["AENA.MC", 26.4],
  ["ASML", 1102.5], ["SAP", 268.3], ["NESN.SW", 84.1], ["MC.PA", 612.8],
];

const CRIPTO_CATALOGO: [string, number][] = [
  ["BTC/USDT", 82245.93], ["ETH/USDT", 2442.08], ["SOL/USDT", 142.3], ["BNB/USDT", 1044.2], ["XRP/USDT", 2.41],
  ["DOGE/USDT", 0.2134], ["ADA/USDT", 0.6612], ["TRX/USDT", 0.3381], ["LINK/USDT", 17.42], ["AVAX/USDT", 21.84],
  ["SUI/USDT", 2.874], ["TON/USDT", 2.403], ["DOT/USDT", 3.121], ["LTC/USDT", 93.55], ["BCH/USDT", 512.4],
  ["NEAR/USDT", 2.315], ["APT/USDT", 3.906], ["UNI/USDT", 6.982], ["PEPE/USDT", 0.00000731], ["SHIB/USDT", 0.00001042],
  ["ARB/USDT", 0.3388], ["OP/USDT", 0.4917], ["FET/USDT", 0.5123], ["INJ/USDT", 11.87], ["AAVE/USDT", 228.6],
  ["LUNA/USDT", 0.1418], ["WLD/USDT", 0.8705], ["ENA/USDT", 0.4519],
];

function semillaDe(texto: string): number {
  let h = 7;
  for (const c of texto) h = (h * 31 + c.charCodeAt(0)) % 100_003;
  return h / 100_003;
}

function cotizaciones(m: Mundo): S["Cotizaciones"] {
  const fila = ([sim, precio]: [string, number], i: number, cripto: boolean): S["Cotizacion"] => {
    const r = semillaDe(sim);
    const sinDatos = cripto && sim === "LUNA/USDT";
    return {
      activo: sim,
      precio,
      var_24h: sinDatos ? null : Math.round((r - 0.5) * (cripto ? 1200 : 500)) / 100,
      volumen_24h_m: sinDatos ? null : Math.round((cripto ? 4000 : 900) / (i + 1) * (0.6 + r) * 10) / 10,
      descargado: m.descargados.has(sim),
    };
  };
  const ordenar = (xs: S["Cotizacion"][]) => xs.sort((a, b) => (b.volumen_24h_m ?? -1) - (a.volumen_24h_m ?? -1));
  return {
    at: new Date().toISOString(),
    bolsa: ordenar(BOLSA_CATALOGO.map((x, i) => fila(x, i, false))),
    cripto: ordenar(CRIPTO_CATALOGO.map((x, i) => fila(x, i, true))),
    errores: ["Bolsa: yfinance no devolvio precio para 2 valores (GRF.MC, SAB.MC); se omiten."],
  };
}

function cartera(m: Mundo): S["Cartera"] {
  if (m.escenario === "vacio" && m.abiertasExtra.length === 0) {
    return {
      vacia: true,
      error: null,
      avisos: [],
      abiertas: [],
      retiradas: [],
      invertido_abiertas: "0",
      valor_total: "0",
      efectivo: "0",
      realizado_total: "0",
    };
  }
  const base: S["PosicionAbierta"][] =
    m.escenario === "vacio"
      ? []
      : [
          {
            activo: "GLD",
            cantidad: "10",
            coste_medio: "240.70",
            invertido: "2407.00",
            abierta: "2025-03-14T00:00:00Z",
            precio: "382.71",
            precio_fecha: "2026-10-15",
            valor: "3827.10",
            pnl_no_realizado: "1420.10",
          },
          {
            activo: "BTC/USDT",
            cantidad: "0.025",
            coste_medio: "61261.20",
            invertido: "1531.53",
            abierta: "2026-02-03T00:00:00Z",
            precio: "82245.93",
            precio_fecha: "2026-10-15",
            valor: "2056.14825",
            pnl_no_realizado: "524.61825",
          },
          {
            activo: "IBE.MC",
            cantidad: "120",
            coste_medio: "14.3367",
            invertido: "1720.40",
            abierta: "2026-06-22T00:00:00Z",
            precio: null,
            precio_fecha: null,
            valor: null,
            pnl_no_realizado: null,
          },
        ];
  const abiertas = [...base, ...m.abiertasExtra];
  return {
    vacia: false,
    error: null,
    avisos:
      m.escenario === "vacio"
        ? []
        : [
            "IBE.MC no tiene historico descargado: su valor no se puede calcular y el total queda incompleto. Descargalo con invest-ll-fetch IBE.MC --market equity.",
          ],
    abiertas,
    retiradas:
      m.escenario === "vacio"
        ? []
        : [
            {
              activo: "TLT",
              abierta: "2024-05-02",
              retirada: "2025-09-30",
              dias: 516,
              invertido: "1803.20",
              recuperado: "1612.40",
              pnl_realizado: "-190.80",
            },
            {
              activo: "XLF",
              abierta: "2025-01-10",
              retirada: "2025-08-01",
              dias: 203,
              invertido: "1500.00",
              recuperado: "1641.25",
              pnl_realizado: "141.25",
            },
          ],
    invertido_abiertas: m.escenario === "vacio" ? "0" : "5658.93",
    valor_total: abiertas.some((a) => a.valor === null) ? null : "5883.24825",
    efectivo: m.escenario === "vacio" ? "0" : "1832.47",
    realizado_total: m.escenario === "vacio" ? "0" : "-49.55",
  };
}

function motivoNoEnviar(m: Mundo, cantidad: string, escrito: string): string | null {
  if (!modo(m.escenario).envia_ordenes) {
    return "Modo simulacion: no se envia nada al exterior. Para operar de verdad, arranca el panel con INVEST_LL_MODE=testnet (o =real) y sus credenciales.";
  }
  if (leerDecimal(cantidad) === null || compararDecimal(cantidad, "0") <= 0) return "La cantidad tiene que ser positiva.";
  if (leerDecimal(escrito) === null) return `Escribe la cantidad exacta (${cantidad}) para confirmar.`;
  if (compararDecimal(escrito, cantidad) !== 0) return `Lo escrito (${escrito.trim()}) no coincide con la cantidad (${cantidad}).`;
  return null;
}

function propuesta(m: Mundo, o: Objeto): Response {
  if (m.pausa) {
    return fallo(409, `Pausa activa: ${m.pausa}. No se proponen entradas nuevas; las posiciones abiertas no se tocan. Retirala con invest-ll-triggers resume.`);
  }
  const coste = costeDe(o);
  if (coste instanceof Response) return coste;
  const ids = listaTextos(o, "activos");
  const importe = numeroDe(o, "importe", 0);
  const frecuencia = texto(o, "frecuencia") ?? "";
  if (!ids.length) return json({ detail: [{ loc: ["body", "activos"], msg: "List should have at least 1 item after validation, not 0", type: "too_short" }] }, 422);
  if (!["monthly", "quarterly", "weekly"].includes(frecuencia)) return fallo(422, `frecuencia desconocida: '${frecuencia}' (usa monthly, quarterly o weekly)`);
  const series = ids.map((id) => serie(id)).filter((s): s is SerieGenerada => s !== null);
  const parte = importe / series.length;
  const compras: S["CompraPropuesta-Output"][] = series.map((s) => {
    const precio = ultimo(s.cierres);
    return {
      symbol: s.def.simbolo,
      importe: parte.toFixed(2),
      precio: precio !== undefined ? precio.toFixed(2) : null,
      fecha: ultimo(s.fechas) ?? null,
      cantidad: precio ? (parte / precio).toFixed(4) : null,
    };
  });
  const sesiones = { monthly: 21, quarterly: 63, weekly: 5 }[frecuencia] ?? 21;
  const lineas = [
    "PROPUESTA DE CARTERA  (simulacion sobre el pasado: no mueve dinero)",
    "",
    `  Aportacion          ${importe.toFixed(2)} cada ${sesiones} sesiones (${frecuencia})`,
    `  Costes              comision ${(Number(texto(o, "comision")) * 100).toFixed(2)}% + slippage ${(Number(texto(o, "slippage")) * 100).toFixed(3)}%`,
    "",
    "  Reparto de cada aportacion",
    ...compras.map((c) => `    ${c.symbol.padEnd(10)} ${Number(c.importe).toFixed(2).padStart(10)}`),
    "",
    "  Simulado de 2015-01-02 a 2024-12-31 (datos reservados desde 2025-01-01)",
    `    aportado            ${(importe * 120).toFixed(2)}`,
    `    valor final         ${(importe * 120 * 1.42).toFixed(2)}`,
    `    peor caida          ${(-importe * 120 * 0.14).toFixed(2)}  (2022-10-14)`,
    "",
    "  [!] Una simulacion sobre el pasado no es una prevision. Reparte por igual entre",
    "      los candidatos: no elige ganadores, que es justo lo que no se sabe hacer.",
  ];
  const p: S["Propuesta"] = {
    texto: lineas.join("\n"),
    compras,
    comandos: compras.map((c) =>
      c.cantidad
        ? `uv run invest-ll-execute --symbol ${c.symbol} --side buy --quantity ${c.cantidad}`
        : `# ${c.symbol}: sin precio descargado, calcula la cantidad a mano`,
    ),
  };
  return json(p);
}

function unActivo(o: Objeto): Response {
  const coste = costeDe(o);
  if (coste instanceof Response) return coste;
  const s = serie(texto(o, "activo") ?? "");
  if (!s) return fallo(404, `No hay ningun activo descargado con id ${texto(o, "activo") ?? "(nada)"}`);
  const { fechas, cierres } = recortarReserva(s);
  const estrategia = texto(o, "estrategia") ?? "cruce-medias";
  const corta = numeroDe(o, "corta", 10);
  const larga = numeroDe(o, "larga", 30);
  if (estrategia === "cruce-medias" && corta >= larga) {
    return fallo(422, `la media corta (${corta}) tiene que ser menor que la larga (${larga})`);
  }
  const periodos = numeroDe(o, "periodos", 50);
  const margen = numeroDe(o, "margen", 0);
  const lookback = numeroDe(o, "lookback", 20);
  const capital = numeroDe(o, "capital", 10000);
  const fraccion = numeroDe(o, "fraccion", 1);
  const dentro = (i: number, invertido: boolean): boolean => {
    const c = cierres[i] ?? 0;
    if (estrategia === "precio-vs-media") {
      const mm = media(cierres, i, periodos);
      if (mm === null) return false;
      return invertido ? c > mm * (1 - margen) : c > mm;
    }
    if (estrategia === "ruptura-maximos") {
      if (i < lookback) return false;
      const ventana = cierres.slice(i - lookback, i);
      return invertido ? c > Math.min(...ventana) : c > Math.max(...ventana);
    }
    const a = media(cierres, i, corta);
    const b = media(cierres, i, larga);
    return a !== null && b !== null && a > b;
  };
  const sim = simular(fechas, cierres, dentro, capital, fraccion, coste);
  return json(informe(sim, fechas, cierres, capital, coste) satisfies S["Informe"]);
}

function universo(ids: string[]): { simbolos: string[]; fechas: string[]; cierres: number[][] } {
  const series = ids.map((id) => serie(id)).filter((s): s is SerieGenerada => s !== null);
  const comunes = series
    .map((s) => new Set(recortarReserva(s).fechas))
    .reduce<Set<string> | null>((acc, set) => (acc === null ? set : new Set([...acc].filter((f) => set.has(f)))), null);
  const fechas = [...(comunes ?? new Set<string>())].sort();
  const cierres = series.map((s) => {
    const indice = new Map(s.fechas.map((f, i) => [f, s.cierres[i] ?? 0]));
    return fechas.map((f) => indice.get(f) ?? 0);
  });
  return { simbolos: series.map((s) => s.def.simbolo), fechas, cierres };
}

function analisis(o: Objeto): Response {
  const ids = listaTextos(o, "activos");
  if (ids.length < 2) return json({ detail: [{ loc: ["body", "activos"], msg: "List should have at least 2 items after validation, not 1", type: "too_short" }] }, 422);
  const u = universo(ids);
  if (u.fechas.length < 30) return fallo(422, `Solo ${u.fechas.length} fechas comunes entre ${u.simbolos.join(", ")}: no hay solape suficiente para formar una cartera.`);
  const r = u.cierres.map(rendimientos);
  const pares: S["Par"][] = [];
  for (let i = 0; i < r.length; i++)
    for (let j = i + 1; j < r.length; j++)
      pares.push({ par: `${u.simbolos[i]} / ${u.simbolos[j]}`, correlacion: Math.round(correlacion(r[i] ?? [], r[j] ?? []) * 100) / 100 });
  const media_ = pares.reduce((s, p) => s + p.correlacion, 0) / (pares.length || 1);
  const n = u.simbolos.length;
  const efectivos = n / (1 + (n - 1) * Math.max(0, media_));
  const diversificada = efectivos >= n * 0.6;
  const a: S["AnalisisCartera"] = {
    fechas_comunes: u.fechas.length,
    desde: u.fechas[0] ?? "",
    hasta: ultimo(u.fechas) ?? "",
    activos: n,
    activos_efectivos: efectivos,
    correlacion_media: media_,
    diversificada,
    aviso: diversificada
      ? null
      : `Tus ${n} activos equivalen a ${efectivos.toFixed(1)} independientes. Con una correlacion media de ${media_.toFixed(2)} se mueven casi a la vez: tener varios no te protege de una caida general.`,
    pares,
  };
  return json(a);
}

function aportaciones(o: Objeto): Response {
  const coste = costeDe(o);
  if (coste instanceof Response) return coste;
  const u = universo(listaTextos(o, "activos"));
  const aportacion = numeroDe(o, "aportacion", 500);
  const cada = numeroDe(o, "cada", 21);
  const unidades = u.simbolos.map(() => 0);
  let aportado = 0;
  let costes = 0;
  for (let i = 0; i < u.fechas.length; i += cada) {
    aportado += aportacion;
    u.cierres.forEach((c, k) => {
      const parte = aportacion / u.simbolos.length;
      costes += parte * coste;
      unidades[k] = (unidades[k] ?? 0) + (parte * (1 - coste)) / (c[i] ?? 1);
    });
  }
  const valorFinal = u.cierres.reduce((s, c, k) => s + (unidades[k] ?? 0) * (ultimo(c) ?? 0), 0);
  const deGolpe = u.cierres.reduce(
    (s, c) => s + ((aportado / u.simbolos.length) * (1 - coste) * (ultimo(c) ?? 0)) / (c[0] ?? 1),
    0,
  );
  const ganancia = valorFinal - aportado;
  const lineas = [
    "APORTACIONES PERIODICAS  (simulacion sobre el pasado)",
    "",
    `  Activos             ${u.simbolos.join(", ")}`,
    `  Periodo             ${u.fechas[0]} a ${ultimo(u.fechas)} (${u.fechas.length} sesiones comunes)`,
    `  Aportacion          ${aportacion.toFixed(2)} cada ${cada} sesiones, repartida por igual`,
    "",
    `  Aportado            ${aportado.toFixed(2)}`,
    `  Valor final         ${valorFinal.toFixed(2)}`,
    `  Ganancia            ${ganancia.toFixed(2)}  (${((ganancia / aportado) * 100).toFixed(1)}% sobre lo aportado)`,
    `  Costes              ${costes.toFixed(2)}`,
    "",
    `  Todo de golpe al principio habria dado ${deGolpe.toFixed(2)}.`,
  ];
  const r: S["InformeAportaciones"] = {
    aportado: dinero(aportado),
    valor_final: dinero(valorFinal),
    ganancia: dinero(ganancia),
    rentabilidad: ganancia / aportado,
    costes: dinero(costes),
    bate_a_todo_de_golpe: valorFinal > deGolpe,
    valor_todo_de_golpe: dinero(deGolpe),
    texto: lineas.join("\n"),
  };
  return json(r);
}

function rotacion(o: Objeto): Response {
  const coste = costeDe(o);
  if (coste instanceof Response) return coste;
  const u = universo(listaTextos(o, "activos"));
  const lookback = numeroDe(o, "lookback", 60);
  const capital = numeroDe(o, "capital", 10000);
  // Rotacion: cada 21 sesiones, todo al activo con mejor impulso. Se simula como una curva
  // compuesta por tramos sobre el indice del activo elegido.
  const indice: number[] = [1];
  let elegido = 0;
  let cambios = 0;
  for (let i = 1; i < u.fechas.length; i++) {
    if (i % 21 === 0 && i > lookback) {
      let mejor = elegido;
      let mejorR = -Infinity;
      u.cierres.forEach((c, k) => {
        const r = (c[i - 1] ?? 1) / (c[i - 1 - lookback] ?? 1) - 1;
        if (r > mejorR) {
          mejorR = r;
          mejor = k;
        }
      });
      if (mejor !== elegido) {
        cambios++;
        elegido = mejor;
      }
    }
    const c = u.cierres[elegido] ?? [];
    indice.push((indice[i - 1] ?? 1) * ((c[i] ?? 1) / (c[i - 1] ?? 1)));
  }
  const sim = simular(u.fechas, indice, (i) => i >= lookback, capital, 1, coste);
  sim.costes += cambios * capital * coste;
  const promedio = u.fechas.map((_, i) => u.cierres.reduce((s, c) => s + (c[i] ?? 0) / (c[0] ?? 1), 0) / u.cierres.length);
  const inf = informe(sim, u.fechas, promedio, capital, coste);
  return json({ ...inf, operaciones: inf.operaciones + cambios } satisfies S["Informe"]);
}

function llm(m: Mundo, o: Objeto): Response {
  const coste = costeDe(o);
  if (coste instanceof Response) return coste;
  if (m.escenario === "vacio") {
    const r: S["ComparacionLLM"] = {
      disponible: false,
      motivo: "No hay decisiones grabadas en decisions/llm-trimestral. Generalas con invest-ll-generate (gasta cuota; se hace una sola vez).",
      filas: [],
      ninguna_bate: false,
      advertencia: ADVERTENCIA_CONTAMINACION,
    };
    return json(r);
  }
  const r: S["ComparacionLLM"] = {
    disponible: true,
    motivo: null,
    filas: [
      { estrategia: "LLM (grabado)", resultado: "11204.18", drawdown: "-6930.02", operaciones: 61, costes: "448.91" },
      { estrategia: "momentum", resultado: "2890.12", drawdown: "-5873.40", operaciones: 423, costes: "3102.77" },
      { estrategia: "comprar y mantener", resultado: "37773.05", drawdown: "-9410.66", operaciones: 1, costes: "15.00" },
    ],
    ninguna_bate: true,
    advertencia: ADVERTENCIA_CONTAMINACION,
  };
  return json(r);
}

function alertas(url: URL): S["Alertas"] {
  const dias = Number(url.searchParams.get("dias") ?? "7");
  const caida = Number(url.searchParams.get("caida_pct") ?? "15") / 100;
  const hoy = Date.parse("2026-10-17T00:00:00Z");
  const lista: S["Alerta"][] = [];
  for (const d of DEFINICIONES) {
    const s = serie(d.simbolo);
    if (!s) continue;
    const ult = ultimo(s.cierres) ?? 0;
    let max = 0;
    let fechaMax = "";
    s.cierres.forEach((c, i) => {
      if (c > max) {
        max = c;
        fechaMax = s.fechas[i] ?? "";
      }
    });
    const desdeMax = ult / max - 1;
    if (desdeMax <= -caida) {
      lista.push({
        symbol: d.simbolo,
        nivel: "revisar",
        mensaje: `cae un ${(-desdeMax * 100).toFixed(1)}% desde su cierre maximo (${max.toFixed(2)} el ${fechaMax}); umbral ${Math.round(caida * 100)}%`,
      });
    }
    const sinDatos = Math.floor((hoy - Date.parse(`${ultimo(s.fechas)}T00:00:00Z`)) / 86_400_000);
    if (sinDatos > dias) {
      lista.push({
        symbol: d.simbolo,
        nivel: "revisar",
        mensaje: `lleva ${sinDatos} dias sin datos nuevos (ultimo cierre ${ultimo(s.fechas)}): lo que ves de el no es actual`,
      });
    }
  }
  if (lista.length) {
    lista.push({
      symbol: null,
      nivel: "informativo",
      mensaje: "Las alertas que dependen de tus posiciones (perdida desde tu entrada, desviacion del plan) no se han evaluado: no hay posiciones declaradas con --holding.",
    });
  }
  return { alertas: lista, nada_que_contar: lista.length ? null : NADA_QUE_CONTAR };
}

function comprobarTriggers(m: Mundo): S["ComprobacionTriggers"] {
  const disparados: S["Disparo"][] = [];
  const sinEvaluar: string[] = [];
  for (const t of m.triggers) {
    const s = serie(t.symbol);
    if (!s) {
      sinEvaluar.push(`${t.trigger_id} ${t.symbol}: sin historico descargado, no se puede medir`);
      continue;
    }
    const ult = ultimo(s.cierres) ?? 0;
    const umbral = Number(t.umbral);
    const medido =
      t.regla === "loss-from-entry"
        ? t.symbol === "BTC/USDT"
          ? ult / 61261.2 - 1
          : null
        : ult / Math.max(...s.cierres) - 1;
    if (medido === null) {
      sinEvaluar.push(`${t.trigger_id} ${t.symbol}: no hay posicion abierta en la cartera, no hay entrada con la que comparar`);
      continue;
    }
    if (medido <= -umbral) {
      const cantidad = t.symbol === "GLD" ? "10" : "0.025";
      disparados.push({
        trigger_id: t.trigger_id,
        symbol: t.symbol,
        medido: medido.toFixed(4),
        umbral: t.umbral,
        cantidad_propuesta: cantidad,
        precio: ult.toFixed(2),
        precio_fecha: ultimo(s.fechas) ?? "",
        comando: `uv run invest-ll-execute --symbol ${t.symbol} --side sell --quantity ${cantidad}`,
      });
    }
  }
  return { disparados, sin_evaluar: sinEvaluar, armados: m.triggers.length };
}

function seguimiento(m: Mundo): S["Seguimiento"] {
  if (m.escenario === "vacio") return { evaluadas: 0, pendientes: 0, sobreestimaciones: 0, tendencia: null, filas: [] };
  return {
    evaluadas: 6,
    pendientes: 2,
    sobreestimaciones: 5,
    tendencia: "sobreestima: 5 de 6 estimaciones quedaron por encima de lo que paso (error medio +412,30)",
    filas: [
      { emitida: "2026-04-01", estimado: "10850.00", real: "10212.40", error: "637.60" },
      { emitida: "2026-05-01", estimado: "10920.00", real: "10498.15", error: "421.85" },
      { emitida: "2026-06-01", estimado: "11010.00", real: "11105.32", error: "-95.32" },
      { emitida: "2026-07-01", estimado: "11240.00", real: "10790.08", error: "449.92" },
      { emitida: "2026-08-01", estimado: "11300.00", real: "10871.66", error: "428.34" },
      { emitida: "2026-09-01", estimado: "11450.00", real: "10818.60", error: "631.40" },
    ],
  };
}

function investigacion(m: Mundo, url: URL): S["Investigacion"] {
  const capital = Number(url.searchParams.get("capital") ?? "1000");
  if (m.escenario === "vacio") {
    return {
      disponible: false,
      motivo: "Sin datos todavía. Descárgalos con `uv run invest-ll-quant download` (unos 6 minutos).",
      ultimo_dato: null,
      dias_desfase: null,
      objetivo: [],
      prueba_adelante: [],
      estudio: null,
    };
  }
  const pesos: [string, number][] = [["BTC", 0.35], ["ETH", 0.162], ["SOL", 0.118], ["XRP", 0.081], ["BNB", 0.064], ["liquidez", 0.225]];
  return {
    disponible: true,
    motivo: null,
    ultimo_dato: "2026-10-12",
    dias_desfase: 5,
    objetivo: pesos.map(([moneda, peso]) => ({ moneda, peso, usdt: peso * capital })),
    prueba_adelante: [
      { clave: "preregistered", etiqueta: "Prerregistrada", registros: 12, desde: "2026-10-03", valor_final: 10234.5, mantener_btc: 10120.7, peor_caida: -0.041, nota: null },
      {
        clave: "filtered",
        etiqueta: "Segunda fase (filtro de mercado + banda)",
        registros: 1,
        desde: "2026-10-12",
        valor_final: null,
        mantener_btc: null,
        peor_caida: null,
        nota: "Primer registro el 2026-10-12: aún no hay días después para medir.",
      },
      {
        clave: "btc-trend",
        etiqueta: "Tendencia de BTC (BTC o liquidez)",
        registros: 0,
        desde: null,
        valor_final: null,
        mantener_btc: null,
        peor_caida: null,
        nota: "Todavía no hay registros. `uv run invest-ll-quant paper record` guarda la cartera de hoy; `scripts/paper-daily.ps1` lo hace cada día y lo deja en un commit con fecha.",
      },
    ],
    estudio: { ruta: "research/runs/2026-10-15-1830/report.html", generado: "2026-10-15T18:42:10Z" },
  };
}

const ESTUDIO_HTML = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Estudio (ejemplo)</title>
<style>body{font-family:system-ui,sans-serif;margin:24px;color:#0b0b0b;background:#fff;line-height:1.5}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px;text-align:right}th:first-child,td:first-child{text-align:left}
.aviso{background:#fdf3dc;border-left:4px solid #fab219;padding:8px}</style></head><body>
<h1>Estudio de cartera cripto (EJEMPLO, datos inventados)</h1>
<p class="aviso">Este HTML es una respuesta de ejemplo de <code>web/mocks/</code>. El de verdad lo genera <code>invest-ll-quant study</code>.</p>
<h2>Prerregistrada frente a mantener BTC (con comisiones)</h2>
<table><tr><th>configuracion</th><th>CAGR</th><th>peor caida</th><th>Sharpe</th></tr>
<tr><td>prerregistrada</td><td>31,2%</td><td>-41,8%</td><td>0,94</td></tr>
<tr><td>segunda fase</td><td>28,7%</td><td>-33,1%</td><td>0,97</td></tr>
<tr><td>mantener BTC</td><td>38,9%</td><td>-76,6%</td><td>0,81</td></tr></table>
<p>Lo que no se puede leer aqui: el periodo es corto, el universo cambia y la seleccion del ganador de una rejilla sobreestima siempre el resultado.</p>
</body></html>`;

function chat(m: Mundo, o: Objeto): Response {
  const pregunta = (texto(o, "pregunta") ?? "").trim();
  if (!pregunta) return json({ detail: [{ loc: ["body", "pregunta"], msg: "String should have at least 1 character", type: "string_too_short" }] }, 422);
  const pedida = texto(o, "sesion");
  if (pedida !== null && !m.chats.has(pedida)) return fallo(404, `No hay ninguna sesion de chat con id ${pedida}`);
  const sesion = pedida ?? `ejemplo-${Math.floor(Math.random() * 1e6)}`;
  const historial = m.chats.get(sesion) ?? [];
  const respuesta =
    "Con lo que veo (datos hasta el 2026-10-15): tu cartera tiene GLD, BTC/USDT e IBE.MC abiertas; IBE.MC no tiene histórico, así que su valor no se puede calcular.\n\n" +
    "GLD está un 26,7% por debajo de su máximo y tu trigger t1 (caída del 15% desde el pico) ha saltado. Eso es texto para que lo leas: yo no puedo ejecutar nada. Si decides vender, el comando sería:\n\n" +
    "    uv run invest-ll-execute --symbol GLD --side sell --quantity 10\n\n" +
    "(Respuesta de ejemplo: el modo NEXT_PUBLIC_MOCK=1 no consulta a Claude.)";
  const nuevo: S["MensajeChat"][] = [...historial, { autor: "operador", texto: pregunta }, { autor: "claude", texto: respuesta }];
  m.chats.set(sesion, nuevo);
  const r: S["RespuestaChat"] = { sesion, respuesta, historial: nuevo };
  return json(r);
}

// -- Enrutador -----------------------------------------------------------------------------------

export async function responder(peticion: Request): Promise<Response> {
  const url = new URL(peticion.url, "http://ejemplo.local");
  const ruta = url.pathname;
  const metodo = peticion.method.toUpperCase();
  const m = elMundo();
  await esperar(150 + Math.random() * 250);

  const clave = `${metodo} ${ruta}`;
  switch (clave) {
    case "GET /api/estado":
      if (m.escenario === "modo-roto") {
        return fallo(422, "INVEST_LL_MODE='reall' no es un modo conocido: usa simulation, testnet o real");
      }
      return json(estado(m));
    case "GET /api/mercado/rendimiento":
      return json(rendimiento());
    case "GET /api/mercado/serie":
      return serieRuta(url);
    case "GET /api/mercado/comparacion":
      return comparacion(url);
    case "GET /api/mercado/datos":
      return json(datos());
    case "POST /api/mercado/cotizaciones":
      await esperar(900);
      return json(cotizaciones(m));
    case "POST /api/mercado/descargar": {
      const o = await cuerpo(peticion);
      const simbolo = texto(o, "symbol") ?? "";
      await esperar(1500);
      if (simbolo === "LUNA/USDT") {
        const r: S["ResultadoDescarga"] = { symbol: simbolo, ok: false, detalle: "binance: el par LUNA/USDT no tiene velas diarias desde 2015 (listado en 2022-05-31); prueba con --start 2022-06-01" };
        return json(r);
      }
      m.descargados.add(simbolo);
      const r: S["ResultadoDescarga"] = { symbol: simbolo, ok: true, detalle: `Descargadas las velas diarias de ${simbolo} de 2015-01-01 a 2026-10-17 (${texto(o, "mercado") === "crypto" ? "ccxt-binance" : "yfinance"}).` };
      return json(r);
    }
    case "POST /api/mercado/actualizar": {
      await esperar(3500);
      const resultados: S["ResultadoDescarga"][] = DEFINICIONES.filter((d) => d.descargado !== null).map((d) =>
        d.simbolo === "XLU"
          ? { symbol: d.simbolo, ok: false, detalle: "yfinance: Read timed out tras 3 reintentos (query2.finance.yahoo.com)" }
          : { symbol: d.simbolo, ok: true, detalle: "Actualizado hasta 2026-10-16 (+1 vela)" },
      );
      const r: S["ResultadoActualizacion"] = { resultados, saltados: DEFINICIONES.filter((d) => d.descargado === null).map((d) => d.simbolo) };
      return json(r);
    }
    case "GET /api/cartera":
      return json(cartera(m));
    case "POST /api/cartera/movimientos": {
      const o = await cuerpo(peticion);
      const tipo = texto(o, "tipo") ?? "";
      const cantidad = texto(o, "cantidad") ?? "";
      if (leerDecimal(cantidad) === null || compararDecimal(cantidad, "0") <= 0) return fallo(422, `la cantidad debe ser un numero positivo, recibido '${cantidad}'`);
      if ((tipo === "compra" || tipo === "venta") && (!texto(o, "simbolo") || !texto(o, "precio"))) {
        return fallo(422, `una ${tipo} necesita activo y precio unitario`);
      }
      m.movimientos += 1;
      if (tipo === "compra") {
        const simbolo = (texto(o, "simbolo") ?? "").toUpperCase();
        const precio = texto(o, "precio") ?? "0";
        const s = serie(simbolo);
        const cierre = s ? ultimo(s.cierres) : undefined;
        const invertido = (Number(cantidad) * Number(precio)).toFixed(2);
        m.abiertasExtra.push({
          activo: simbolo,
          cantidad,
          coste_medio: precio,
          invertido,
          abierta: `${texto(o, "fecha") ?? "2026-10-17"}T00:00:00Z`,
          precio: cierre !== undefined ? cierre.toFixed(2) : null,
          precio_fecha: s ? (ultimo(s.fechas) ?? null) : null,
          valor: cierre !== undefined ? (Number(cantidad) * cierre).toFixed(2) : null,
          pnl_no_realizado: cierre !== undefined ? (Number(cantidad) * cierre - Number(invertido)).toFixed(2) : null,
        });
      }
      const r: S["MovimientoRegistrado"] = { activity_id: `act-${String(1000 + m.movimientos)}` };
      return json(r, 201);
    }
    case "GET /api/ordenes": {
      const filas = m.ordenes;
      const r: S["OrdenesEnviadas"] = {
        filas,
        total: filas.length,
        reales: filas.filter((f) => f.modo === "REAL").length,
        atencion: filas
          .filter((f) => f.estado !== "filled" || f.ejecutada !== f.pedida)
          .map((f) =>
            f.estado === "rejected"
              ? `${f.activo}: rechazada.`
              : f.estado === "unknown"
                ? `${f.activo}: ESTADO DESCONOCIDO. Se envio la orden y se perdio la conexion. NO se asume que se ejecuto ni que fallo — compruebalo en el exchange antes de volver a operar.`
                : `${f.activo}: ejecutada solo en parte (${f.ejecutada} de ${f.pedida}).`,
          ),
        sin_comision: filas.filter((f) => f.comision === null && f.ejecutada !== "0").length,
        registro: "ledger/ejecuciones.jsonl",
      };
      return json(r);
    }
    case "POST /api/ordenes/comprobar": {
      const o = await cuerpo(peticion);
      const motivo = motivoNoEnviar(m, texto(o, "cantidad") ?? "", texto(o, "escrito") ?? "");
      const r: S["EstadoEnvio"] = { puede: motivo === null, motivo };
      return json(r);
    }
    case "POST /api/ordenes": {
      const o = await cuerpo(peticion);
      if (!modo(m.escenario).envia_ordenes) {
        return fallo(403, "Modo simulacion: no se envia nada al exterior. Para operar de verdad, arranca el panel con INVEST_LL_MODE=testnet (o =real) y sus credenciales.");
      }
      const cantidad = texto(o, "cantidad") ?? "";
      const motivo = motivoNoEnviar(m, cantidad, texto(o, "escrito") ?? "");
      if (motivo) return fallo(422, motivo);
      const par = texto(o, "par") ?? "";
      const lado = texto(o, "lado") ?? "buy";
      await esperar(800);
      const precio = ultimo(serie(par)?.cierres ?? []) ?? 100;
      m.ordenes.unshift({
        cuando: new Date().toISOString(),
        modo: modo(m.escenario).nombre,
        activo: par,
        lado,
        pedida: cantidad,
        ejecutada: cantidad,
        precio: precio.toFixed(2),
        comision: (Number(cantidad) * precio * 0.001).toFixed(8),
        estado: "filled",
        referencia: `ejemplo-${Math.floor(Math.random() * 1e7)}`,
      });
      const r: S["ResultadoOrden"] = {
        estado: "filled",
        descripcion: `${par}: ejecutada ${cantidad} a ${precio.toFixed(2)}.`,
        necesita_atencion: false,
        modo: modo(m.escenario).nombre,
      };
      return json(r);
    }
    case "GET /api/simular/opciones": {
      const r: S["OpcionesSimular"] = {
        frecuencias: ["monthly", "quarterly", "weekly"],
        sugeridos: ["yfinance:GLD:DAY_1", "yfinance:TLT:DAY_1", "yfinance:SPY:DAY_1", "yfinance:XLE:DAY_1"],
        estrategias: ["cruce-medias", "precio-vs-media", "ruptura-maximos"],
        pausa: m.pausa,
      };
      return json(r);
    }
    case "POST /api/simular/propuesta":
      return propuesta(m, await cuerpo(peticion));
    case "POST /api/simular/propuesta/registrar": {
      if (m.pausa) return fallo(409, `Pausa activa: ${m.pausa}. No se registran entradas nuevas.`);
      const o = await cuerpo(peticion);
      const compras = Array.isArray(o.compras) ? o.compras : [];
      let registradas = 0;
      const problemas: string[] = [];
      for (const c of compras) {
        const fila = typeof c === "object" && c !== null ? (c as Objeto) : {};
        if (!texto(fila, "cantidad")) problemas.push(`${texto(fila, "symbol") ?? "?"}: sin precio descargado, registralo a mano`);
        else registradas += 1;
      }
      const r: S["RegistroPropuesta"] = { registradas, problemas };
      return json(r);
    }
    case "POST /api/simular/activo":
      return unActivo(await cuerpo(peticion));
    case "POST /api/simular/cartera/analisis":
      return analisis(await cuerpo(peticion));
    case "POST /api/simular/cartera/aportaciones":
      return aportaciones(await cuerpo(peticion));
    case "POST /api/simular/cartera/rotacion":
      return rotacion(await cuerpo(peticion));
    case "POST /api/simular/llm":
      await esperar(1200);
      return llm(m, await cuerpo(peticion));
    case "GET /api/vigilar/alertas":
      // En el escenario vacio no salta nada: se ve el texto de "nada que contar" tal cual.
      if (m.escenario === "vacio") return json({ alertas: [], nada_que_contar: NADA_QUE_CONTAR } satisfies S["Alertas"]);
      return json(alertas(url));
    case "GET /api/triggers": {
      const r: S["Triggers"] = { triggers: m.triggers, reglas: ["loss-from-entry", "drop-from-peak"], pausa: m.pausa };
      return json(r);
    }
    case "POST /api/triggers": {
      const o = await cuerpo(peticion);
      const simbolo = (texto(o, "simbolo") ?? "").trim().toUpperCase();
      const regla = texto(o, "regla") ?? "";
      const pct = numeroDe(o, "umbral_pct", 15);
      if (!simbolo) return fallo(422, "el trigger necesita un activo");
      if (!["loss-from-entry", "drop-from-peak"].includes(regla)) return fallo(422, `regla desconocida: '${regla}'`);
      const t = trigger(`t${m.siguienteTrigger}`, simbolo, regla, String(pct / 100), new Date().toISOString());
      m.siguienteTrigger += 1;
      m.triggers.push(t);
      return json(t, 201);
    }
    case "GET /api/triggers/comprobar":
      await esperar(400);
      return json(comprobarTriggers(m));
    case "POST /api/pausa": {
      const o = await cuerpo(peticion);
      const motivo = (texto(o, "motivo") ?? "").trim();
      if (!motivo) return fallo(422, "la pausa necesita un motivo: es lo que leeras cuando quieras retirarla");
      m.pausa = `${motivo} (${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC)`;
      return sinCuerpo();
    }
    case "DELETE /api/pausa":
      if (!m.pausa) return fallo(404, "No habia ninguna pausa activa");
      m.pausa = null;
      return sinCuerpo();
    case "GET /api/seguimiento":
      return json(seguimiento(m));
    case "GET /api/investigacion":
      return json(investigacion(m, url));
    case "GET /api/investigacion/estudio":
      if (m.escenario === "vacio") return fallo(404, "No hay ningun estudio en research/runs");
      return new Response(ESTUDIO_HTML, { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } });
    case "POST /api/chat":
      await esperar(1200);
      return chat(m, await cuerpo(peticion));
    default:
      break;
  }

  const desarmar = /^\/api\/triggers\/([^/]+)$/.exec(ruta);
  if (metodo === "DELETE" && desarmar) {
    const id = decodeURIComponent(desarmar[1] ?? "");
    const antes = m.triggers.length;
    m.triggers = m.triggers.filter((t) => t.trigger_id !== id);
    if (m.triggers.length === antes) return fallo(404, `No hay ningun trigger armado con id ${id}`);
    return sinCuerpo();
  }

  return fallo(404, `Ruta de ejemplo no definida: ${metodo} ${ruta}`);
}
