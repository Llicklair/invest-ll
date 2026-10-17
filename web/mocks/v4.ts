/**
 * El panel v4 en el modo de ejemplo (docs/panel-v4-real.md): las conexiones con varios exchanges,
 * las estrategias a medida (con sus pruebas sobre el pasado y sus versiones) y la conversacion
 * para disenarlas con Claude, con las MISMAS rutas que la API (`/api/conexiones*`, `/api/medida*`).
 * Los bots reales viven en mocks/vivo.ts, con los demas bots; de aqui leen el estado de los
 * exchanges y de las estrategias.
 *
 * Todo cuerpo va tipado con el contrato (`S["..."]`): si `web/openapi.json` cambia, `tsc` falla
 * aqui. Solo existe con `npm run dev:mock` (NEXT_PUBLIC_MOCK=1); `next build` no lo incluye.
 * Las claves que se "guardan" no se guardan: solo se recuerda que las hay (y una huella para
 * comprobar que las reales no son las de pruebas). Nunca se devuelven.
 */
import type { components } from "@/api/esquema";

import { escenarioActual, type Escenario } from "./escenarios";

type S = components["schemas"];
type Red = "pruebas" | "real";

// -- Azar con semilla (el mismo de mocks/vivo.ts) --------------------------------------------------

function mulberry32(semilla: number): () => number {
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function semilla(texto: string): number {
  let h = 2166136261;
  for (const c of texto) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

function normal(rnd: () => number): number {
  const u = Math.max(rnd(), 1e-12);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd());
}

function huella(texto: string): string {
  return semilla(texto).toString(16).padStart(8, "0") + semilla(`h:${texto}`).toString(16).padStart(8, "0").slice(0, 4);
}

const DIA_MS = 86_400_000;
const iso = (ms: number): string => new Date(ms).toISOString();

// -- Exchanges ----------------------------------------------------------------------------------------

const CLAVE_SECRETO = (nombre: string): S["CampoClave"] => ({
  clave: "secret",
  nombre: "Secreto (Secret Key)",
  secreto: true,
  ayuda: `El secreto que ${nombre} te enseña UNA vez al crear la clave. Aquí se escribe oculto y no se vuelve a enseñar nunca.`,
});

export const DISPONIBLES: S["ExchangeDisponible"][] = [
  {
    id: "binance",
    nombre: "Binance",
    tiene_pruebas: true,
    campos: [
      { clave: "apiKey", nombre: "Clave de la API (API Key)", secreto: false, ayuda: "Una cadena larga de letras y números. Sola no sirve para operar." },
      CLAVE_SECRETO("Binance"),
    ],
    como_conseguir_pruebas: [
      "Entra en testnet.binance.vision con tu cuenta de GitHub.",
      "Pulsa «Generate HMAC_SHA256 Key» y ponle un nombre. Las de tipo Ed25519 o RSA no sirven aquí.",
      "Copia la clave (API Key) y el secreto (Secret Key): el secreto solo se ve una vez.",
      "Pégalos aquí y prueba la conexión. Solo lee tu saldo ficticio: no envía nada.",
    ],
    como_conseguir_real: [
      "En binance.com, entra en tu perfil → Gestión de API → Crear API, de tipo «Generada por el sistema».",
      "Deja marcado solo «Habilitar lectura» y «Habilitar trading al contado (spot)».",
      "NUNCA marques «Habilitar retiros»: con esta clave nadie podría sacar dinero de tu cuenta.",
      "Si puedes, restringe la clave a la IP de este ordenador.",
      "Copia la clave y el secreto (tienen que ser distintos de los de pruebas) y pégalos aquí.",
    ],
    aviso: null,
  },
  {
    id: "hyperliquid",
    nombre: "Hyperliquid",
    tiene_pruebas: true,
    campos: [
      { clave: "walletAddress", nombre: "Dirección de tu cartera", secreto: false, ayuda: "La dirección pública (empieza por 0x) de la cuenta con la que operas." },
      {
        clave: "privateKey",
        nombre: "Clave privada de la API wallet",
        secreto: true,
        ayuda: "La de la API wallet, NUNCA la de tu cartera principal: una API wallet puede operar, pero no puede retirar.",
      },
    ],
    como_conseguir_pruebas: [
      "Entra en app.hyperliquid-testnet.xyz con tu cartera.",
      "Pide USDC de prueba en el grifo (Faucet). Ojo: Hyperliquid solo lo da si antes has depositado algo en la red real con esa misma dirección.",
      "En «API», crea una API wallet, autorízala y copia su clave privada.",
      "Pega aquí tu dirección y la clave privada de la API wallet, y prueba la conexión.",
    ],
    como_conseguir_real: [
      "En app.hyperliquid.xyz, ve a «API» y crea una API wallet nueva, distinta de la de pruebas.",
      "Autorízala con tu cartera: podrá comprar y vender, pero no retirar ni mover fondos.",
      "Copia su clave privada (solo se ve una vez) y pégala aquí con la dirección de tu cartera.",
      "Nunca pegues aquí la clave privada de tu cartera principal.",
    ],
    aviso: "Aquí Hyperliquid se usa solo al contado (spot), sin apalancamiento.",
  },
  {
    id: "bybit",
    nombre: "Bybit",
    tiene_pruebas: true,
    campos: [{ clave: "apiKey", nombre: "Clave de la API (API Key)", secreto: false, ayuda: "La que Bybit llama «API Key»." }, CLAVE_SECRETO("Bybit")],
    como_conseguir_pruebas: [
      "Entra en testnet.bybit.com (es una cuenta aparte de la normal).",
      "En «API», crea una clave de sistema con permiso de lectura y de trading al contado.",
      "Copia la clave y el secreto y pégalos aquí.",
    ],
    como_conseguir_real: [
      "En bybit.com → API → Crear nueva clave → «Generada por el sistema».",
      "Permisos: solo lectura y «Spot - Trade». NUNCA «Retiro» (Withdrawal).",
      "Restringe la clave a la IP de este ordenador si puedes.",
      "Copia la clave y el secreto y pégalos aquí.",
    ],
    aviso: null,
  },
  {
    id: "okx",
    nombre: "OKX",
    tiene_pruebas: true,
    campos: [
      { clave: "apiKey", nombre: "Clave de la API (API Key)", secreto: false, ayuda: "La que OKX llama «API key»." },
      CLAVE_SECRETO("OKX"),
      { clave: "password", nombre: "Frase de paso (passphrase)", secreto: true, ayuda: "La frase que elegiste TÚ al crear la clave en OKX." },
    ],
    como_conseguir_pruebas: [
      "En okx.com, cambia a «Trading demo» (arriba, en tu perfil).",
      "En «API» del modo demo, crea una clave con permiso «Leer» y «Operar». Elige una frase de paso.",
      "Copia la clave, el secreto y tu frase de paso y pégalos aquí.",
    ],
    como_conseguir_real: [
      "En okx.com (modo normal) → API → Crear clave.",
      "Permisos: «Leer» y «Operar». NUNCA «Retirar».",
      "Elige una frase de paso distinta de la de pruebas y apúntala: OKX no te la vuelve a enseñar.",
      "Copia la clave, el secreto y la frase de paso y pégalos aquí.",
    ],
    aviso: null,
  },
  {
    id: "kraken",
    nombre: "Kraken",
    tiene_pruebas: false,
    campos: [{ clave: "apiKey", nombre: "Clave de la API (API Key)", secreto: false, ayuda: "La que Kraken llama «API Key»." }, CLAVE_SECRETO("Kraken")],
    como_conseguir_pruebas: [],
    como_conseguir_real: [
      "En kraken.com → Ajustes → Seguridad → API → Crear clave.",
      "Marca solo: consultar fondos, consultar órdenes y operaciones, crear y modificar órdenes, y cancelar órdenes.",
      "NUNCA «Retirar fondos» (Withdraw Funds).",
      "Copia la clave y el secreto y pégalos aquí.",
    ],
    aviso: "Kraken no tiene red de pruebas: antes de usar dinero real, tu bot tiene que haber pasado por ficticio (7 días recomendados). Y Kraken no dice por la API si una clave puede retirar: compruébalo tú al crearla.",
  },
  {
    id: "coinbase",
    nombre: "Coinbase (Advanced)",
    tiene_pruebas: false,
    campos: [
      { clave: "apiKey", nombre: "Nombre de la clave (API key name)", secreto: false, ayuda: "Empieza por «organizations/…»." },
      { clave: "secret", nombre: "Clave privada (Private key)", secreto: true, ayuda: "El bloque que empieza por «-----BEGIN EC PRIVATE KEY-----». Se escribe oculto y no se vuelve a enseñar." },
    ],
    como_conseguir_pruebas: [],
    como_conseguir_real: [
      "En coinbase.com/developer-platform, crea una clave de la API de Advanced Trade.",
      "Permisos: «View» y «Trade». NUNCA «Transfer».",
      "Descarga o copia el nombre de la clave y la clave privada y pégalos aquí.",
    ],
    aviso: "Coinbase no tiene red de pruebas: antes de usar dinero real, tu bot tiene que haber pasado por ficticio (7 días recomendados).",
  },
];

interface RedMock {
  /** Huella de los valores guardados (para comparar reales con pruebas); null = sin claves. */
  huella: string | null;
  origen: "panel" | "entorno" | "ninguno";
  verificada: boolean;
  puede_retirar: boolean | null;
  comprobado: number | null;
}

interface ExchangeMock {
  id: string;
  activo: "sin_conectar" | "pruebas" | "real";
  redes: Record<Red, RedMock>;
}

const SIN_CLAVES: RedMock = { huella: null, origen: "ninguno", verificada: false, puede_retirar: null, comprobado: null };

function red(parcial: Partial<RedMock>): RedMock {
  return { ...SIN_CLAVES, ...parcial };
}

/** El estado de cada exchange segun el escenario (Binance sigue al camino de v2 en los de antes). */
function exchangesDe(e: Escenario, ahora: number): Map<string, ExchangeMock> {
  const hace = (min: number) => ahora - min * 60_000;
  const m = new Map<string, ExchangeMock>();
  for (const d of DISPONIBLES) m.set(d.id, { id: d.id, activo: "sin_conectar", redes: { pruebas: red({}), real: red({}) } });
  const fijar = (id: string, x: Omit<ExchangeMock, "id">) => m.set(id, { id, ...x });
  if (e === "sin-conexiones") return m;
  if (e === "bots-reales" || e === "parado-todo") {
    fijar("binance", {
      activo: "real",
      redes: {
        pruebas: red({ huella: "p-binance", origen: "panel", verificada: true, puede_retirar: false, comprobado: hace(60 * 24 * 12) }),
        real: red({ huella: "r-binance", origen: "panel", verificada: true, puede_retirar: false, comprobado: hace(60 * 24 * 9) }),
      },
    });
    fijar("hyperliquid", { activo: "pruebas", redes: { pruebas: red({ huella: "p-hl", origen: "panel", verificada: false, puede_retirar: false, comprobado: hace(95) }), real: red({}) } });
    fijar("okx", { activo: "sin_conectar", redes: { pruebas: red({ huella: "p-okx", origen: "panel" }), real: red({}) } });
    fijar("coinbase", { activo: "sin_conectar", redes: { pruebas: red({}), real: red({ huella: "r-cb", origen: "panel", puede_retirar: true, comprobado: hace(30) }) } });
    return m;
  }
  // Los escenarios de v2: Binance va por donde va el camino del plan.
  if (e === "entorno") {
    fijar("binance", { activo: "pruebas", redes: { pruebas: red({ huella: "entorno", origen: "entorno", verificada: true, puede_retirar: false, comprobado: hace(40) }), real: red({}) } });
  } else if (e === "pruebas" || e === "fallo-red") {
    fijar("binance", { activo: "pruebas", redes: { pruebas: red({ huella: "p-binance", origen: "panel", puede_retirar: false, comprobado: hace(25) }), real: red({}) } });
  } else if (e === "listo-para-real") {
    fijar("binance", {
      activo: "pruebas",
      redes: {
        pruebas: red({ huella: "p-binance", origen: "panel", verificada: true, puede_retirar: false, comprobado: hace(60 * 26) }),
        real: red({ huella: "r-binance", origen: "panel", puede_retirar: false, comprobado: hace(12) }),
      },
    });
  } else if (e === "real") {
    fijar("binance", {
      activo: "real",
      redes: {
        pruebas: red({ huella: "p-binance", origen: "panel", verificada: true, puede_retirar: false, comprobado: hace(60 * 24 * 3) }),
        real: red({ huella: "r-binance", origen: "panel", verificada: true, puede_retirar: false, comprobado: hace(60 * 20) }),
      },
    });
  }
  return m;
}

function disponible(id: string): S["ExchangeDisponible"] | undefined {
  return DISPONIBLES.find((d) => d.id === id);
}

function queFaltaReal(x: ExchangeMock): string[] {
  const d = disponible(x.id);
  const nombre = d?.nombre ?? x.id;
  const falta: string[] = [];
  const r = x.redes.real;
  if (r.huella === null) falta.push(`Guarda las claves de dinero real de ${nombre}.`);
  if (r.puede_retirar === true) falta.push("La clave de dinero real PUEDE retirar fondos: bórrala y crea otra sin ese permiso.");
  if (d?.tiene_pruebas && !x.redes.pruebas.verificada) falta.push("Haz al menos una orden en la red de pruebas: es la evidencia de que todo funciona.");
  return falta;
}

function estadoExchange(x: ExchangeMock): S["EstadoExchange"] {
  const d = disponible(x.id);
  const redes: S["EstadoRedExchange"][] = (d?.tiene_pruebas ? (["pruebas", "real"] as const) : (["real"] as const)).map((r) => {
    const v = x.redes[r];
    return {
      red: r,
      claves_guardadas: v.huella !== null,
      origen: v.origen,
      verificada: v.verificada,
      puede_retirar: v.huella === null ? null : v.puede_retirar,
      comprobado: v.comprobado === null ? null : iso(v.comprobado),
    };
  });
  return { id: x.id, nombre: d?.nombre ?? x.id, activo: x.activo, redes, que_falta_real: x.activo === "real" ? [] : queFaltaReal(x) };
}

const MCP: S["ConfigMcp"] = {
  comando: "uv",
  argumentos: ["run", "--directory", "C:\\Users\\marcos\\dev\\invest-ll", "invest-ll-mcp"],
  bloque_json: JSON.stringify(
    { mcpServers: { "invest-ll": { command: "uv", args: ["run", "--directory", "C:\\Users\\marcos\\dev\\invest-ll", "invest-ll-mcp"] } } },
    null,
    2,
  ),
  nota:
    "Con este conector, Claude puede ver tus exchanges y sus monedas, leer velas, escribir y validar estrategias, probarlas sobre el pasado, guardarlas, desplegarlas como bots con dinero ficticio, ver cómo van tus bots y pararlos. NO puede activar dinero real, subir límites ni tocar tus claves: eso solo se hace desde este panel, tecleando la confirmación.",
};

// -- Estrategias a medida -----------------------------------------------------------------------------

interface DefMoneda {
  nombre: string;
  precio: number;
  vol: number;
  dec: number;
}

const MONEDAS: Record<string, DefMoneda> = {
  BTC: { nombre: "Bitcoin", precio: 67_420, vol: 0.028, dec: 5 },
  ETH: { nombre: "Ethereum", precio: 2_441, vol: 0.035, dec: 4 },
  SOL: { nombre: "Solana", precio: 142.3, vol: 0.045, dec: 2 },
  XRP: { nombre: "XRP", precio: 2.41, vol: 0.042, dec: 1 },
  DOGE: { nombre: "Dogecoin", precio: 0.2134, vol: 0.05, dec: 0 },
  LINK: { nombre: "Chainlink", precio: 17.42, vol: 0.045, dec: 2 },
  AVAX: { nombre: "Avalanche", precio: 21.84, vol: 0.05, dec: 2 },
  HYPE: { nombre: "Hyperliquid", precio: 38.6, vol: 0.06, dec: 2 },
  PURR: { nombre: "Purr", precio: 0.1832, vol: 0.08, dec: 0 },
};

/** Como decide la estrategia en el mock (en la API la decide el interprete con su definicion). */
type Regla = "rebote" | "cruce" | "fuerza" | "rsi";

interface EstrategiaMock {
  id: string;
  nombre: string;
  autor: "claude" | "marcos";
  estado: S["ResumenEstrategia"]["estado"];
  monedas: string[];
  intervalo: string;
  explicacion: string;
  reglas: string[];
  regla: Regla;
  /** Fraccion del capital que entra cuando la regla dice "dentro". */
  tamano: number;
  /** Lo que hizo "mantener" en el ultimo ano en el ejemplo (fraccion), por moneda. */
  mantener: number[];
  definicion: Record<string, unknown>;
  versiones: S["VersionEstrategia"][];
  /** Versiones distintas que se han probado (para el aviso de sobreajuste). */
  probadas: Set<number>;
  pruebas: S["ResultadoPrueba"][];
  bots: string[];
  actualizada: number;
  /** Dias que lleva en ficticio (lo usan los bots reales de mocks/vivo.ts). */
  diasFicticio: number;
}

function definicionDe(nombre: string, monedas: string[], intervalo: string, regla: Regla, tamano: number, stop: number | null, autor: "claude" | "marcos", explicacion: string): Record<string, unknown> {
  const entradas: Record<Regla, unknown> = {
    rebote: { y: [{ ">": ["cierre", { minimo: { n: 30, sobre: "cierre" } }] }, { "<": ["cierre", { "*": [{ minimo: { n: 30, sobre: "cierre" } }, 1.05] }] }, { cruza_arriba: ["cierre", { sma: { n: 5 } }] }] },
    cruce: { cruza_arriba: [{ ema: { n: 12 } }, { ema: { n: 26 } }] },
    fuerza: { ">": [{ retorno: { n: 30 } }, 0] },
    rsi: { "<": [{ rsi: { n: 14 } }, 30] },
  };
  const entrar = entradas[regla];
  const salidas: Record<Regla, unknown> = {
    rebote: { o: [{ "<": ["cierre", { minimo: { n: 30, sobre: "cierre" } }] }, { cruza_abajo: ["cierre", { sma: { n: 20 } }] }] },
    cruce: { cruza_abajo: [{ ema: { n: 12 } }, { ema: { n: 26 } }] },
    fuerza: { "<=": [{ retorno: { n: 30 } }, 0] },
    rsi: { ">": [{ rsi: { n: 14 } }, 55] },
  };
  const salir = salidas[regla];
  return {
    formato: 1,
    nombre,
    monedas,
    intervalo,
    entrar,
    salir,
    tamano: { fraccion: tamano, reparto: monedas.length > 1 ? "igual" : "una", maximo_por_moneda: monedas.length > 1 ? 0.4 : 1 },
    riesgo: { stop_perdida: stop, toma_beneficio: null, stop_que_sigue: null },
    explicacion,
    autor,
  };
}

/** Puente browniano en logaritmos: n puntos de `desde` a `hasta` (como en mocks/vivo.ts). */
function puente(rnd: () => number, n: number, desde: number, hasta: number, sigma: number): number[] {
  const w: number[] = [0];
  for (let i = 1; i < n; i++) w.push((w[i - 1] ?? 0) + sigma * normal(rnd));
  const total = w[n - 1] ?? 0;
  const l0 = Math.log(desde);
  const l1 = Math.log(hasta);
  return w.map((x, i) => Math.exp(l0 + x - (i / (n - 1)) * total + (i / (n - 1)) * (l1 - l0)));
}

function peorCaida(valores: readonly number[]): number {
  let max = -Infinity;
  let peor = 0;
  for (const v of valores) {
    max = Math.max(max, v);
    peor = Math.min(peor, v / max - 1);
  }
  return peor;
}

function texto2(v: number): string {
  return v.toFixed(2);
}

function cantidadTexto(v: number, dec: number): string {
  return v.toFixed(dec).replace(/0+$/, "").replace(/\.$/, "") || "0";
}

const COMISION = 0.001;
const DESLIZAMIENTO = 0.0005;

/**
 * Una prueba sobre el pasado, inventada pero coherente: las cifras salen de las curvas (nunca se
 * escriben a mano), con comisiones y deslizamiento, y "mantener" con el mismo capital.
 */
function probarSobrePasado(e: EstrategiaMock, version: number, exchange: string, capital: number, desde: number, hasta: number): S["ResultadoPrueba"] {
  const rnd = mulberry32(semilla(`prueba:${e.id}:${version}:${exchange}:${capital}:${desde}:${hasta}`));
  const dias = Math.max(30, Math.round((hasta - desde) / DIA_MS));
  const n = Math.min(370, dias);
  const tiempos = Array.from({ length: n }, (_, i) => desde + (i / (n - 1)) * (hasta - desde));
  const escalaAnio = dias / 365;
  const caminos = e.monedas.map((coin, i) => {
    const def = MONEDAS[coin];
    const objetivo = Math.pow(1 + (e.mantener[i] ?? 0.1), escalaAnio) * (1 + 0.04 * normal(rnd));
    return puente(rnd, n, 1, Math.max(0.2, objetivo), (def?.vol ?? 0.04) * Math.sqrt(dias / n));
  });
  const indice = tiempos.map((_, k) => caminos.reduce((s, c) => s + (c[k] ?? 1), 0) / caminos.length);

  // La regla del ejemplo, sobre el indice de sus monedas (con velas cerradas: decide con k-1).
  const media = (k: number, v: number) => {
    const tramo = indice.slice(Math.max(0, k - v + 1), k + 1);
    return tramo.reduce((s, x) => s + x, 0) / tramo.length;
  };
  const minimo = (k: number, v: number) => Math.min(...indice.slice(Math.max(0, k - v + 1), k + 1));
  const quiere = (k: number, dentro: boolean): boolean => {
    const p = indice[k] ?? 1;
    switch (e.regla) {
      case "rebote":
        return dentro ? p > minimo(k, 30) && p > media(k, 20) * 0.985 : p < minimo(k, 30) * 1.06 && p > media(k, 5);
      case "cruce":
        return media(k, 6) > media(k, 14);
      case "fuerza":
        return k >= 30 && p > (indice[k - 30] ?? p);
      case "rsi":
        return dentro ? p < media(k, 10) * 1.04 : p < media(k, 14) * 0.95;
    }
  };

  let efectivo = capital;
  const cantidades = e.monedas.map(() => 0);
  let dentro = false;
  let dentroPasos = 0;
  let comisiones = 0;
  const curva: S["PuntoBot"][] = [];
  const curvaMantener: S["PuntoBot"][] = [];
  const operaciones: S["OperacionBot"][] = [];
  const valores: number[] = [];
  const precioDe = (i: number, k: number) => (MONEDAS[e.monedas[i] ?? ""]?.precio ?? 1) * ((caminos[i]?.[k] ?? 1) / (caminos[i]?.[n - 1] ?? 1));
  for (let k = 0; k < n; k++) {
    const t = tiempos[k] ?? hasta;
    const decide: boolean = k > 0 ? quiere(k - 1, dentro) : false;
    if (decide !== dentro) {
      for (const [i, coin] of e.monedas.entries()) {
        const def = MONEDAS[coin];
        const precio = precioDe(i, k) * (decide ? 1 + DESLIZAMIENTO : 1 - DESLIZAMIENTO);
        if (decide) {
          const importe = (capital * e.tamano) / e.monedas.length;
          const usar = Math.min(importe, efectivo / (1 + COMISION));
          const cantidad = usar / precio;
          const comision = usar * COMISION;
          efectivo -= usar + comision;
          cantidades[i] = (cantidades[i] ?? 0) + cantidad;
          comisiones += comision;
          operaciones.push(operacion(t, coin, def, "compra", cantidad, precio, comision, e.regla));
        } else {
          const cantidad = cantidades[i] ?? 0;
          const importe = cantidad * precio;
          const comision = importe * COMISION;
          efectivo += importe - comision;
          cantidades[i] = 0;
          comisiones += comision;
          operaciones.push(operacion(t, coin, def, "venta", cantidad, precio, comision, e.regla));
        }
      }
      dentro = decide;
    }
    if (dentro) dentroPasos++;
    const valor = efectivo + e.monedas.reduce((s, _, i) => s + (cantidades[i] ?? 0) * precioDe(i, k), 0);
    valores.push(valor);
    curva.push({ at: iso(t), valor: Math.round(valor * 100) / 100 });
    curvaMantener.push({ at: iso(t), valor: Math.round(capital * ((indice[k] ?? 1) / (indice[0] ?? 1)) * 100) / 100 });
  }
  const final = valores[n - 1] ?? capital;
  const mantenerFinal = curvaMantener[n - 1]?.valor ?? capital;
  const versionesProbadas = e.probadas.size;
  return {
    exchange,
    monedas: e.monedas,
    intervalo: e.intervalo,
    desde: iso(desde),
    hasta: iso(hasta),
    capital: texto2(capital),
    valor_final: texto2(final),
    ganancia_pct: final / capital - 1,
    mantener_pct: mantenerFinal / capital - 1,
    peor_caida: peorCaida(valores),
    mantener_peor_caida: peorCaida(curvaMantener.map((p) => p.valor)),
    operaciones: operaciones.length,
    comisiones: texto2(comisiones),
    tiempo_dentro: dentroPasos / n,
    curva,
    curva_mantener: curvaMantener,
    lista_operaciones: operaciones.slice(-200).reverse(),
    versiones_probadas: versionesProbadas,
    aviso_sobreajuste:
      versionesProbadas >= 3
        ? `Has probado ${versionesProbadas} versiones de esta estrategia sobre el mismo pasado. Elegir la mejor de muchas pruebas sobre el pasado se parece a hacer trampa: lo más probable es que en el futuro lo haga peor que aquí.`
        : null,
    avisos: [
      `Con comisiones de ${(COMISION * 100).toLocaleString("es-ES")} % por operación y un deslizamiento estimado de ${(DESLIZAMIENTO * 100).toLocaleString("es-ES")} %. Sin impuestos.`,
      ...(operaciones.length < 12 ? [`Solo ${operaciones.length} operaciones en todo el periodo: muy pocas para fiarse del resultado.`] : []),
      "El pasado no es una promesa: es lo que habría pasado, no lo que va a pasar.",
    ],
  };
}

function operacion(t: number, coin: string, def: DefMoneda | undefined, lado: "compra" | "venta", cantidad: number, precio: number, comision: number, regla: Regla): S["OperacionBot"] {
  const nombre = def?.nombre ?? coin;
  const porque: Record<Regla, [string, string]> = {
    rebote: ["el precio rebotó desde cerca de su mínimo de 30 días y cruzó por encima de su media de 5 velas", "el precio cayó por debajo de su media de 20 velas"],
    cruce: ["la media rápida (12 velas) cruzó por encima de la lenta (26)", "la media rápida cruzó por debajo de la lenta"],
    fuerza: [`${nombre} sube en 30 días: entra`, `${nombre} ya no sube en 30 días: sale a USDC`],
    rsi: ["el RSI de 14 velas bajó de 30 (muy vendido)", "el RSI subió de 55"],
  };
  const precioTxt = precio.toLocaleString("es-ES", { maximumFractionDigits: precio < 10 ? 4 : 2, useGrouping: "always" });
  return {
    at: iso(t),
    coin,
    nombre,
    lado,
    cantidad: cantidadTexto(cantidad, def?.dec ?? 4),
    precio: precio.toFixed(precio < 10 ? 4 : 2),
    importe: texto2(cantidad * precio),
    comision: comision.toFixed(4),
    motivo: `${lado === "compra" ? "Compraría" : "Vendería"} ${cantidad.toLocaleString("es-ES", { maximumFractionDigits: def?.dec ?? 4, useGrouping: "always" })} ${coin} a ${precioTxt}: ${(lado === "compra" ? porque[regla][0] : porque[regla][1])}.`,
  };
}

interface Semilla {
  id: string;
  nombre: string;
  autor: "claude" | "marcos";
  estado: S["ResumenEstrategia"]["estado"];
  monedas: string[];
  intervalo: string;
  regla: Regla;
  tamano: number;
  stop: number | null;
  mantener: number[];
  explicacion: string;
  reglas: string[];
  /** Notas de cada version, de la primera a la ultima. */
  notas: string[];
  /** Cuantas versiones se probaron (las ultimas). */
  probadas: number;
  bots: string[];
  diasFicticio: number;
}

function crearEstrategia(s: Semilla, ahora: number): EstrategiaMock {
  const versiones = s.notas.map((nota, i) => ({
    version: i + 1,
    at: iso(ahora - (s.notas.length - i) * 2.3 * DIA_MS),
    huella: huella(`${s.id}:${i + 1}`),
    nota,
  }));
  const e: EstrategiaMock = {
    id: s.id,
    nombre: s.nombre,
    autor: s.autor,
    estado: s.estado,
    monedas: s.monedas,
    intervalo: s.intervalo,
    explicacion: s.explicacion,
    reglas: s.reglas,
    regla: s.regla,
    tamano: s.tamano,
    mantener: s.mantener,
    definicion: definicionDe(s.nombre, s.monedas, s.intervalo, s.regla, s.tamano, s.stop, s.autor, s.explicacion),
    versiones,
    probadas: new Set(),
    pruebas: [],
    bots: s.bots,
    actualizada: Date.parse(versiones[versiones.length - 1]?.at ?? iso(ahora)),
    diasFicticio: s.diasFicticio,
  };
  const ultima = s.notas.length;
  for (let v = ultima - s.probadas + 1; v <= ultima; v++) {
    e.probadas.add(v);
    const hasta = Math.floor((ahora - (ultima - v) * DIA_MS) / DIA_MS) * DIA_MS;
    e.pruebas.unshift(probarSobrePasado(e, v, "binance", 1000, hasta - 365 * DIA_MS, hasta));
  }
  return e;
}

function semillasDe(e: Escenario): Semilla[] {
  if (e === "sin-conexiones") return [];
  const conBots = e === "bots-reales" || e === "parado-todo";
  return [
    {
      id: "rebote-eth",
      nombre: "Rebote de ETH desde su mínimo de 30 días",
      autor: "claude",
      estado: conBots ? "real" : "probada",
      monedas: ["ETH"],
      intervalo: "4h",
      regla: "rebote",
      tamano: 0.5,
      stop: 0.08,
      mantener: [0.31],
      explicacion:
        "Compra Ethereum cuando rebota desde cerca de su mínimo de los últimos 30 días, con la mitad del capital, y vende si vuelve a caer por debajo de su media o si pierde un 8 % desde la compra. El resto se queda en USDC.",
      reglas: [
        "Entra cuando el precio está a menos de un 5 % de su mínimo de 30 días y cruza por encima de su media de 5 velas.",
        "Sale cuando el precio cae por debajo de su media de 20 velas, o por debajo del mínimo de 30 días.",
        "Usa la mitad del capital en cada entrada; el resto se queda en USDC.",
        "Stop de pérdida: vende si pierde un 8 % desde la compra.",
        "Decide solo con velas de 4 horas ya cerradas.",
      ],
      notas: [
        "Primera versión: entra al rebotar desde el mínimo de 30 días.",
        "Sale por debajo de la media de 20 velas en vez de esperar al mínimo.",
        "Entra con la mitad del capital, no con todo.",
        "Stop de pérdida del 8 %.",
      ],
      probadas: 4,
      bots: conBots ? ["eth-rebote-real"] : [],
      diasFicticio: 16,
    },
    {
      id: "cruce-btc-4h",
      nombre: "Cruce de medias de Bitcoin en 4 h",
      autor: "claude",
      estado: conBots ? "ficticio" : "probada",
      monedas: ["BTC"],
      intervalo: "4h",
      regla: "cruce",
      tamano: 1,
      stop: null,
      mantener: [0.42],
      explicacion: "Está en Bitcoin mientras su media rápida (12 velas de 4 h) va por encima de la lenta (26 velas), y en USDC cuando va por debajo.",
      reglas: [
        "Entra con todo el capital cuando la media de 12 velas cruza por encima de la de 26.",
        "Sale a USDC cuando la media de 12 velas cruza por debajo de la de 26.",
        "Decide solo con velas de 4 horas ya cerradas.",
      ],
      notas: ["Primera versión, a petición tuya: «un cruce de medias clásico en BTC»."],
      probadas: 1,
      bots: conBots ? ["cruce-btc-ficticio"] : [],
      diasFicticio: conBots ? 3.1 : 0,
    },
    {
      id: "fuerza-tres",
      nombre: "Las tres más fuertes del mes",
      autor: "claude",
      estado: conBots ? "ficticio" : "probada",
      monedas: ["BTC", "ETH", "SOL"],
      intervalo: "1d",
      regla: "fuerza",
      tamano: 0.9,
      stop: null,
      mantener: [0.42, 0.31, 0.18],
      explicacion: "Reparte el capital entre Bitcoin, Ethereum y Solana, pero solo en las que suben en los últimos 30 días; las que no, a USDC.",
      reglas: [
        "Cada día, mira lo que ha hecho cada moneda en 30 días.",
        "Está en las que suben, a partes iguales y como mucho un 40 % del capital en cada una.",
        "Las que no suben, a USDC.",
        "Usa como mucho el 90 % del capital.",
      ],
      notas: ["Primera versión.", "Como mucho un 40 % en cada moneda."],
      probadas: 2,
      bots: conBots ? ["fuerza-pruebas"] : [],
      diasFicticio: conBots ? 2.4 : 0,
    },
    {
      id: "mi-rsi-sol",
      nombre: "RSI bajo en Solana",
      autor: "marcos",
      estado: "borrador",
      monedas: ["SOL"],
      intervalo: "1h",
      regla: "rsi",
      tamano: 0.3,
      stop: 0.05,
      mantener: [0.18],
      explicacion: "Compra un poco de Solana cuando está muy vendida (RSI por debajo de 30) y la vende cuando se recupera.",
      reglas: [
        "Entra con el 30 % del capital cuando el RSI de 14 velas de 1 h baja de 30.",
        "Sale cuando el RSI sube de 55.",
        "Stop de pérdida: vende si pierde un 5 % desde la compra.",
      ],
      notas: ["Escrita a mano."],
      probadas: 0,
      bots: [],
      diasFicticio: 0,
    },
  ];
}

// -- Disenar con Claude -------------------------------------------------------------------------------

interface SesionMock {
  id: string;
  historial: S["MensajeDiseno"][];
  estrategia: string | null;
  herramientas: string[];
  turnos: number;
}

// -- El mundo de ejemplo ------------------------------------------------------------------------------

interface MundoV4 {
  escenario: Escenario;
  exchanges: Map<string, ExchangeMock>;
  estrategias: Map<string, EstrategiaMock>;
  sesiones: Map<string, SesionMock>;
  siguiente: number;
  /** v5: en «sin-claude», si ya se pulsó Conectar (y pasó el rato de iniciar sesión). */
  claudeConectado?: boolean;
}

let mundo: MundoV4 | null = null;

function elMundo(): MundoV4 {
  const e = escenarioActual("con-plan");
  if (mundo && mundo.escenario === e) return mundo;
  const ahora = Date.now();
  const estrategias = new Map<string, EstrategiaMock>();
  for (const s of semillasDe(e)) estrategias.set(s.id, crearEstrategia(s, ahora));
  const m: MundoV4 = { escenario: e, exchanges: exchangesDe(e, ahora), estrategias, sesiones: new Map(), siguiente: 1 };
  mundo = m;
  if (e === "bots-reales" || e === "parado-todo") m.sesiones.set("dis-eth-rebote", sesionDeEjemplo(m, ahora));
  return m;
}

function sesionDeEjemplo(m: MundoV4, ahora: number): SesionMock {
  const e = m.estrategias.get("rebote-eth");
  const p = e?.pruebas[0];
  const hace = (h: number) => iso(ahora - h * 3_600_000);
  return {
    id: "dis-eth-rebote",
    estrategia: "rebote-eth",
    herramientas: ["validar", "guardar", "probar"],
    turnos: 2,
    historial: [
      { autor: "marcos", texto: "Quiero algo para ETH: comprar cuando rebote desde el mínimo de 30 días y vender si cae un 8 %.", at: hace(30) },
      {
        autor: "claude",
        texto:
          "He escrito **Rebote de ETH desde su mínimo de 30 días** y la he probado sobre el último año en Binance, con comisiones.\n\n" +
          "- Entra cuando el precio está cerca de su mínimo de 30 días y empieza a subir.\n- Sale si cae por debajo de su media de 20 velas o pierde un 8 %.\n\n" +
          "**La pega principal:** con todo el capital dentro, la peor caída fue casi la misma que manteniendo. ¿Pruebo a entrar solo con la mitad?",
        at: hace(29.9),
      },
      { autor: "marcos", texto: "Sí, con la mitad. Y enséñame cuánto pierde en el peor momento.", at: hace(29) },
      { autor: "claude", texto: textoResultado(e?.nombre ?? "la estrategia", p, e?.monedas ?? ["ETH"], true), at: hace(28.9) },
    ],
  };
}

function pct(v: number | null | undefined, decimales = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = Math.abs(v * 100).toLocaleString("es-ES", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
  return `${v > 0.0000001 ? "+" : v < -0.0000001 ? "−" : ""}${s} %`;
}

/** El resumen de una prueba en markdown, CON sus pegas (docs/panel-v4-real.md §2). */
function textoResultado(nombre: string, p: S["ResultadoPrueba"] | undefined, monedas: string[], segunda: boolean): string {
  if (!p) return `He guardado **${nombre}**, pero aún no la he probado.`;
  const mantener = monedas.length > 1 ? "Mantener las tres" : `Mantener ${monedas[0] ?? ""}`;
  const pegas: string[] = [];
  if (p.ganancia_pct < p.mantener_pct) pegas.push(`Ganó **menos que solo mantener** (${pct(p.ganancia_pct)} frente a ${pct(p.mantener_pct)}).`);
  if (p.operaciones < 12) pegas.push(`Solo hizo **${p.operaciones} operaciones** en un año: pocas para fiarse.`);
  if (p.tiempo_dentro < 0.5) pegas.push(`Pasó el ${Math.round((1 - p.tiempo_dentro) * 100)} % del tiempo en USDC: habrá rachas en que no gane nada mientras el mercado sube.`);
  if (p.aviso_sobreajuste) pegas.push(`Ya van **${p.versiones_probadas} versiones** probadas sobre el mismo año: cuantas más pruebo, más probable es que esté eligiendo la que tuvo suerte.`);
  return (
    `${segunda ? "Hecho: nueva versión que entra con la mitad del capital." : `He escrito **${nombre}**, la he validado y la he probado.`} Resultado sobre el último año en Binance, con comisiones y 1.000 USDC:\n\n` +
    `| | La estrategia | ${mantener} |\n|---|---|---|\n` +
    `| Resultado | ${pct(p.ganancia_pct)} | ${pct(p.mantener_pct)} |\n` +
    `| En el peor momento | ${pct(p.peor_caida)} | ${pct(p.mantener_peor_caida)} |\n` +
    `| Operaciones | ${p.operaciones} | 1 |\n\n` +
    `**Las pegas**\n\n${pegas.map((x) => `- ${x}`).join("\n") || "- Ninguna grave, pero es un solo año: el pasado no es una promesa."}\n\n` +
    "Si quieres, la despliego como bot con **dinero ficticio** para verla en vivo. Pasarla a dinero real no puedo: eso lo haces tú desde el panel."
  );
}

// -- Lo que leen los bots (mocks/vivo.ts) -------------------------------------------------------------

export interface InfoEstrategia {
  id: string;
  nombre: string;
  monedas: string[];
  diasFicticio: number;
  ultima: S["ResultadoPrueba"] | null;
}

export function estrategiaMock(id: string): InfoEstrategia | null {
  const e = elMundo().estrategias.get(id);
  return e ? { id: e.id, nombre: e.nombre, monedas: e.monedas, diasFicticio: e.diasFicticio, ultima: e.pruebas[0] ?? null } : null;
}

/** ¿Se puede operar en este exchange y red? (claves guardadas y el exchange activo en esa red o mas). */
export function exchangeEn(id: string, r: Red): { nombre: string; ok: boolean } | null {
  const x = elMundo().exchanges.get(id);
  const d = disponible(id);
  if (!x || !d) return null;
  const ok = r === "real" ? x.activo === "real" : x.activo !== "sin_conectar" && x.redes.pruebas.huella !== null;
  return { nombre: d.nombre, ok };
}

export function nombreExchange(id: string | null): string | null {
  return id === null ? null : (disponible(id)?.nombre ?? id);
}

/** Un bot de pruebas que ejecuta su primera orden es la evidencia de la etapa 2. */
export function anotarOrdenPruebas(id: string): void {
  const x = elMundo().exchanges.get(id);
  if (x) x.redes.pruebas.verificada = true;
}

/** Al desplegar o activar, la estrategia cambia de estado y apunta el bot. */
export function anotarBotEstrategia(id: string, bot: string, modo: "ficticio" | "pruebas" | "real"): void {
  const e = elMundo().estrategias.get(id);
  if (!e) return;
  if (!e.bots.includes(bot)) e.bots.push(bot);
  if (modo === "real") e.estado = "real";
  else if (modo === "ficticio" && e.estado !== "real") e.estado = "ficticio";
  else if (e.estado === "borrador") e.estado = "probada";
}

type Desplegador = (estrategia: InfoEstrategia, nombre: string, capital: number) => string;
let desplegador: Desplegador | null = null;

/** mocks/vivo.ts registra aqui como se despliega un bot ficticio (el conector MCP lo hace asi). */
export function alDesplegarFicticio(fn: Desplegador): void {
  desplegador = fn;
}

// -- Rutas ------------------------------------------------------------------------------------------------

type Objeto = Record<string, unknown>;

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

function fallo(status: number, detail: string): Response {
  return json({ detail }, status);
}

function esperar(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

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

function esRed(v: string): v is Red {
  return v === "pruebas" || v === "real";
}

export function esRutaV4(ruta: string): boolean {
  return /^\/api\/(conexiones|medida|claude|operar)(\/|$)/.test(ruta);
}

function conexiones(m: MundoV4): S["Conexiones"] {
  return { exchanges: DISPONIBLES.map((d) => estadoExchange(m.exchanges.get(d.id) ?? { id: d.id, activo: "sin_conectar", redes: { pruebas: red({}), real: red({}) } })), mcp: MCP };
}

function guardarClaves(m: MundoV4, id: string, r: Red, o: Objeto): Response {
  const x = m.exchanges.get(id);
  const d = disponible(id);
  if (!x || !d) return fallo(404, `No conozco ningún exchange «${id}».`);
  if (r === "pruebas" && !d.tiene_pruebas) return fallo(422, `${d.nombre} no tiene red de pruebas: solo se guardan claves de dinero real.`);
  if (x.redes[r].origen === "entorno") return fallo(409, `Las claves de ${r === "pruebas" ? "pruebas" : "dinero real"} de ${d.nombre} vienen del entorno: mandan ellas. Cámbialas allí.`);
  const valores = typeof o.valores === "object" && o.valores !== null ? (o.valores as Objeto) : {};
  const faltan = d.campos.filter((c) => typeof valores[c.clave] !== "string" || String(valores[c.clave]).trim().length === 0);
  if (faltan.length) return fallo(422, `Falta: ${faltan.map((c) => c.nombre).join(", ")}.`);
  const cortas = d.campos.filter((c) => c.clave !== "walletAddress" && String(valores[c.clave]).trim().length < 8);
  if (cortas.length) return fallo(422, `${cortas.map((c) => c.nombre).join(", ")}: es demasiado corta para ser una clave de ${d.nombre}. Cópiala entera.`);
  const h = huella(d.campos.map((c) => String(valores[c.clave]).trim()).join("|"));
  const otra = x.redes[r === "real" ? "pruebas" : "real"];
  if (otra.huella === h) return fallo(422, "Son las mismas claves que las de la otra red: las de dinero real tienen que ser distintas de las de pruebas.");
  const mala = d.campos.some((c) => String(valores[c.clave]).trim().toLowerCase().startsWith("mal"));
  x.redes[r] = { huella: mala ? `mal-${h}` : h, origen: "panel", verificada: r === "real" ? false : x.redes[r].verificada, puede_retirar: null, comprobado: null };
  return new Response(null, { status: 204 });
}

function borrarClaves(m: MundoV4, id: string, r: Red): Response {
  const x = m.exchanges.get(id);
  const d = disponible(id);
  if (!x || !d) return fallo(404, `No conozco ningún exchange «${id}».`);
  if (x.redes[r].origen === "entorno") return fallo(409, "Esas claves vienen del entorno: el panel no las puede borrar.");
  if (x.redes[r].huella === null) return fallo(404, `No había claves de ${r === "pruebas" ? "pruebas" : "dinero real"} de ${d.nombre} guardadas.`);
  x.redes[r] = { ...SIN_CLAVES, verificada: x.redes[r].verificada };
  if (x.activo === r || (r === "pruebas" && x.activo === "pruebas")) x.activo = "sin_conectar";
  return new Response(null, { status: 204 });
}

const SALDOS: Record<string, Record<Red, S["SaldoMoneda"][]>> = {
  binance: {
    pruebas: [
      { moneda: "USDT", cantidad: "10000.00000000" },
      { moneda: "BTC", cantidad: "1.00000000" },
      { moneda: "ETH", cantidad: "1.00000000" },
    ],
    real: [
      { moneda: "USDC", cantidad: "1184.21000000" },
      { moneda: "ETH", cantidad: "0.10240000" },
      { moneda: "SOL", cantidad: "0.90000000" },
    ],
  },
  hyperliquid: { pruebas: [{ moneda: "USDC", cantidad: "999.00" }], real: [{ moneda: "USDC", cantidad: "250.00" }] },
};

function probar(m: MundoV4, id: string, r: Red): Response {
  const x = m.exchanges.get(id);
  const d = disponible(id);
  if (!x || !d) return fallo(404, `No conozco ningún exchange «${id}».`);
  const v = x.redes[r];
  if (v.huella === null) return fallo(404, `No hay claves de ${r === "pruebas" ? "pruebas" : "dinero real"} de ${d.nombre} guardadas: pégalas primero.`);
  if (v.huella.startsWith("mal-")) {
    v.comprobado = null;
    return json({
      ok: false,
      detalle: `${d.nombre} dice que la clave no es válida («Invalid API-key, IP, or permissions for action»). Revisa que la copiaste entera, que es de la ${r === "pruebas" ? "red de pruebas" : "cuenta normal"} y, si la limitaste por IP, que es la de este ordenador.`,
      saldo: [],
      permisos: null,
    } satisfies S["PruebaExchange"]);
  }
  v.comprobado = Date.now();
  if (id === "coinbase" && r === "real") v.puede_retirar = true;
  else if (id === "kraken") v.puede_retirar = null;
  else v.puede_retirar = false;
  const permisos =
    v.puede_retirar === true
      ? "Lectura, operar y RETIRAR. Esta clave puede sacar dinero de tu cuenta: bórrala y crea otra sin el permiso de retirada."
      : v.puede_retirar === false
        ? "Lectura y operar al contado. No puede retirar."
        : `${d.nombre} no dice si esta clave puede retirar: compruébalo tú en su página de claves.`;
  return json({
    ok: true,
    detalle: `Conectado con ${d.nombre} (${r === "pruebas" ? "red de pruebas: dinero ficticio" : "dinero real"}). Solo se ha leído el saldo: no se ha enviado ninguna orden.`,
    saldo: SALDOS[id]?.[r] ?? [{ moneda: "USDT", cantidad: r === "pruebas" ? "5000.00" : "312.40" }],
    permisos,
  } satisfies S["PruebaExchange"]);
}

function activar(m: MundoV4, id: string, o: Objeto): Response {
  const x = m.exchanges.get(id);
  const d = disponible(id);
  if (!x || !d) return fallo(404, `No conozco ningún exchange «${id}».`);
  const r = texto(o, "red") ?? "";
  if (!esRed(r)) return fallo(422, "La red tiene que ser «pruebas» o «real».");
  if (r === "pruebas") {
    if (!d.tiene_pruebas) return fallo(422, `${d.nombre} no tiene red de pruebas.`);
    if (x.redes.pruebas.huella === null) return fallo(422, `Guarda antes las claves de pruebas de ${d.nombre}.`);
    // Como la API: activar prueba la conexion por si mismo (no hace falta "Probar" antes).
    if (x.redes.pruebas.huella.startsWith("mal-")) return fallo(422, `No se activó: ${d.nombre} dice que la clave de pruebas no es válida. Revisa que la copiaste entera y que es de su red de pruebas.`);
    x.redes.pruebas.comprobado = Date.now();
    x.activo = "pruebas";
    return json(estadoExchange(x) satisfies S["EstadoExchange"]);
  }
  if ((texto(o, "confirmacion") ?? "") !== "DINERO REAL") return fallo(422, "Para usar dinero real, escribe exactamente DINERO REAL, en mayúsculas.");
  if (x.redes.real.huella?.startsWith("mal-")) return fallo(422, `No se activó: ${d.nombre} dice que la clave de dinero real no es válida.`);
  // Activar prueba la conexion por si mismo, y con ello sabe (si el exchange lo dice) si la clave puede retirar.
  if (x.redes.real.huella !== null) {
    x.redes.real.comprobado = Date.now();
    x.redes.real.puede_retirar = id === "coinbase" ? true : id === "kraken" ? null : false;
  }
  const falta = queFaltaReal(x);
  if (falta.length) return fallo(422, `Todavía no se puede usar dinero real en ${d.nombre}: ${falta.map((f) => f.replace(/\.$/, "")).join("; ")}.`);
  x.activo = "real";
  return json(estadoExchange(x) satisfies S["EstadoExchange"]);
}

const BASES = ["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "HYPE"] as const;

function mercados(id: string, r: Red): Response {
  const d = disponible(id);
  if (!d) return fallo(404, `No conozco ningún exchange «${id}».`);
  if (r === "pruebas" && !d.tiene_pruebas) return fallo(422, `${d.nombre} no tiene red de pruebas.`);
  const cotizada = id === "hyperliquid" || id === "coinbase" ? "USDC" : id === "kraken" ? "USD" : "USDT";
  // La testnet de Hyperliquid solo tiene libro en PURR/USDC (BTC/USDC esta, pero vacio).
  const bases: readonly string[] =
    id === "hyperliquid" && r === "pruebas"
      ? ["PURR"]
      : BASES.filter((b) => (b === "HYPE" ? id === "hyperliquid" || id === "bybit" || id === "okx" : true)).filter((b) => !(r === "pruebas" && (b === "LINK" || b === "AVAX")));
  const lista: S["MercadoExchange"][] = bases.map((b) => ({
    par: `${b}/${cotizada}`,
    base: b,
    cotizada,
    nombre: MONEDAS[b]?.nombre ?? b,
    minimo_importe: id === "hyperliquid" ? "10" : id === "kraken" ? "5" : "5",
    paso_cantidad: (10 ** -(MONEDAS[b]?.dec ?? 4)).toFixed(MONEDAS[b]?.dec ?? 4),
  }));
  return json({ exchange: id, red: r, mercados: lista } satisfies S["MercadosExchange"]);
}

function resumen(e: EstrategiaMock): S["ResumenEstrategia"] {
  return {
    id: e.id,
    nombre: e.nombre,
    version: e.versiones.length,
    estado: e.estado,
    autor: e.autor,
    explicacion: e.explicacion,
    monedas: e.monedas,
    intervalo: e.intervalo,
    actualizada: iso(e.actualizada),
    ultima_prueba: e.pruebas[0] ?? null,
    bots: e.bots,
  };
}

function detalle(e: EstrategiaMock): S["DetalleEstrategia"] {
  return { ...resumen(e), definicion: e.definicion, reglas_en_llano: e.reglas, versiones: [...e.versiones].reverse(), pruebas: e.pruebas };
}

const INTERVALOS = ["15m", "1h", "4h", "1d"];

/** La validacion del formato cerrado, en llano (en la API la hace estrategias_custom). */
function validar(def: unknown): { ok: true; d: Objeto } | { ok: false; motivo: string } {
  if (typeof def !== "object" || def === null || Array.isArray(def)) return { ok: false, motivo: "La estrategia tiene que ser un objeto JSON ({ … })." };
  const d = def as Objeto;
  const nombre = d.nombre;
  if (typeof nombre !== "string" || !nombre.trim()) return { ok: false, motivo: "Falta «nombre»: ponle un nombre a la estrategia." };
  const monedas = d.monedas;
  if (!Array.isArray(monedas) || !monedas.length || !monedas.every((x) => typeof x === "string")) return { ok: false, motivo: "«monedas» tiene que ser una lista con al menos una moneda, por ejemplo [\"ETH\"]." };
  const rara = (monedas as string[]).find((x) => !(x in MONEDAS));
  if (rara) return { ok: false, motivo: `No conozco la moneda «${rara}». Usa el nombre corto: BTC, ETH, SOL…` };
  if (typeof d.intervalo !== "string" || !INTERVALOS.includes(d.intervalo)) return { ok: false, motivo: `«intervalo» tiene que ser uno de: ${INTERVALOS.join(", ")}.` };
  for (const campo of ["entrar", "salir"]) {
    const v = d[campo];
    if (typeof v !== "object" || v === null || Array.isArray(v)) return { ok: false, motivo: `Falta «${campo}»: una condición, por ejemplo {"cruza_arriba": [{"ema": {"n": 12}}, {"ema": {"n": 26}}]}.` };
    if (JSON.stringify(v).includes("\"codigo\"") || JSON.stringify(v).includes("\"expresion\"")) return { ok: false, motivo: `«${campo}» no admite código ni expresiones libres: solo indicadores, comparaciones y y/o/no.` };
  }
  const tamano = d.tamano;
  const fraccion = typeof tamano === "object" && tamano !== null ? (tamano as Objeto).fraccion : undefined;
  if (typeof fraccion !== "number" || fraccion <= 0 || fraccion > 1) return { ok: false, motivo: "«tamano.fraccion» tiene que ser un número entre 0 y 1 (0.5 = la mitad del capital)." };
  return { ok: true, d };
}

function guardar(m: MundoV4, o: Objeto): Response {
  const v = validar(o.definicion);
  if (!v.ok) return fallo(422, v.motivo);
  const autor = texto(o, "autor") === "claude" ? "claude" : "marcos";
  const nota = (texto(o, "nota") ?? "").trim();
  const id = texto(o, "id");
  const d = v.d;
  const monedas = d.monedas as string[];
  const intervalo = d.intervalo as string;
  const nombre = (d.nombre as string).trim();
  const fraccion = (d.tamano as Objeto).fraccion as number;
  const explicacion = typeof d.explicacion === "string" && d.explicacion.trim() ? d.explicacion.trim() : `${nombre}, escrita a mano.`;
  const ahora = Date.now();
  if (id) {
    const e = m.estrategias.get(id);
    if (!e) return fallo(404, "No hay ninguna estrategia con ese id: puede que la hayas borrado.");
    const version = e.versiones.length + 1;
    e.versiones.push({ version, at: iso(ahora), huella: huella(JSON.stringify(d)), nota: nota || "Cambios a mano." });
    e.definicion = d;
    e.nombre = nombre;
    e.monedas = monedas;
    e.intervalo = intervalo;
    e.tamano = fraccion;
    e.explicacion = explicacion;
    e.autor = autor === "marcos" && e.autor === "claude" ? "claude" : e.autor;
    e.actualizada = ahora;
    if (e.estado === "probada") e.estado = "borrador";
    return json(detalle(e) satisfies S["DetalleEstrategia"], 201);
  }
  const nuevoId = `${nombre.toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32) || "estrategia"}-${m.siguiente++}`;
  const e: EstrategiaMock = {
    id: nuevoId,
    nombre,
    autor,
    estado: "borrador",
    monedas,
    intervalo,
    explicacion,
    reglas: ["(Reglas en llano de lo que has escrito: entrar, salir, tamaño y riesgo, frase a frase.)"],
    regla: "cruce",
    tamano: fraccion,
    mantener: monedas.map((c) => (c === "BTC" ? 0.42 : c === "ETH" ? 0.31 : 0.15)),
    definicion: d,
    versiones: [{ version: 1, at: iso(ahora), huella: huella(JSON.stringify(d)), nota: nota || "Primera versión." }],
    probadas: new Set(),
    pruebas: [],
    bots: [],
    actualizada: ahora,
    diasFicticio: 0,
  };
  m.estrategias.set(e.id, e);
  return json(detalle(e) satisfies S["DetalleEstrategia"], 201);
}

function probarRuta(m: MundoV4, id: string, o: Objeto): Response {
  const e = m.estrategias.get(id);
  if (!e) return fallo(404, "No hay ninguna estrategia con ese id: puede que la hayas borrado.");
  const exchange = texto(o, "exchange") ?? "";
  if (!disponible(exchange)) return fallo(422, `No conozco ningún exchange «${exchange}».`);
  const capital = Number(texto(o, "capital") ?? "1000");
  if (!Number.isFinite(capital) || capital <= 0) return fallo(422, "El capital tiene que ser mayor que cero.");
  const ahora = Math.floor(Date.now() / DIA_MS) * DIA_MS;
  const hasta = texto(o, "hasta") ? Date.parse(texto(o, "hasta") ?? "") : ahora;
  const desde = texto(o, "desde") ? Date.parse(texto(o, "desde") ?? "") : hasta - 365 * DIA_MS;
  if (!Number.isFinite(desde) || !Number.isFinite(hasta)) return fallo(422, "Las fechas no se entienden: usa el formato del calendario.");
  if (hasta > ahora + DIA_MS) return fallo(422, "La prueba no puede acabar en el futuro.");
  if (hasta - desde < 30 * DIA_MS) return fallo(422, "Prueba al menos 30 días: con menos, el resultado es puro azar.");
  if (desde < Date.parse("2020-01-01")) return fallo(422, `Solo hay velas de ${disponible(exchange)?.nombre ?? exchange} desde el 1 de enero de 2020.`);
  const version = e.versiones.length;
  e.probadas.add(version);
  const r = probarSobrePasado(e, version, exchange, capital, desde, hasta);
  e.pruebas.unshift(r);
  if (e.estado === "borrador") e.estado = "probada";
  e.actualizada = Date.now();
  return json(r satisfies S["ResultadoPrueba"]);
}

const ESQUEMA: S["EsquemaEstrategia"] = {
  esquema: {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    title: "Estrategia a medida (formato 1)",
    type: "object",
    required: ["formato", "nombre", "monedas", "intervalo", "entrar", "salir", "tamano"],
    properties: {
      formato: { const: 1 },
      nombre: { type: "string", maxLength: 80 },
      monedas: { type: "array", items: { type: "string" }, minItems: 1 },
      intervalo: { enum: INTERVALOS },
      entrar: { $ref: "#/$defs/condicion" },
      salir: { $ref: "#/$defs/condicion" },
      tamano: { type: "object", properties: { fraccion: { type: "number", exclusiveMinimum: 0, maximum: 1 }, reparto: { enum: ["una", "igual", "volatilidad"] }, maximo_por_moneda: { type: "number" } } },
      riesgo: { type: "object", properties: { stop_perdida: { type: ["number", "null"] }, toma_beneficio: { type: ["number", "null"] }, stop_que_sigue: { type: ["number", "null"] } } },
      explicacion: { type: "string" },
      autor: { enum: ["claude", "marcos"] },
    },
  },
  ejemplos: [definicionDe("Cruce de medias de Bitcoin en 4 h", ["BTC"], "4h", "cruce", 1, null, "marcos", "Está en Bitcoin mientras su media rápida va por encima de la lenta.")],
  explicacion:
    "Una estrategia es un JSON cerrado: monedas, intervalo de las velas, una condición para entrar y otra para salir (con indicadores como sma, ema, rsi, retorno, maximo, minimo, volatilidad, atr o volumen_medio, comparados con >, <, >=, <=, cruza_arriba o cruza_abajo, y combinados con y, o, no), el tamaño (qué parte del capital) y el riesgo (stops). No admite código ni expresiones libres: el motor lo interpreta, no lo ejecuta.",
};

async function disenar(m: MundoV4, o: Objeto): Promise<Response> {
  if (m.escenario === "sin-claude") {
    await esperar(800);
    return fallo(422, "No encuentro el programa `claude` en este ordenador. Instala Claude Code y entra con tu cuenta (`claude login`): sin él no se puede diseñar con Claude. Lo demás del panel funciona igual.");
  }
  const mensaje = (texto(o, "mensaje") ?? "").trim();
  if (!mensaje) return fallo(422, "Escribe qué quieres que haga la estrategia.");
  const pedida = texto(o, "sesion");
  let s: SesionMock | undefined;
  if (pedida) {
    s = m.sesiones.get(pedida);
    if (!s) return fallo(404, "Esa conversación ya no existe (puede que se borrara la carpeta medida/). Empieza otra.");
  } else {
    s = { id: `dis-${Date.now().toString(36)}`, historial: [], estrategia: null, herramientas: [], turnos: 0 };
    m.sesiones.set(s.id, s);
  }
  // Un turno de verdad tarda de unos segundos a un par de minutos; aqui, de 7 a 12 s.
  await esperar(7000 + Math.random() * 5000);
  const ahora = Date.now();
  s.historial.push({ autor: "marcos", texto: mensaje, at: iso(ahora - 9000) });
  s.turnos++;
  let respuesta: string;
  let herramientas: string[];
  let estrategia: string | null = null;
  const pide = mensaje.toLowerCase();
  const e = s.estrategia ? m.estrategias.get(s.estrategia) : undefined;
  if (/dinero real|activa|en real|límite|limite/.test(pide)) {
    herramientas = ["bots"];
    respuesta =
      "Eso no lo puedo hacer: **ni activar dinero real ni subir límites**. El conector no tiene esas herramientas a propósito.\n\n" +
      "Lo que sí puedo hacer es desplegarla con dinero ficticio. Cuando lleve unos días (se recomiendan 7), la activas tú desde la ficha del bot, con sus límites y escribiendo `ACTIVAR <nombre del bot>`.";
  } else if (e && /ficticio|despliega|desplegar|bot/.test(pide)) {
    herramientas = ["desplegar_ficticio", "bots"];
    estrategia = e.id;
    const nombreBot = `${e.nombre.split(" ").slice(0, 3).join(" ")} · ficticio`;
    const bot = desplegador ? desplegador({ id: e.id, nombre: e.nombre, monedas: e.monedas, diasFicticio: e.diasFicticio, ultima: e.pruebas[0] ?? null }, nombreBot, 1000) : null;
    if (bot) anotarBotEstrategia(e.id, bot, "ficticio");
    respuesta =
      `Desplegada como bot **${nombreBot}** con 1.000 USDC **ficticios**, a precios en vivo. Lo verás en Bots.\n\n` +
      "- Solo opera mientras el panel está abierto.\n- Si en una semana va bien y quieres usar dinero real, eso lo haces tú desde su ficha: yo no puedo.";
  } else if (e) {
    herramientas = ["validar", "guardar", "probar"];
    estrategia = e.id;
    const version = e.versiones.length + 1;
    e.versiones.push({ version, at: iso(ahora), huella: huella(`${e.id}:${version}:${mensaje}`), nota: `A petición tuya: «${mensaje.slice(0, 80)}${mensaje.length > 80 ? "…" : ""}».` });
    e.probadas.add(version);
    e.tamano = Math.max(0.2, e.tamano - 0.1);
    const hasta = Math.floor(ahora / DIA_MS) * DIA_MS;
    const r = probarSobrePasado(e, version, "binance", 1000, hasta - 365 * DIA_MS, hasta);
    e.pruebas.unshift(r);
    e.actualizada = ahora;
    respuesta = textoResultado(e.nombre, r, e.monedas, true).replace("Hecho: nueva versión que entra con la mitad del capital.", `Hecho: versión ${version}, con el cambio que pedías.`);
  } else {
    herramientas = ["esquema", "monedas", "velas", "validar", "guardar", "probar"];
    const coin = (["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "HYPE"] as const).find((c) => pide.includes(c.toLowerCase()) || pide.includes((MONEDAS[c]?.nombre ?? "").toLowerCase())) ?? "ETH";
    const nombre = `Rebote de ${coin} desde su mínimo de 30 días`;
    const pedido = /(\d+(?:[.,]\d+)?)\s*%/.exec(mensaje);
    const stop = pedido ? Number((pedido[1] ?? "8").replace(",", ".")) : 8;
    const id = `rebote-${coin.toLowerCase()}-${m.siguiente++}`;
    const nueva = crearEstrategia(
      {
        id,
        nombre,
        autor: "claude",
        estado: "probada",
        monedas: [coin],
        intervalo: "4h",
        regla: "rebote",
        tamano: 1,
        stop: stop / 100,
        mantener: [coin === "BTC" ? 0.42 : coin === "ETH" ? 0.31 : 0.18],
        explicacion: `Compra ${MONEDAS[coin]?.nombre ?? coin} cuando rebota desde cerca de su mínimo de 30 días y vende si cae por debajo de su media de 20 velas o pierde un ${stop.toLocaleString("es-ES")} %.`,
        reglas: [
          "Entra con todo el capital cuando el precio está a menos de un 5 % de su mínimo de 30 días y cruza por encima de su media de 5 velas.",
          "Sale cuando el precio cae por debajo de su media de 20 velas.",
          `Stop de pérdida: vende si pierde un ${stop.toLocaleString("es-ES")} % desde la compra.`,
          "Decide solo con velas de 4 horas ya cerradas.",
        ],
        notas: [`Primera versión, a partir de: «${mensaje.slice(0, 80)}${mensaje.length > 80 ? "…" : ""}».`],
        probadas: 1,
        bots: [],
        diasFicticio: 0,
      },
      ahora,
    );
    m.estrategias.set(id, nueva);
    s.estrategia = id;
    estrategia = id;
    respuesta = textoResultado(nombre, nueva.pruebas[0], [coin], false);
  }
  s.historial.push({ autor: "claude", texto: respuesta, at: iso(Date.now()) });
  s.herramientas = herramientas;
  if (estrategia) s.estrategia = estrategia;
  return json({ sesion: s.id, respuesta, estrategia, herramientas, historial: s.historial } satisfies S["RespuestaDiseno"]);
}

// -- Operar → Hyperliquid (docs/panel-v5.md): la cuenta de verdad, de ejemplo ----------------------

const PRECIOS_HL: Record<string, number> = { BTC: 81_600, ETH: 2_390, SOL: 102.8, PURR: 0.21, HYPE: 79.1 };
const saldosHL: Record<string, number> = { USDC: 1_000, SOL: 0.5 };
const abiertasHL: S["OrdenAbiertaReal"][] = [];

function operarReal(m: MundoV4, coin: string): S["EstadoOperarReal"] {
  const x = m.exchanges.get("hyperliquid");
  const red = x && x.activo !== "sin_conectar" ? x.activo : null;
  const base: S["EstadoOperarReal"] = {
    exchange: "hyperliquid",
    nombre: "Hyperliquid",
    red,
    conectado: red !== null,
    que_falta: red === null ? ["Hyperliquid no está conectado: actívalo en Conexiones."] : [],
    coin,
    mercado: null,
    aviso: null,
    saldo: [],
    ordenes_abiertas: [],
    at: iso(Date.now()),
  };
  if (red === null) return base;
  const tiene = coin in PRECIOS_HL;
  return {
    ...base,
    mercado: tiene
      ? { par: `${coin}/USDC`, base: coin, cotizada: "USDC", minimo_importe: "10", minimo_cantidad: null, paso_cantidad: coin === "BTC" ? "0.00001" : "0.01", paso_precio: "0.01", comision_tomador: "0.00045" }
      : null,
    aviso: tiene ? null : `Hyperliquid no tiene mercado de contado de ${coin} en su red de pruebas: aquí solo se opera al contado (sin apalancamiento). Elige otra moneda.`,
    saldo: Object.entries(saldosHL)
      .filter(([, v]) => v > 0)
      .map(([moneda, v]) => ({ moneda, cantidad: String(Number(v.toFixed(6))) })),
    ordenes_abiertas: abiertasHL.filter((o) => o.par.startsWith(`${coin}/`)),
  };
}

function ordenReal(m: MundoV4, o: Objeto): Response {
  const e = operarReal(m, texto(o, "coin") ?? "BTC");
  if (!e.conectado || !e.red) return fallo(409, "Hyperliquid no está conectado: conéctalo en Conexiones antes de operar.");
  if (texto(o, "red") !== e.red) return fallo(409, "La pantalla mostraba otra red: no se ha enviado nada. Recarga y vuelve a mirar.");
  const cantidad = Number(texto(o, "cantidad"));
  const escrito = (texto(o, "escrito") ?? "").replace(/\./g, "").replace(",", ".");
  if (Number(escrito) !== cantidad) return fallo(422, `Lo escrito no coincide con la cantidad (${cantidad}): no se ha enviado nada.`);
  if (!e.mercado) return fallo(422, e.aviso ?? "Sin mercado.");
  const coin = e.mercado.base;
  const lado = texto(o, "lado") === "venta" ? "venta" : "compra";
  const precio = texto(o, "tipo") === "limite" ? Number(texto(o, "precio")) : (PRECIOS_HL[coin] ?? 1);
  const id = `ill${Math.random().toString(16).slice(2, 14)}`;
  const comun = { id_cliente: id, par: e.mercado.par, lado, red: e.red, cantidad: String(cantidad), comision_moneda: "USDC" } as const;
  if (texto(o, "tipo") === "limite") {
    abiertasHL.push({ id_cliente: id, par: e.mercado.par, lado, tipo: "limite", cantidad: String(cantidad), ejecutada: "0", precio: String(precio), at: iso(Date.now()) });
    return json({ ...comun, estado: "abierta", texto: `Orden puesta en Hyperliquid (red de pruebas): ${lado === "compra" ? "comprar" : "vender"} ${cantidad} ${coin} a ${precio} USDC. Sigue abierta hasta que se ejecute o la canceles.`, ejecutada: "0", precio_medio: String(precio), comision: null, anotada: false } satisfies S["ResultadoOrdenReal"]);
  }
  const importe = cantidad * precio;
  const comision = importe * 0.00045;
  saldosHL.USDC = (saldosHL.USDC ?? 0) + (lado === "compra" ? -(importe + comision) : importe - comision);
  saldosHL[coin] = (saldosHL[coin] ?? 0) + (lado === "compra" ? cantidad : -cantidad);
  return json({
    ...comun,
    estado: "ejecutada",
    texto: `${lado === "compra" ? "Compraste" : "Vendiste"} ${String(cantidad).replace(".", ",")} ${coin} a ${String(precio).replace(".", ",")} USDC (red de pruebas). Comisión: ${comision.toFixed(4).replace(".", ",")} USDC.`,
    ejecutada: String(cantidad),
    precio_medio: String(precio),
    comision: comision.toFixed(6),
    anotada: true,
  } satisfies S["ResultadoOrdenReal"]);
}

const USOS_CLAUDE = ["Pregunta", "Mi plan", "Diseñar con Claude", "El conector de Claude (MCP)"];

function estadoClaude(m: MundoV4): S["EstadoClaude"] {
  const conectado = m.escenario !== "sin-claude" || m.claudeConectado === true;
  return { instalado: true, conectado, con_suscripcion: conectado, plan: conectado ? "Max" : null, aviso: null, usos: USOS_CLAUDE };
}

export async function responderV4(peticion: Request, url: URL): Promise<Response> {
  const m = elMundo();
  const ruta = url.pathname;
  const metodo = peticion.method.toUpperCase();
  await esperar(120 + Math.random() * 200);

  switch (`${metodo} ${ruta}`) {
    // Claude con tu suscripción (docs/panel-v5.md): conectado salvo en «sin-claude»; conectar lo deja
    // conectado a los pocos segundos, como si se hubiera iniciado sesión en la ventana.
    case "GET /api/claude":
      return json(estadoClaude(m) satisfies S["EstadoClaude"]);
    case "POST /api/claude/conectar": {
      if (estadoClaude(m).con_suscripcion) return fallo(409, "Claude ya está conectado con tu suscripción Max.");
      window.setTimeout(() => {
        m.claudeConectado = true;
      }, 6000);
      return json({
        abierto: true,
        texto: "Se ha abierto una ventana de Claude Code en este equipo: sigue sus pasos (abre tu navegador para elegir la cuenta) y vuelve aquí. Esta página se entera sola.",
      } satisfies S["ConectarClaude"]);
    }
    case "GET /api/operar/hyperliquid":
      return json(operarReal(m, url.searchParams.get("coin") ?? "BTC") satisfies S["EstadoOperarReal"]);
    case "POST /api/operar/hyperliquid/ordenes":
      return ordenReal(m, await cuerpo(peticion));
    case "GET /api/conexiones":
      return json(conexiones(m) satisfies S["Conexiones"]);
    case "GET /api/conexiones/disponibles":
      return json(DISPONIBLES satisfies S["ExchangeDisponible"][]);
    case "GET /api/medida":
      return json({ estrategias: [...m.estrategias.values()].sort((a, b) => b.actualizada - a.actualizada).map(resumen) } satisfies S["Estrategias"]);
    case "POST /api/medida":
      return guardar(m, await cuerpo(peticion));
    case "GET /api/medida/esquema":
      return json(ESQUEMA satisfies S["EsquemaEstrategia"]);
    case "POST /api/medida/disenar":
      return disenar(m, await cuerpo(peticion));
    default:
      break;
  }

  const claves = /^\/api\/conexiones\/([^/]+)\/claves\/([^/]+)$/.exec(ruta);
  if (claves) {
    const id = decodeURIComponent(claves[1] ?? "");
    const r = decodeURIComponent(claves[2] ?? "");
    if (!esRed(r)) return fallo(422, "La red tiene que ser «pruebas» o «real».");
    if (metodo === "PUT") {
      await esperar(300);
      return guardarClaves(m, id, r, await cuerpo(peticion));
    }
    if (metodo === "DELETE") return borrarClaves(m, id, r);
  }
  const probarClaves = /^\/api\/conexiones\/([^/]+)\/probar\/([^/]+)$/.exec(ruta);
  if (probarClaves && metodo === "POST") {
    const r = decodeURIComponent(probarClaves[2] ?? "");
    if (!esRed(r)) return fallo(422, "La red tiene que ser «pruebas» o «real».");
    await esperar(1100);
    return probar(m, decodeURIComponent(probarClaves[1] ?? ""), r);
  }
  const activarRuta = /^\/api\/conexiones\/([^/]+)\/activar$/.exec(ruta);
  if (activarRuta && metodo === "POST") return activar(m, decodeURIComponent(activarRuta[1] ?? ""), await cuerpo(peticion));
  const mercadosRuta = /^\/api\/conexiones\/([^/]+)\/mercados$/.exec(ruta);
  if (mercadosRuta && metodo === "GET") {
    const r = url.searchParams.get("red") ?? "real";
    if (!esRed(r)) return fallo(422, "La red tiene que ser «pruebas» o «real».");
    return mercados(decodeURIComponent(mercadosRuta[1] ?? ""), r);
  }

  const sesion = /^\/api\/medida\/disenar\/([^/]+)$/.exec(ruta);
  if (sesion && metodo === "GET") {
    const s = m.sesiones.get(decodeURIComponent(sesion[1] ?? ""));
    if (!s) return fallo(404, "Esa conversación ya no existe (puede que se borrara la carpeta medida/). Empieza otra.");
    const ultima = [...s.historial].reverse().find((x) => x.autor === "claude");
    return json({ sesion: s.id, respuesta: ultima?.texto ?? "", estrategia: s.estrategia, herramientas: s.herramientas, historial: s.historial } satisfies S["RespuestaDiseno"]);
  }
  const probarEstrategia = /^\/api\/medida\/([^/]+)\/probar$/.exec(ruta);
  if (probarEstrategia && metodo === "POST") {
    await esperar(1800 + Math.random() * 1500);
    return probarRuta(m, decodeURIComponent(probarEstrategia[1] ?? ""), await cuerpo(peticion));
  }
  const una = /^\/api\/medida\/([^/]+)$/.exec(ruta);
  if (una) {
    const id = decodeURIComponent(una[1] ?? "");
    const e = m.estrategias.get(id);
    if (!e) return fallo(404, "No hay ninguna estrategia con ese id: puede que la hayas borrado.");
    if (metodo === "GET") return json(detalle(e) satisfies S["DetalleEstrategia"]);
    if (metodo === "DELETE") {
      if (e.bots.length) return fallo(409, `No se puede borrar: la usa${e.bots.length > 1 ? "n" : ""} ${e.bots.length} bot${e.bots.length > 1 ? "s" : ""}. Borra antes ${e.bots.length > 1 ? "esos bots" : "ese bot"}.`);
      m.estrategias.delete(id);
      return new Response(null, { status: 204 });
    }
  }

  return fallo(404, `Ruta de ejemplo no definida: ${metodo} ${ruta}`);
}
