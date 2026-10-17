"use client";

import { useState, type ReactNode } from "react";

import { fecha } from "@/lib/formato";

import { clases } from "../ui";

/**
 * Lo comun a todas las graficas, segun la skill de dataviz:
 * - colores de serie en orden fijo, nunca ciclados (8 huecos validados en claro y oscuro);
 * - lineas de 2px, rejilla y ejes en filete de 1px, recesivos;
 * - el texto nunca lleva el color de la serie: la identidad la da la marca de al lado;
 * - toda grafica tiene su gemela en tabla (y en claro tres huecos no llegan a 3:1, asi que la
 *   tabla y las etiquetas directas son obligatorias, no un adorno).
 */
export const SERIES = [
  "var(--serie-1)",
  "var(--serie-2)",
  "var(--serie-3)",
  "var(--serie-4)",
  "var(--serie-5)",
  "var(--serie-6)",
  "var(--serie-7)",
  "var(--serie-8)",
] as const;

export const MAX_SERIES = SERIES.length;

/** El color de un hueco fijo (0-7). */
export function colorSerie(hueco: number): string {
  return SERIES[hueco % SERIES.length] ?? SERIES[0];
}

/**
 * Dominio y marcas redondas para el eje Y (pasos de 1, 2, 2,5 o 5 por potencia de diez), en vez
 * de los 360/405/450 que salen de repartir el rango tal cual.
 */
export function ejeRedondo(valores: readonly number[], marcas = 5): { dominio: [number, number]; ticks: number[] } {
  const finitos = valores.filter((v) => Number.isFinite(v));
  if (!finitos.length) return { dominio: [0, 1], ticks: [0, 1] };
  let min = Math.min(...finitos);
  let max = Math.max(...finitos);
  if (min === max) {
    const holgura = Math.abs(min) * 0.05 || 1;
    min -= holgura;
    max += holgura;
  }
  const bruto = (max - min) / Math.max(1, marcas - 1);
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const paso = ([1, 2, 2.5, 5, 10].find((m) => m * potencia >= bruto) ?? 10) * potencia;
  const desde = Math.floor(min / paso) * paso;
  const hasta = Math.ceil(max / paso) * paso;
  const ticks: number[] = [];
  for (let t = desde; t <= hasta + paso / 2; t += paso) ticks.push(Number(t.toPrecision(12)));
  return { dominio: [desde, hasta], ticks };
}

export const EJE = {
  stroke: "var(--eje)",
  tick: { fill: "var(--tinta-suave)", fontSize: 12 },
  tickLine: false,
} as const;

export const REJILLA = { stroke: "var(--rejilla)", strokeWidth: 1, vertical: false } as const;

const MESES = new Intl.DateTimeFormat("es-ES", { month: "short", year: "2-digit", timeZone: "UTC" });
const DIA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", timeZone: "UTC" });
const DIA_MS = 86_400_000;

/**
 * Marcas del eje temporal en fechas redondas (1 de enero, 1 de mes...) y su formato. Repartir el
 * rango tal cual daba dos marcas con la misma etiqueta ("2016", "2016").
 */
export function marcasTiempo(min: number, max: number, maxMarcas = 8): { ticks: number[]; formato: (t: number) => string } {
  const dias = (max - min) / DIA_MS;
  const ticks: number[] = [];
  if (dias > 365 * 2.5) {
    const a0 = new Date(min).getUTCFullYear();
    const a1 = new Date(max).getUTCFullYear();
    const paso = [1, 2, 5, 10, 20].find((p) => (a1 - a0 + 1) / p <= maxMarcas) ?? 20;
    for (let a = Math.ceil(a0 / paso) * paso; a <= a1; a += paso) {
      const t = Date.UTC(a, 0, 1);
      if (t >= min && t <= max) ticks.push(t);
    }
    return { ticks, formato: (t) => String(new Date(t).getUTCFullYear()) };
  }
  if (dias > 60) {
    const d0 = new Date(min);
    const meses = dias / 30.44;
    const paso = [1, 2, 3, 6, 12].find((p) => meses / p <= maxMarcas) ?? 12;
    for (let m = d0.getUTCFullYear() * 12 + d0.getUTCMonth(); ; m++) {
      const t = Date.UTC(Math.floor(m / 12), m % 12, 1);
      if (t > max) break;
      if (t >= min && (m % 12) % paso === 0) ticks.push(t);
    }
    return { ticks, formato: (t) => MESES.format(new Date(t)) };
  }
  const paso = [1, 2, 7, 14, 30].find((p) => dias / p <= maxMarcas) ?? 30;
  for (let t = Math.ceil(min / DIA_MS) * DIA_MS; t <= max; t += paso * DIA_MS) ticks.push(t);
  return { ticks, formato: (t) => DIA.format(new Date(t)) };
}

