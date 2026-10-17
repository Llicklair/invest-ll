/**
 * Calculos de juguete para que los ejemplos respondan a lo que se pide (otra estrategia, otro
 * plazo...). NO es el motor de INVEST LL: es lo justo para que las respuestas tengan la forma y
 * los ordenes de magnitud de las de verdad. Aqui se usa float sin miedo porque estas cifras son
 * inventadas; los importes salen como cadena, igual que en la API.
 */
import type { components } from "@/api/esquema";

type S = components["schemas"];

export const dinero = (v: number): string => v.toFixed(2);

export interface Operacion {
  entrada: string;
  precioEntrada: number;
  salida: string | null;
  precioSalida: number | null;
  motivo: string;
  resultado: number;
}

export interface Simulacion {
  curva: { fecha: string; valor: number }[];
  operaciones: Operacion[];
  costes: number;
}

/** Media movil simple de los `k` cierres que acaban en `i` (incluido). */
export function media(cierres: readonly number[], i: number, k: number): number | null {
  if (i + 1 < k) return null;
  let s = 0;
  for (let j = i - k + 1; j <= i; j++) s += cierres[j] ?? 0;
  return s / k;
}

/**
 * Recorre los cierres con una senal (dentro/fuera) decidida con el cierre ANTERIOR: sin mirar
 * el futuro. Cobra comision + slippage en cada entrada y salida.
 */
export function simular(
  fechas: readonly string[],
  cierres: readonly number[],
  dentro: (i: number, invertido: boolean) => boolean,
  capital: number,
  fraccion: number,
  coste: number,
): Simulacion {
  let efectivo = capital;
  let unidades = 0;
  let costes = 0;
  let abierta: { fecha: string; precio: number; invertido: number } | null = null;
  const operaciones: Operacion[] = [];
  const curva: { fecha: string; valor: number }[] = [];

  for (let i = 0; i < cierres.length; i++) {
    const precio = cierres[i] ?? 0;
    const fecha = fechas[i] ?? "";
    if (i > 0) {
      const quiere = dentro(i - 1, unidades > 0);
      if (quiere && unidades === 0) {
        const nocional = (efectivo + unidades * precio) * fraccion;
        const comision = nocional * coste;
        unidades = (nocional - comision) / precio;
        efectivo -= nocional;
        costes += comision;
        abierta = { fecha, precio, invertido: nocional };
      } else if (!quiere && unidades > 0 && abierta) {
        const bruto = unidades * precio;
        const comision = bruto * coste;
        efectivo += bruto - comision;
        costes += comision;
        operaciones.push({
          entrada: abierta.fecha,
          precioEntrada: abierta.precio,
          salida: fecha,
          precioSalida: precio,
          motivo: "senal",
          resultado: bruto - comision - abierta.invertido,
        });
        unidades = 0;
        abierta = null;
      }
    }
    curva.push({ fecha, valor: efectivo + unidades * precio });
  }
  if (abierta) {
    const precio = cierres[cierres.length - 1] ?? 0;
    operaciones.push({
      entrada: abierta.fecha,
      precioEntrada: abierta.precio,
      salida: null,
      precioSalida: null,
      motivo: "abierta al final",
      resultado: unidades * precio - abierta.invertido,
    });
  }
  return { curva, operaciones, costes };
}

function peorCaida(curva: readonly { valor: number }[]): number {
  let pico = curva[0]?.valor ?? 0;
  let peor = 0;
  for (const p of curva) {
    pico = Math.max(pico, p.valor);
    peor = Math.min(peor, p.valor - pico);
  }
  return peor;
}

function consistencia(curva: readonly { fecha: string; valor: number }[]): S["Consistencia"] | null {
  const finDeMes = new Map<string, number>();
  for (const p of curva) finDeMes.set(p.fecha.slice(0, 7), p.valor);
  const valores = [...finDeMes.values()];
  const variaciones: number[] = [];
  for (let i = 1; i < valores.length; i++) variaciones.push((valores[i] ?? 0) - (valores[i - 1] ?? 0));
  if (!variaciones.length) return null;
  const positivos = variaciones.filter((v) => v > 0).length;
  let racha = 0;
  let peorRacha = 0;
  for (const v of variaciones) {
    racha = v < 0 ? racha + 1 : 0;
    peorRacha = Math.max(peorRacha, racha);
  }
  const peor = Math.min(...variaciones);
  const mejor = Math.max(...variaciones);
  const proporcion = positivos / variaciones.length;
  const asimetria = mejor !== 0 ? Math.abs(peor) / Math.abs(mejor) : 0;
  return {
    periodos: variaciones.length,
    positivos,
    proporcion,
    peor_periodo: dinero(peor),
    racha_en_rojo: peorRacha,
    asimetria,
    aviso:
      proporcion >= 0.7 && asimetria > 3
        ? `${Math.round(proporcion * 100)}% de meses en verde, pero el peor mes se come ${asimetria.toFixed(1)} meses buenos. Ese perfil aguanta años y luego lo devuelve de golpe: mira la asimetría, no el porcentaje.`
        : null,
  };
}

