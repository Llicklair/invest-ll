/**
 * El catalogo de estrategias de ejemplo (docs/panel-v2.md, seccion 5) y sus calculos de
 * juguete: curvas, historico desde 10.000, "tus numeros" desde un ano y la recomendacion.
 *
 * Las curvas se calculan sobre los historicos INVENTADOS de series.ts con reglas parecidas a las
 * del motor (60/40 mensual, filtros de tendencia, mantener), asi que salen con formas y ordenes
 * de magnitud creibles, pero NO son las cifras del estudio. Los textos son los de la spec.
 */
import type { components } from "@/api/esquema";

import { serie } from "./series";

type S = components["schemas"];

export type Escasez = "ninguna" | "sin-cripto";

interface Def {
  clave: string;
  nombre: string;
  frase: string;
  para_quien: string;
  mercado: "bolsa" | "cripto";
  ejecucion: "binance" | "broker";
  riesgo: 1 | 2 | 3 | 4 | 5;
  como_funciona: string[];
  avisos: string[];
  evidencia: S["Evidencia"];
  activos: string[];
  laboratorio: boolean;
  retirada: boolean;
}

const RIESGO = ["Tranquila", "Suave", "Moderada", "Movida", "Muy movida"] as const;

const AVISOS_BOLSA = [
  "Las cifras usan fondos de EE.UU.; desde España se compran sus versiones europeas (UCITS), que se comportan casi igual.",
  "Sin contar el cambio euro-dólar.",
];
const AVISO_CRIPTO = "En dólares digitales (USDT).";
const PASADO: S["Evidencia"] = { tipo: "pasado", desde: null, texto: "Probada sobre el pasado" };