/** Formato comun a todas las marcas del eje Y: o todas en "K", o ninguna. */
export function formatoMarcasY(ticks: readonly number[]): (v: number) => string {
  const max = Math.max(0, ...ticks.map((t) => Math.abs(t)));
  const paso = ticks.length > 1 ? Math.abs((ticks[1] ?? 0) - (ticks[0] ?? 0)) : max;
  if (max >= 1_000_000) {
    const dec = paso < 1_000_000 ? 1 : 0;
    return (v) =>
      v === 0 ? "0" : `${(v / 1_000_000).toLocaleString("es-ES", { maximumFractionDigits: dec, minimumFractionDigits: 0 })} M`;
  }
  if (max >= 10_000) {
    const dec = paso < 1_000 ? 1 : 0;
    return (v) =>
      v === 0 ? "0" : `${(v / 1_000).toLocaleString("es-ES", { maximumFractionDigits: dec, minimumFractionDigits: 0 })} K`;
  }
  const dec = paso >= 1 ? 0 : paso >= 0.1 ? 1 : paso >= 0.01 ? 2 : 4;
  return (v) => v.toLocaleString("es-ES", { maximumFractionDigits: dec, minimumFractionDigits: dec, useGrouping: true });
}

export function fechaIso(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

/** La fecha de un punto, para leerla: "16 oct 2026". */
export function fechaTexto(t: number): string {
  return fecha(fechaIso(t));
}

/** Tecla de serie en forma de linea corta (leyendas de lineas y filas del tooltip). */
export function TeclaLinea({ color, grosor = 2.5 }: { color: string; grosor?: number }) {
  return (
    <svg width="16" height="8" aria-hidden="true" className="shrink-0">
      <line x1="1" y1="4" x2="15" y2="4" stroke={color} strokeWidth={grosor} strokeLinecap="round" />
    </svg>
  );
}

/** Caja del tooltip: el valor manda (fuerte), la etiqueta acompana. */
export function CajaTooltip({ titulo, filas }: { titulo: string; filas: { color?: string; nombre: string; valor: string }[] }) {
  return (
    <div className="rounded-xl border border-linea bg-superficie px-3 py-2.5 text-sm shadow-alta">
      <div className="mb-1 text-tinta-suave">{titulo}</div>
      <ul className="space-y-0.5">
        {filas.map((f) => (
          <li key={f.nombre} className="flex items-center gap-2">
            {f.color ? <TeclaLinea color={f.color} /> : null}
            <span className="cifras font-semibold text-tinta">{f.valor}</span>
            <span className="text-tinta-suave">{f.nombre}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * El contenedor de una grafica: titulo, la grafica (con su resumen para lectores de pantalla),
 * el pie con la fecha de los datos y la vista en tabla, que solo se monta al abrirla.
 */
export function Figura({
  titulo,
  resumen,
  pie,
  atenuada = false,
  tabla,
  filasTabla,
  children,
}: {
  titulo?: ReactNode;
  /** Lo que la grafica dice, en una frase: lo lee el lector de pantalla. */
  resumen: string;
  pie?: ReactNode;
  /** Se esta recargando: se conserva el dibujo anterior atenuado, sin saltos. */
  atenuada?: boolean;
  tabla: () => ReactNode;
  filasTabla: number;
  children: ReactNode;
}) {
  const [verTabla, setVerTabla] = useState(false);
  return (
    <figure className="space-y-3 rounded-tarjeta border border-linea bg-superficie p-4 shadow-suave sm:p-5">
      {titulo ? <figcaption className="text-[0.9375rem] font-semibold text-tinta">{titulo}</figcaption> : null}
      <div
        role="img"
        aria-label={resumen}
        className={clases("transition-opacity", atenuada && "opacity-50")}
      >
        {children}
      </div>
      {pie ? <div className="text-sm leading-relaxed text-tinta-suave">{pie}</div> : null}
      <details onToggle={(e) => setVerTabla(e.currentTarget.open)}>
        <summary className="inline-flex min-h-11 cursor-pointer items-center text-sm font-medium text-marca underline underline-offset-4">
          Ver los datos en tabla ({filasTabla.toLocaleString("es-ES")} filas)
        </summary>
        {verTabla ? <div className="relative mt-2 max-h-80 overflow-auto rounded-xl border border-linea">{tabla()}</div> : null}
      </details>
    </figure>
  );
}