/** El `Informe` del contrato a partir de una simulacion y su comprar-y-mantener. */
export function informe(
  sim: Simulacion,
  fechas: readonly string[],
  cierres: readonly number[],
  capital: number,
  coste: number,
): S["Informe"] {
  const final = sim.curva[sim.curva.length - 1]?.valor ?? capital;
  const neto = final - capital;
  const drawdown = peorCaida(sim.curva);
  const p0 = cierres[0] ?? 1;
  const unidadesBh = (capital * (1 - coste)) / p0;
  const curvaBh = cierres.map((c) => ({ valor: unidadesBh * c }));
  const netoBh = unidadesBh * (cierres[cierres.length - 1] ?? p0) - capital;
  const ddBh = peorCaida(curvaBh);
  const n = sim.operaciones.length;
  const ganadoras = sim.operaciones.filter((o) => o.resultado > 0).length;
  const expectancy = n ? sim.operaciones.reduce((s, o) => s + o.resultado, 0) / n : 0;
  const bate = neto > netoBh;
  return {
    concluyente: n >= 20,
    motivo_no_concluyente:
      n >= 20
        ? null
        : `solo ${n} operaciones: con menos de 20 el resultado puede ser pura suerte y no dice nada de la estrategia.`,
    resultado_neto: dinero(neto),
    drawdown_maximo: dinero(drawdown),
    operaciones: n,
    costes: dinero(sim.costes),
    comprar_y_mantener: { resultado: dinero(netoBh), drawdown: dinero(ddBh), no_hizo_nada: false },
    bate_al_mercado: bate,
    diferencia: dinero(neto - netoBh),
    curva: sim.curva.map((p) => ({ fecha: `${p.fecha}T00:00:00Z`, valor: Math.round(p.valor * 100) / 100 })),
    consistencia: consistencia(sim.curva),
    metricas: {
      columnas: ["metrica", "valor"],
      filas: [
        ["Resultado neto", Number(neto.toFixed(2))],
        ["Expectancy por operacion", Number(expectancy.toFixed(2))],
        ["Drawdown maximo", Number(drawdown.toFixed(2))],
        ["Operaciones", n],
        ["Costes totales", Number(sim.costes.toFixed(2))],
        ["Diferencia vs comprar y mantener", Number((neto - netoBh).toFixed(2))],
        ["Win rate (no es criterio de exito)", n ? Number((ganadoras / n).toFixed(3)) : 0],
      ],
    },
    registro: {
      columnas: ["entrada", "precio entrada", "salida", "precio salida", "motivo", "resultado"],
      filas: sim.operaciones.map((o) => [
        `${o.entrada}T00:00:00+00:00`,
        o.precioEntrada,
        o.salida ? `${o.salida}T00:00:00+00:00` : null,
        o.precioSalida,
        o.motivo,
        Number(o.resultado.toFixed(2)),
      ]),
    },
  };
}

export function rendimientos(cierres: readonly number[]): number[] {
  const r: number[] = [];
  for (let i = 1; i < cierres.length; i++) r.push((cierres[i] ?? 0) / (cierres[i - 1] ?? 1) - 1);
  return r;
}

export function correlacion(a: readonly number[], b: readonly number[]): number {
  const n = Math.min(a.length, b.length);
  if (n < 2) return 0;
  let ma = 0;
  let mb = 0;
  for (let i = 0; i < n; i++) {
    ma += a[i] ?? 0;
    mb += b[i] ?? 0;
  }
  ma /= n;
  mb /= n;
  let sab = 0;
  let saa = 0;
  let sbb = 0;
  for (let i = 0; i < n; i++) {
    const x = (a[i] ?? 0) - ma;
    const y = (b[i] ?? 0) - mb;
    sab += x * y;
    saa += x * x;
    sbb += y * y;
  }
  return saa && sbb ? sab / Math.sqrt(saa * sbb) : 0;
}