export const DEFS: Def[] = [
  {
    clave: "bolsa-equilibrada",
    nombre: "Equilibrada",
    frase: "Seis partes de bolsa de EE.UU. y cuatro de bonos del Estado. Cada mes se vuelve a ese reparto.",
    para_quien: "Para dinero que no vas a necesitar en al menos cinco años, si una caída te pondría nervioso pero no te haría vender.",
    mercado: "bolsa",
    ejecucion: "broker",
    riesgo: 3,
    como_funciona: [
      "Cada mes repartes tu aportación: unos 60 de cada 100 € a un fondo de bolsa de EE.UU. y 40 a uno de bonos del Estado.",
      "Los bonos suelen aguantar cuando la bolsa cae, así que el conjunto se mueve bastante menos que la bolsa sola.",
      "No hace falta vender nada: aportar siempre al reparto objetivo va corrigiendo el equilibrio solo.",
    ],
    avisos: [...AVISOS_BOLSA],
    evidencia: PASADO,
    activos: ["Bolsa de EE.UU.", "Bonos de EE.UU. a 7-10 años"],
    laboratorio: false,
    retirada: false,
  },
  {
    clave: "bolsa-prudente",
    nombre: "Prudente con freno",
    frase: "Reparte entre bolsa, bonos, oro y otros fondos, y se sale a liquidez de lo que va cuesta abajo.",
    para_quien: "Para quien dormiría mal viendo su dinero caer un 30 %, aunque eso suponga ganar menos.",
    mercado: "bolsa",
    ejecucion: "broker",
    riesgo: 2,
    como_funciona: [
      "Reparte el dinero entre ocho fondos (bolsa, bonos, oro, materias primas…) según cuánto se mueve cada uno: lo más movido lleva menos.",
      "Cada mes mira si cada fondo va hacia arriba o hacia abajo en los últimos meses.",
      "Lo que va hacia abajo se cambia por bonos a corto plazo hasta que vuelve a subir.",
    ],
    avisos: ["Cae mucho menos, pero también crece aproximadamente la mitad.", ...AVISOS_BOLSA],
    evidencia: PASADO,
    activos: ["Bolsa de EE.UU.", "Bolsa de otros países", "Bonos", "Oro", "Materias primas", "Inmobiliario"],
    laboratorio: false,
    retirada: false,
  },
  {
    clave: "bolsa-eeuu",
    nombre: "Bolsa de EE.UU.",
    frase: "Las 500 mayores empresas de EE.UU. en un solo fondo, y no tocarlo.",
    para_quien: "Para dinero que no vas a tocar en más de diez años, si ver una caída a la mitad no te haría vender.",
    mercado: "bolsa",
    ejecucion: "broker",
    riesgo: 4,
    como_funciona: [
      "Cada mes compras un fondo que lleva dentro las 500 mayores empresas de EE.UU.",
      "No se vende nunca: ni cuando cae ni cuando sube.",
      "Es lo más sencillo y, con muchos años por delante, lo que más ha crecido de las tres de bolsa. También lo que más cae.",
    ],
    avisos: [...AVISOS_BOLSA],
    evidencia: PASADO,
    activos: ["Bolsa de EE.UU."],
    laboratorio: false,
    retirada: false,
  },
  {
    clave: "btc-freno",
    nombre: "Bitcoin con freno",
    frase: "Bitcoin cuando sube, liquidez cuando baja. Lo decide una regla cada semana, no una corazonada.",
    para_quien: "Para una parte pequeña de tus ahorros, si quieres algo de bitcoin pero no aguantarías verlo caer un 80 %.",
    mercado: "cripto",
    ejecucion: "binance",
    riesgo: 4,
    como_funciona: [
      "Cada semana mira si el precio del bitcoin está por encima de su media del último mes.",
      "Si lo está, se queda en bitcoin; si no, pasa a dólares digitales (USDT) y espera.",
      "El panel prepara cada orden en Binance y tú la confirmas escribiendo la cantidad.",
    ],
    avisos: [
      "Pasa casi la mitad del tiempo fuera, en liquidez: habrá años en que lo haga peor que tener Bitcoin quieto.",
      AVISO_CRIPTO,
    ],
    evidencia: { tipo: "prueba_real", desde: "2026-10-15", texto: "En prueba real desde el 15 oct 2026" },
    activos: ["Bitcoin", "Dólares digitales (USDT)"],
    laboratorio: false,
    retirada: false,
  },
  {
    clave: "cripto-cesta-freno",
    nombre: "Cesta cripto con freno",
    frase: "Las criptomonedas grandes que mejor van, repartidas, y fuera de todas cuando el mercado cae.",
    para_quien: "Para quien ya entiende la cripto y acepta que haga muchas operaciones.",
    mercado: "cripto",
    ejecucion: "binance",
    riesgo: 4,
    como_funciona: [
      "Cada semana elige las monedas grandes que mejor van en las últimas semanas y reparte entre ellas.",
      "Si el mercado cripto en conjunto va hacia abajo, lo pasa todo a dólares digitales (USDT).",
      "Solo cambia el reparto cuando se aleja más de un 2 % del objetivo, para no operar de más.",
    ],
    avisos: [
      "Se diseñó después de ver los primeros resultados: su historia es más bonita de lo que probablemente será su futuro.",
      "Hace muchas operaciones: los impuestos se comen una parte visible.",
      AVISO_CRIPTO,
    ],
    evidencia: { tipo: "prueba_real", desde: "2026-10-12", texto: "En prueba real desde el 12 oct 2026" },
    activos: ["Bitcoin", "Ethereum", "Solana", "Dólares digitales (USDT)"],
    laboratorio: false,
    retirada: false,
  },
  {
    clave: "btc-mantener",
    nombre: "Bitcoin y olvidarse",
    frase: "Comprar bitcoin y no venderlo, pase lo que pase.",
    para_quien: "Solo con dinero que puedas olvidar durante años.",
    mercado: "cripto",
    ejecucion: "binance",
    riesgo: 5,
    como_funciona: [
      "Cada mes compras bitcoin con tu aportación.",
      "No se vende nunca.",
      "Lo que valga dependerá por completo del precio del bitcoin el día que lo necesites.",
    ],
    avisos: ["Ha llegado a perder más del 80 %. Solo con dinero que puedas olvidar.", AVISO_CRIPTO],
    evidencia: PASADO,
    activos: ["Bitcoin"],
    laboratorio: false,
    retirada: false,
  },
  {
    clave: "cripto-prerregistrada",
    nombre: "Cartera cripto prerregistrada",
    frase: "Momentum diversificado sobre las 20 monedas más líquidas, fijado antes de ver resultados.",
    para_quien: "Para estudiarla: es la referencia contra la que se miden las demás de cripto.",
    mercado: "cripto",
    ejecucion: "binance",
    riesgo: 4,
    como_funciona: [
      "Cada semana ordena las 20 monedas más líquidas por cómo van en los últimos meses.",
      "Reparte por riesgo, con un máximo del 35 % por moneda y un objetivo de volatilidad del 60 %.",
      "Decide en siete tramos para no entrar ni salir de golpe.",
    ],
    avisos: ["Incluye las monedas que luego murieron: sus cifras no tienen sesgo de supervivencia.", AVISO_CRIPTO],
    evidencia: { tipo: "prueba_real", desde: "2026-10-03", texto: "En prueba real desde el 3 oct 2026" },
    activos: ["Las 20 criptomonedas más líquidas", "Dólares digitales (USDT)"],
    laboratorio: true,
    retirada: false,
  },
  {
    clave: "bolsa-todo-tiempo",
    nombre: "Todo tiempo",
    frase: "Algo de bolsa, muchos bonos y oro: pensada para cualquier clima económico.",
    para_quien: "Del estudio de fondos: para compararla con Equilibrada.",
    mercado: "bolsa",
    ejecucion: "broker",
    riesgo: 2,
    como_funciona: [
      "Treinta partes de bolsa, cincuenta y cinco de bonos y quince de oro.",
      "Cada mes se vuelve a ese reparto.",
      "Sufre menos en las caídas de la bolsa y más cuando suben los tipos de interés.",
    ],
    avisos: [...AVISOS_BOLSA],
    evidencia: PASADO,
    activos: ["Bolsa de EE.UU.", "Bonos de EE.UU.", "Oro"],
    laboratorio: true,
    retirada: false,
  },
  {
    clave: "rotacion-etf",
    nombre: "Rotación entre fondos (retirada)",
    frase: "Todo al fondo que mejor fue los últimos tres meses, y cambiar cada mes.",
    para_quien: "Nadie: se conserva para que se vea por qué se retiró.",
    mercado: "bolsa",
    ejecucion: "broker",
    riesgo: 4,
    como_funciona: [
      "Cada mes mira qué fondo subió más en los últimos tres meses.",
      "Vende lo que tenía y lo pone todo en ese.",
      "Repite al mes siguiente.",
    ],
    avisos: ["Retirada: sin el sesgo de supervivencia se fue casi a cero.", ...AVISOS_BOLSA],
    evidencia: PASADO,
    activos: ["Bolsa de EE.UU.", "Bonos", "Oro", "Energía"],
    laboratorio: true,
    retirada: true,
  },
];

