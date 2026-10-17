"use client";

import type { ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { numero } from "@/lib/formato";

import {
  CajaTooltip,
  EJE,
  Figura,
  REJILLA,
  SERIES,
  TeclaLinea,
  colorSerie,
  ejeRedondo,
  fechaTexto,
  formatoMarcasY,
  marcasTiempo,
} from "./comun";

export interface PuntoLinea {
  /** Milisegundos UTC. */
  t: number;
  v: number;
}

const CURSOR = { stroke: "var(--tinta-suave)", strokeWidth: 1 };

function etiquetaTiempo(label: unknown): string {
  return typeof label === "number" ? fechaTexto(label) : String(label ?? "");
}

/**
 * Una sola serie en el tiempo (precio de un activo, patrimonio de un backtest): una linea de 2px,
 * sin leyenda (el titulo ya dice que es), cruz que busca la fecha y tooltip con el valor delante.
 */
export function GraficaLinea({
  puntos,
  nombreSerie,
  titulo,
  pie,
  atenuada,
  alto = 320,
  formatoValor = (v) => numero(v, 2),
  cabeceraValor = "valor",
}: {
  puntos: readonly PuntoLinea[];
  nombreSerie: string;
  titulo?: ReactNode;
  pie?: ReactNode;
  atenuada?: boolean;
  alto?: number;
  formatoValor?: (v: number) => string;
  cabeceraValor?: string;
}) {
  const primero = puntos[0];
  const ultimo = puntos[puntos.length - 1];
  const ejeX = marcasTiempo(primero?.t ?? 0, ultimo?.t ?? 0);
  const ejeY = ejeRedondo(puntos.map((p) => p.v));
  const fmtY = formatoMarcasY(ejeY.ticks);
  const resumen =
    primero && ultimo
      ? `${nombreSerie}: ${puntos.length} puntos del ${fechaTexto(primero.t)} al ${fechaTexto(ultimo.t)}, de ${formatoValor(primero.v)} a ${formatoValor(ultimo.v)}.`
      : `${nombreSerie}: sin datos.`;

  const tooltip = (p: TooltipContentProps) => {
    if (!p.active || !p.payload.length) return null;
    const valor = p.payload[0]?.value;
    return (
      <CajaTooltip
        titulo={etiquetaTiempo(p.label)}
        filas={[{ nombre: nombreSerie, valor: typeof valor === "number" ? formatoValor(valor) : "—" }]}
      />
    );
  };

  return (
    <Figura
      titulo={titulo}
      resumen={resumen}
      pie={pie}
      atenuada={atenuada}
      filasTabla={puntos.length}
      tabla={() => (
        <table className="cifras w-full text-xs">
          <thead>
            <tr className="tabla-densa text-left text-tinta-suave">
              <th scope="col" className="px-2 py-1">fecha</th>
              <th scope="col" className="px-2 py-1 text-right">{cabeceraValor}</th>
            </tr>
          </thead>
          <tbody>
            {puntos.map((p) => (
              <tr key={p.t} className="border-t border-linea">
                <td className="px-2 py-0.5">{fechaTexto(p.t)}</td>
                <td className="px-2 py-0.5 text-right">{formatoValor(p.v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    >
      <ResponsiveContainer width="100%" height={alto}>
        <LineChart data={puntos as PuntoLinea[]} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid {...REJILLA} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={ejeX.ticks}
            tickFormatter={ejeX.formato}
            minTickGap={24}
            {...EJE}
          />
          <YAxis domain={ejeY.dominio} ticks={ejeY.ticks} tickFormatter={fmtY} width={58} axisLine={false} {...EJE} />
          <Tooltip cursor={CURSOR} content={tooltip} isAnimationActive={false} />
          <Line
            type="linear"
            dataKey="v"
            name={nombreSerie}
            stroke={SERIES[0]}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 4, fill: SERIES[0], stroke: "var(--superficie)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </Figura>
  );
}

export interface SerieComparada {
  nombre: string;
  /** Hueco de color (0-7) fijado a la entidad, no a su posicion: filtrar no repinta a nadie. */
  hueco: number;
  puntos: readonly PuntoLinea[];
}

/**
 * Varias series en base 100 sobre UN eje (nunca dos escalas). Leyenda siempre; etiquetas al final
 * de cada linea si son 4 o menos y no se pisan (si se pisan, se queda la leyenda y el tooltip).
 */
export function GraficaComparada({
  series,
  titulo,
  pie,
  atenuada,
  alto = 380,
  formatoValor = (v) => numero(v, 1),
}: {
  series: readonly SerieComparada[];
  titulo?: ReactNode;
  pie?: ReactNode;
  atenuada?: boolean;
  alto?: number;
  formatoValor?: (v: number) => string;
}) {
  // Filas por fecha con una columna por serie (s0, s1...: los simbolos pueden llevar puntos).
  const porFecha = new Map<number, (number | null)[]>();
  series.forEach((s, i) => {
    for (const p of s.puntos) {
      let fila = porFecha.get(p.t);
      if (!fila) {
        fila = series.map(() => null);
        porFecha.set(p.t, fila);
      }
      fila[i] = p.v;
    }
  });
  const tiempos = [...porFecha.keys()].sort((a, b) => a - b);
  const filas = tiempos.map((t) => {
    const valores = porFecha.get(t) ?? [];
    const fila: Record<string, number | null> = { t };
    valores.forEach((v, i) => {
      fila[`s${i}`] = v;
    });
    return fila;
  });

  const primero = tiempos[0];
  const ultimoT = tiempos[tiempos.length - 1];
  const ejeX = marcasTiempo(primero ?? 0, ultimoT ?? 0);

  const finales = series.map((s) => s.puntos[s.puntos.length - 1] ?? null);
  const todos = series.flatMap((s) => s.puntos.map((p) => p.v));
  const rango = todos.length ? Math.max(...todos) - Math.min(...todos) || 1 : 1;
  const ejeY = ejeRedondo(todos);
  const fmtY = formatoMarcasY(ejeY.ticks);

  // Etiquetas directas: solo con 4 series o menos, y quitando las que caerian encima de otra.
  const conEtiqueta = new Set<number>();
  if (series.length <= 4) {
    const orden = finales
      .map((f, i) => ({ i, v: f?.v }))
      .filter((x): x is { i: number; v: number } => x.v !== undefined)
      .sort((a, b) => a.v - b.v);
    let anterior: number | null = null;
    for (const x of orden) {
      if (anterior === null || Math.abs(x.v - anterior) / rango > 0.06) {
        conEtiqueta.add(x.i);
        anterior = x.v;
      }
    }
  }

  const resumen = `Comparación en base 100 de ${series.length} activo(s): ${series
    .map((s, i) => `${s.nombre} termina en ${finales[i] ? formatoValor(finales[i].v) : "—"}`)
    .join("; ")}.`;

  const tooltip = (p: TooltipContentProps) => {
    if (!p.active || p.label === undefined) return null;
    const fila = typeof p.label === "number" ? porFecha.get(p.label) : undefined;
    return (
      <CajaTooltip
        titulo={etiquetaTiempo(p.label)}
        filas={series.map((s, i) => {
          const v = fila?.[i];
          return {
            color: colorSerie(s.hueco),
            nombre: s.nombre,
            valor: v === null || v === undefined ? "—" : formatoValor(v),
          };
        })}
      />
    );
  };

  return (
    <Figura
      titulo={titulo}
      resumen={resumen}
      pie={pie}
      atenuada={atenuada}
      filasTabla={filas.length}
      tabla={() => (
        <table className="cifras w-full text-xs">
          <thead>
            <tr className="tabla-densa text-left text-tinta-suave">
              <th scope="col" className="px-2 py-1">fecha</th>
              {series.map((s) => (
                <th key={s.nombre} scope="col" className="px-2 py-1 text-right">
                  {s.nombre}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tiempos.map((t) => (
              <tr key={t} className="border-t border-linea">
                <td className="px-2 py-0.5">{fechaTexto(t)}</td>
                {(porFecha.get(t) ?? []).map((v, i) => (
                  <td key={i} className="px-2 py-0.5 text-right">
                    {v === null ? "—" : formatoValor(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    >
      <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Leyenda">
        {series.map((s, i) => (
          <li key={s.nombre} className="flex items-center gap-1.5">
            <TeclaLinea color={colorSerie(s.hueco)} />
            <span className="text-tinta">{s.nombre}</span>
            <span className="cifras text-tinta-suave">{finales[i] ? formatoValor(finales[i].v) : "—"}</span>
          </li>
        ))}
      </ul>
      <ResponsiveContainer width="100%" height={alto}>
        <LineChart data={filas} margin={{ top: 8, right: conEtiqueta.size ? 76 : 12, bottom: 4, left: 4 }}>
          <CartesianGrid {...REJILLA} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={ejeX.ticks}
            tickFormatter={ejeX.formato}
            minTickGap={24}
            {...EJE}
          />
          <YAxis domain={ejeY.dominio} ticks={ejeY.ticks} tickFormatter={fmtY} width={52} axisLine={false} {...EJE} />
          <Tooltip cursor={CURSOR} content={tooltip} isAnimationActive={false} />
          {series.map((s, i) => (
            <Line
              key={s.nombre}
              type="linear"
              dataKey={`s${i}`}
              name={s.nombre}
              stroke={colorSerie(s.hueco)}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              dot={false}
              connectNulls
              activeDot={{ r: 4, fill: colorSerie(s.hueco), stroke: "var(--superficie)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ))}
          {series.map((s, i) => {
            const fin = finales[i];
            if (!fin || !conEtiqueta.has(i)) return null;
            return (
              <ReferenceDot
                key={`etiqueta-${s.nombre}`}
                x={fin.t}
                y={fin.v}
                r={4}
                fill={colorSerie(s.hueco)}
                stroke="var(--superficie)"
                strokeWidth={2}
                ifOverflow="visible"
                label={{ value: s.nombre, position: "right", fill: "var(--tinta-suave)", fontSize: 11, offset: 8 }}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </Figura>
  );
}