export function definicion(clave: string): Def | undefined {
  return DEFS.find((d) => d.clave === clave);
}

// -- Curvas -------------------------------------------------------------------------------------

interface Curva {
  fechas: string[];
  valores: number[];
  dentro: number;
  operaciones: number;
}

const COSTE = 0.0015;
const cacheCurvas = new Map<string, Curva>();

function cierres(simbolo: string, fechas: readonly string[]): number[] {
  const s = serie(simbolo);
  if (!s) return fechas.map(() => 1);
  const indice = new Map(s.fechas.map((f, i) => [f, s.cierres[i] ?? 0]));
  let ultimo = s.cierres[0] ?? 1;
  return fechas.map((f) => {
    const v = indice.get(f);
    if (v !== undefined) ultimo = v;
    return ultimo;
  });
}

function sma(c: readonly number[], i: number, k: number): number | null {
  if (i + 1 < k) return null;
  let s = 0;
  for (let j = i - k + 1; j <= i; j++) s += c[j] ?? 0;
  return s / k;
}

const mes = (f: string) => f.slice(0, 7);

/** Reparto fijo `pesos` rebalanceado cada mes, con un filtro opcional por activo. */
function cartera(simbolos: string[], pesos: number[], filtro: number | null): Curva {
  const base = serie("SPY");
  const fechas = (base?.fechas ?? []).slice(filtro ?? 0);
  const todos = simbolos.map((s) => cierres(s, base?.fechas ?? []).slice(filtro ?? 0));
  const completos = simbolos.map((s) => cierres(s, base?.fechas ?? []));
  const valores: number[] = [10000];
  let partes = pesos.map((p) => p * 10000);
  let dentro = 0;
  let operaciones = 0;
  let estado = simbolos.map(() => true);
  for (let i = 1; i < fechas.length; i++) {
    partes = partes.map((v, k) => {
      if (!estado[k]) return v * (1 + 0.035 / 252);
      const c = todos[k] ?? [];
      return v * ((c[i] ?? 1) / (c[i - 1] ?? 1));
    });
    let total = partes.reduce((a, b) => a + b, 0);
    const f = fechas[i] ?? "";
    if (mes(f) !== mes(fechas[i - 1] ?? "")) {
      const nuevo = simbolos.map((_, k) => {
        if (filtro === null) return true;
        const c = completos[k] ?? [];
        const j = i + filtro;
        const m = sma(c, j - 1, 200);
        return m === null ? true : (c[j - 1] ?? 0) > m;
      });
      const cambios = nuevo.filter((x, k) => x !== estado[k]).length;
      operaciones += cambios + 1;
      estado = nuevo;
      total *= 1 - COSTE * (cambios ? 0.3 : 0.02);
      partes = pesos.map((p) => p * total);
    }
    if (estado.some(Boolean)) dentro++;
    valores.push(total);
  }
  return { fechas, valores, dentro: dentro / Math.max(1, fechas.length - 1), operaciones };
}

/**
 * Un activo con o sin filtro de tendencia semanal (dentro si cierra por encima de su media).
 *
 * El filtro decide el tiempo dentro y las operaciones, pero la CURVA no sale de el: sobre un paseo
 * aleatorio con tendencias limpias entre anclas, el filtro acertaria demasiado y daria cifras
 * increibles (x180 en ocho anos). Se modela como la del activo "amortiguada" (indice^exponente):
 * crece menos y cae menos, que es lo que el estudio midio en datos reales (peor caida -65 % con
 * freno frente a -81 % sin el). Son datos de ejemplo: forma creible, no cifras del estudio.
 */
function conFreno(simbolos: string[], k: number | null, banda = 0, exponente = 1): Curva {
  const base = serie(simbolos[0] ?? "BTC/USDT");
  const fechasTodas = base?.fechas ?? [];
  const series = simbolos.map((s) => cierres(s, fechasTodas));
  const inicioDe = simbolos.map((s) => serie(s)?.fechas[0] ?? "9999");
  // Indice de la cesta (o del activo), repartido por igual entre lo que exista ese dia.
  const indice: number[] = [1];
  for (let i = 1; i < fechasTodas.length; i++) {
    const f = fechasTodas[i] ?? "";
    const vivos = series.map((c, j) => ({ r: (c[i] ?? 1) / (c[i - 1] ?? 1), j })).filter(({ j }) => (inicioDe[j] ?? "") < f);
    const r = vivos.length ? vivos.reduce((a, b) => a + b.r, 0) / vivos.length : 1;
    indice.push((indice[i - 1] ?? 1) * r);
  }
  const arranque = k ?? 0;
  const fechas = fechasTodas.slice(arranque);
  const valores: number[] = [10000];
  let dentroAhora = true;
  let dias = 0;
  let operaciones = 0;
  for (let i = 1; i < fechas.length; i++) {
    const j = i + arranque;
    const prev = valores[i - 1] ?? 10000;
    const r = (indice[j] ?? 1) / (indice[j - 1] ?? 1);
    const v = dentroAhora ? prev * r : prev * (1 + 0.03 / 365);
    valores.push(v);
    if (dentroAhora) dias++;
    void prev;
    if (k !== null && i % 7 === 0) {
      const m = sma(indice, j, k);
      if (m !== null) {
        const c = indice[j] ?? 0;
        const quiere: boolean = dentroAhora ? c > m * (1 - banda) : c > m * (1 + banda);
        if (quiere !== dentroAhora) {
          dentroAhora = quiere;
          operaciones += simbolos.length;
          void v;
        }
      }
    }
  }
  const base0 = indice[arranque] ?? 1;
  const amortiguada = fechas.map((_, i) => 10000 * ((indice[i + arranque] ?? base0) / base0) ** exponente);
  return { fechas, valores: k === null ? valores : amortiguada, dentro: k === null ? 1 : dias / Math.max(1, fechas.length - 1), operaciones: Math.max(1, operaciones) };
}

function rotacion(): Curva {
  const base = serie("SPY");
  const fechas = (base?.fechas ?? []).slice(63);
  const simbolos = ["SPY", "TLT", "GLD", "XLE"];
  const c = simbolos.map((s) => cierres(s, base?.fechas ?? []));
  const valores = [10000];
  let elegido = 0;
  let operaciones = 0;
  for (let i = 1; i < fechas.length; i++) {
    const j = i + 63;
    const serieElegida = c[elegido] ?? [];
    // La "trampa" de supervivencia del estudio: con los fondos que luego cerraron, se hunde.
    const lastre = 1 - 0.00055;
    valores.push((valores[i - 1] ?? 1) * ((serieElegida[j] ?? 1) / (serieElegida[j - 1] ?? 1)) * lastre);
    if (mes(fechas[i] ?? "") !== mes(fechas[i - 1] ?? "")) {
      let mejor = 0;
      let mejorR = -Infinity;
      c.forEach((x, k) => {
        const r = (x[j - 1] ?? 1) / (x[j - 64] ?? 1);
        if (r > mejorR) {
          mejorR = r;
          mejor = k;
        }
      });
      if (mejor !== elegido) operaciones += 2;
      elegido = mejor;
    }
  }
  return { fechas, valores, dentro: 1, operaciones };
}

export function curva(clave: string): Curva | null {
  const guardada = cacheCurvas.get(clave);
  if (guardada) return guardada;
  let c: Curva | null = null;
  switch (clave) {
    case "bolsa-equilibrada":
      c = cartera(["SPY", "IEF"], [0.6, 0.4], null);
      break;
    case "bolsa-prudente":
      c = cartera(["SPY", "IEF", "GLD", "XLV"], [0.2, 0.45, 0.2, 0.15], 200);
      break;
    case "bolsa-eeuu":
      c = cartera(["SPY"], [1], null);
      c.operaciones = 1;
      break;
    case "bolsa-todo-tiempo":
      c = cartera(["SPY", "TLT", "GLD"], [0.3, 0.55, 0.15], null);
      break;
    case "btc-freno":
      c = conFreno(["BTC/USDT"], 30, 0, 0.62);
      break;
    case "cripto-cesta-freno":
      c = conFreno(["BTC/USDT", "ETH/USDT", "SOL/USDT"], 20, 0.02, 0.45);
      c.operaciones *= 3;
      break;
    case "cripto-prerregistrada":
      c = conFreno(["BTC/USDT", "ETH/USDT", "SOL/USDT"], 50, 0, 0.55);
      break;
    case "btc-mantener":
      c = conFreno(["BTC/USDT"], null);
      break;
    case "rotacion-etf":
      c = rotacion();
      break;
    default:
      return null;
  }
  cacheCurvas.set(clave, c);
  return c;
}

// -- Cifras --------------------------------------------------------------------------------------

function peorCaida(valores: readonly number[], fechas: readonly string[]): { caida: number; fecha: string; racha: number } {
  let max = valores[0] ?? 1;
  let maxI = 0;
  let caida = 0;
  let fecha = fechas[0] ?? "";
  let racha = 0;
  for (let i = 1; i < valores.length; i++) {
    const v = valores[i] ?? 0;
    if (v >= max) {
      racha = Math.max(racha, i - maxI);
      max = v;
      maxI = i;
    }
    const d = v / max - 1;
    if (d < caida) {
      caida = d;
      fecha = fechas[i] ?? fecha;
    }
  }
  racha = Math.max(racha, valores.length - 1 - maxI);
  return { caida, fecha, racha };
}

function anios(desde: string, hasta: string): number {
  return (Date.parse(`${hasta}T00:00:00Z`) - Date.parse(`${desde}T00:00:00Z`)) / (365.25 * 86_400_000);
}

export function historico(clave: string): S["Historico"] | null {
  const c = curva(clave);
  if (!c || c.fechas.length < 2) return null;
  const desde = c.fechas[0] ?? "";
  const hasta = c.fechas[c.fechas.length - 1] ?? "";
  const final = c.valores[c.valores.length - 1] ?? 10000;
  const a = anios(desde, hasta);
  const p = peorCaida(c.valores, c.fechas);
  const diasPorAnio = c.fechas.length / Math.max(a, 0.1);
  return {
    desde,
    hasta,
    valor_final: Math.round(final * 100) / 100,
    crecimiento_anual: (final / 10000) ** (1 / Math.max(a, 0.1)) - 1,
    peor_caida: p.caida,
    peor_caida_fecha: p.fecha,
    peor_racha_anios: Math.round((p.racha / diasPorAnio) * 10) / 10,
    tiempo_invertido: Math.round(c.dentro * 100) / 100,
    operaciones_al_anio: Math.round((c.operaciones / Math.max(a, 0.1)) * 10) / 10,
  };
}

export function estrategia(d: Def, escasez: Escasez): S["Estrategia"] {
  const sinDatos = escasez === "sin-cripto" && d.mercado === "cripto";
  return {
    clave: d.clave,
    nombre: d.nombre,
    frase: d.frase,
    para_quien: d.para_quien,
    mercado: d.mercado,
    ejecucion: d.ejecucion,
    riesgo: d.riesgo,
    riesgo_texto: RIESGO[d.riesgo - 1] ?? "Moderada",
    como_funciona: d.como_funciona,
    avisos: d.avisos,
    evidencia: d.evidencia,
    activos: d.activos,
    laboratorio: d.laboratorio,
    retirada: d.retirada,
    disponible: !sinDatos,
    motivo: sinDatos ? "Faltan los datos de Binance para calcularla. Descárgalos con uv run invest-ll-quant download." : null,
    historico: sinDatos ? null : historico(d.clave),
  };
}

export function catalogo(escasez: Escasez): S["Catalogo"] {
  return {
    estrategias: DEFS.map((d) => estrategia(d, escasez)),
    nota: "Todas las cifras son del pasado y ya descuentan comisiones. El pasado no es una promesa: dice cómo se comportó cada estrategia, no cómo se comportará.",
  };
}

/** Los viernes entre dos fechas (para muestrear todas las estrategias en las mismas semanas). */
function viernes(desde: string, hasta: string): string[] {
  const salida: string[] = [];
  let t = Date.parse(`${desde}T00:00:00Z`);
  const fin = Date.parse(`${hasta}T00:00:00Z`);
  while (new Date(t).getUTCDay() !== 5) t += 86_400_000;
  for (; t <= fin; t += 7 * 86_400_000) salida.push(new Date(t).toISOString().slice(0, 10));
  return salida;
}

export function simular(clave: string, inicial: number, mensual: number, desdeAnio: number): S["ResultadoSimulado"] | null {
  const d = definicion(clave);
  const c = curva(clave);
  if (!d || !c) return null;
  const pedido = `${desdeAnio}-01-01`;
  let i0 = c.fechas.findIndex((f) => f >= pedido);
  if (i0 < 0) i0 = c.fechas.length - 1;
  const fechas = c.fechas.slice(i0);
  const valoresIndice = c.valores.slice(i0);
  let unidades = 0;
  let aportado = 0;
  const diario: { fecha: string; valor: number; aportado: number }[] = [];
  for (let i = 0; i < fechas.length; i++) {
    const f = fechas[i] ?? "";
    const precio = valoresIndice[i] ?? 1;
    if (i === 0) {
      unidades += inicial / precio;
      aportado += inicial;
    } else if (mes(f) !== mes(fechas[i - 1] ?? "")) {
      unidades += mensual / precio;
      aportado += mensual;
    }
    diario.push({ fecha: f, valor: unidades * precio, aportado });
  }
  const primero = diario[0];
  const ultimo = diario[diario.length - 1];
  if (!primero || !ultimo) return null;

  // El peor momento: cuando menos valia en relacion con lo puesto hasta entonces.
  let peor = primero;
  for (const p of diario) if (p.aportado > 0 && p.valor / p.aportado < peor.valor / Math.max(peor.aportado, 1)) peor = p;
  const caida = peorCaida(valoresIndice, fechas);
  const mesesDebajo = new Set(diario.filter((p) => p.valor < p.aportado - 0.005).map((p) => mes(p.fecha))).size;

  const porFecha = new Map(diario.map((p) => [p.fecha, p]));
  const puntos: S["PuntoSimulado"][] = [];
  let ultimoVisto = primero;
  let k = 0;
  for (const v of viernes(primero.fecha, ultimo.fecha)) {
    while (k < diario.length && (diario[k]?.fecha ?? "") <= v) {
      ultimoVisto = diario[k] ?? ultimoVisto;
      k++;
    }
    const p = porFecha.get(v) ?? ultimoVisto;
    puntos.push({ fecha: v, valor: Math.round(p.valor * 100) / 100, aportado: p.aportado });
  }
  const ultimoPunto = puntos[puntos.length - 1];
  if (!ultimoPunto || ultimoPunto.fecha !== ultimo.fecha) {
    puntos.push({ fecha: ultimo.fecha, valor: Math.round(ultimo.valor * 100) / 100, aportado: ultimo.aportado });
  }

  const aviso =
    primero.fecha.slice(0, 4) > String(desdeAnio)
      ? `Los datos de esta estrategia empiezan el ${primero.fecha}: se cuenta desde ahí.`
      : null;

  return {
    clave,
    nombre: d.nombre,
    desde: primero.fecha,
    hasta: ultimo.fecha,
    puntos,
    aportado: ultimo.aportado,
    valor_final: Math.round(ultimo.valor * 100) / 100,
    ganancia: Math.round((ultimo.valor - ultimo.aportado) * 100) / 100,
    peor_momento_fecha: peor.fecha,
    peor_momento_valor: Math.round(peor.valor * 100) / 100,
    peor_momento_aportado: peor.aportado,
    peor_caida: caida.caida,
    meses_por_debajo: mesesDebajo,
    aviso,
  };
}

// -- Recomendacion (docs/panel-v2.md, seccion 6) ---------------------------------------------------

const TEXTO_HORIZONTE: Record<S["Perfil"]["horizonte"], string> = {
  "menos-2": "en menos de 2 años",
  "2-5": "en 2 a 5 años",
  "5-10": "en 5 a 10 años",
  "mas-10": "en más de 10 años",
};

const TEXTO_CAIDA: Record<S["Perfil"]["ante_caida"], string> = {
  vender: "venderías para no perder más",
  esperar: "esperarías a que se recupere",
  comprar: "aprovecharías para poner más",
};

function reparto(importe: number, pct: number): string {
  return ((importe * pct) / 100).toFixed(2);
}

export function recomendar(p: S["Perfil"]): S["Recomendacion"] {
  const inicial = Number(p.inicial);
  const mensual = Number(p.mensual);
  const largo = p.horizonte === "5-10" || p.horizonte === "mas-10";
  const noInvertir = p.horizonte === "menos-2";
  const porQue: string[] = [];
  const avisos: string[] = ["Esto sale de reglas fijas aplicadas a tus respuestas, no de predecir el mercado."];

  let bolsa = "bolsa-equilibrada";
  if (noInvertir || p.ante_caida === "vender") bolsa = "bolsa-prudente";
  else if (p.ante_caida === "comprar" && largo) bolsa = "bolsa-eeuu";

  let cripto = 0;
  if (!noInvertir) {
    if (p.cripto === "poco") cripto = 5;
    if (p.cripto === "si") cripto = p.ante_caida === "comprar" && largo ? 15 : 10;
    if (p.ante_caida === "vender") cripto = Math.min(cripto, 5);
  }

  const nombre = (k: string) => definicion(k)?.nombre ?? k;
  if (noInvertir) {
    porQue.push(
      `Dijiste que necesitarás este dinero ${TEXTO_HORIZONTE[p.horizonte]}: en ese plazo, una caída no da tiempo a recuperarse.`,
      "Si aun así quieres invertir una parte, lo más tranquilo es Prudente con freno, y sin cripto.",
    );
  } else {
    porQue.push(
      `Porque lo necesitarás ${TEXTO_HORIZONTE[p.horizonte]} y dijiste que, si cayera a la mitad, ${TEXTO_CAIDA[p.ante_caida]}: ${nombre(bolsa)} encaja con eso.`,
    );
    if (cripto > 0) {
      porQue.push(
        `Pediste ${p.cripto === "poco" ? "un poco de" : ""} cripto: un ${cripto} % en Bitcoin con freno, que sale a liquidez cuando el bitcoin baja.`.replace("  ", " "),
      );
      avisos.push("Limitamos la cripto porque, incluso con freno, ha llegado a caer un 65 %.");
    } else if (p.cripto !== "no") {
      porQue.push("Sin cripto: con lo que contestaste sobre las caídas, no te la recomendamos.");
    } else {
      porQue.push("Sin cripto, como pediste.");
    }
    if (inicial === 0 && mensual === 0) porQue.push("No has puesto cifras: el reparto vale para cuando empieces.");
  }

  const partes: S["Parte"][] = [
    { estrategia: bolsa, nombre: nombre(bolsa), porcentaje: 100 - cripto, inicial: reparto(inicial, 100 - cripto), mensual: reparto(mensual, 100 - cripto) },
  ];
  if (cripto > 0) {
    partes.push({ estrategia: "btc-freno", nombre: nombre("btc-freno"), porcentaje: cripto, inicial: reparto(inicial, cripto), mensual: reparto(mensual, cripto) });
  }
  // Alternativas: las otras del mismo mercado que cada parte.
  const mercados = new Set(partes.map((x) => definicion(x.estrategia)?.mercado));
  const alternativas = DEFS.filter(
    (d) => !d.laboratorio && mercados.has(d.mercado) && !partes.some((x) => x.estrategia === d.clave),
  ).map((d) => d.clave);
  return { no_invertir: noInvertir, partes, por_que: porQue, avisos, alternativas };
}
