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

import type { ResultadoSimulado } from "@/api/tipos";
import { eurosNum, mesYAnio } from "@/lib/formato";

import { CajaTooltip, EJE, Figura, REJILLA, TeclaLinea, colorSerie, ejeRedondo, fechaTexto, marcasTiempo } from "./comun";

const PUESTO = "var(--tinta-suave)";
const CURSOR = { stroke: "var(--tinta-suave)", strokeWidth: 1 };

/** Marcas del eje Y en euros enteros: "10.000 €" (la "K" es jerga para quien empieza). */
function formatoEurosEje(ticks: readonly number[]): (v: number) => string {
  const max = Math.max(0, ...ticks.map((t) => Math.abs(t)));
  if (max >= 1_000_000) {
    return (v) => (v === 0 ? "0 €" : `${(v / 1_000_000).toLocaleString("es-ES", { maximumFractionDigits: 1 })} M€`);
  }
  return (v) => eurosNum(v);
}

export interface SerieSimulada {
  resultado: ResultadoSimulado;
  /** Hueco de color (0-7) fijado a la estrategia mientras esta en la vista. */
  hueco: number;
}

/**
 * "Con tus numeros": lo que habrias tenido con cada estrategia frente a lo que habrias puesto
 * (el escalon gris de las aportaciones). Un solo eje, en euros. Siguiendo la skill dataviz:
 * lineas de 2 px, leyenda siempre, etiqueta directa al final de cada linea, cruz que busca la
 * fecha, el peor momento de cada una marcado con un anillo, y la tabla gemela.
 */
export function GraficaTusNumeros({
  series,
  titulo,
  pie,
  atenuada,
  alto = 320,
}: {
  series: readonly SerieSimulada[];
  titulo?: ReactNode;
  pie?: ReactNode;
  atenuada?: boolean;
  alto?: number;
}) {
  // Filas por fecha: una columna por estrategia (s0, s1...) y lo puesto (p).
  const porFecha = new Map<number, { valores: (number | null)[]; puesto: number | null }>();
  series.forEach((s, i) => {
    for (const p of s.resultado.puntos) {
      const t = Date.parse(`${p.fecha}T00:00:00Z`);
      let fila = porFecha.get(t);
      if (!fila) {
        fila = { valores: series.map(() => null), puesto: null };
        porFecha.set(t, fila);
      }
      fila.valores[i] = p.valor;
      fila.puesto ??= p.aportado;
    }
  });
  const tiempos = [...porFecha.keys()].sort((a, b) => a - b);
  const filas = tiempos.map((t) => {
    const f = porFecha.get(t);
    const fila: Record<string, number | null> = { t, p: f?.puesto ?? null };
    f?.valores.forEach((v, i) => {
      fila[`s${i}`] = v;
    });
    return fila;
  });

  const primero = tiempos[0] ?? 0;
  const ultimo = tiempos[tiempos.length - 1] ?? 0;
  const ejeX = marcasTiempo(primero, ultimo, 7);
  const todos = filas.flatMap((f) => Object.entries(f).filter(([k]) => k !== "t").map(([, v]) => v)).filter(
    (v): v is number => typeof v === "number",
  );
  const ejeY = ejeRedondo([0, ...todos], 5);
  const fmtY = formatoEurosEje(ejeY.ticks);
  const finales = series.map((s) => s.resultado.puntos[s.resultado.puntos.length - 1] ?? null);
  const puestoFinal = filas.length ? (filas[filas.length - 1]?.p ?? null) : null;

  const resumen = `Lo que habrías tenido: ${series
    .map((s) => `${s.resultado.nombre} termina en ${eurosNum(s.resultado.valor_final)} y en su peor momento valió ${eurosNum(s.resultado.peor_momento_valor)} (${mesYAnio(s.resultado.peor_momento_fecha)})`)
    .join("; ")}. Lo que habrías puesto: ${eurosNum(puestoFinal)}.`;

  const tooltip = (p: TooltipContentProps) => {
    if (!p.active || typeof p.label !== "number") return null;
    const f = porFecha.get(p.label);
    return (
      <CajaTooltip
        titulo={fechaTexto(p.label)}
        filas={[
          ...series.map((s, i) => ({
            color: colorSerie(s.hueco),
            nombre: s.resultado.nombre,
            valor: f?.valores[i] === null || f?.valores[i] === undefined ? "—" : eurosNum(f.valores[i]),
          })),
          { color: PUESTO, nombre: "lo que habrías puesto", valor: eurosNum(f?.puesto) },
        ]}
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
        <table className="cifras w-full text-sm">
          <thead>
            <tr className="tabla-densa text-left text-tinta-suave">
              <th scope="col" className="px-3 py-2 font-medium">
                Semana
              </th>
              {series.map((s) => (
                <th key={s.resultado.clave} scope="col" className="px-3 py-2 text-right font-medium">
                  {s.resultado.nombre}
                </th>
              ))}
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Puesto
              </th>
            </tr>
          </thead>
          <tbody>
            {tiempos.map((t) => {
              const f = porFecha.get(t);
              return (
                <tr key={t} className="border-t border-linea">
                  <td className="px-3 py-1 whitespace-nowrap">{fechaTexto(t)}</td>
                  {(f?.valores ?? []).map((v, i) => (
                    <td key={i} className="px-3 py-1 text-right whitespace-nowrap">
                      {v === null ? "—" : eurosNum(v)}
                    </td>
                  ))}
                  <td className="px-3 py-1 text-right whitespace-nowrap">{eurosNum(f?.puesto)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    >
      <ul className="mb-3 flex flex-wrap gap-x-5 gap-y-2 text-sm" aria-label="Leyenda">
        {series.map((s, i) => (
          <li key={s.resultado.clave} className="flex items-center gap-2">
            <TeclaLinea color={colorSerie(s.hueco)} />
            <span className="text-tinta">{s.resultado.nombre}</span>
            <span className="cifras font-semibold text-tinta">{finales[i] ? eurosNum(finales[i].valor) : "—"}</span>
          </li>
        ))}
        <li className="flex items-center gap-2">
          <TeclaLinea color={PUESTO} />
          <span className="text-tinta">Lo que habrías puesto</span>
          <span className="cifras font-semibold text-tinta">{eurosNum(puestoFinal)}</span>
        </li>
        <li className="flex items-center gap-2 text-tinta-suave">
          <svg width="14" height="14" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" fill="var(--superficie)" stroke="var(--tinta-suave)" strokeWidth="2" />
          </svg>
          su peor momento
        </li>
      </ul>
      <ResponsiveContainer width="100%" height={alto}>
        <LineChart data={filas} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
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
          <YAxis domain={ejeY.dominio} ticks={ejeY.ticks} tickFormatter={fmtY} width={76} axisLine={false} {...EJE} />
          <Tooltip cursor={CURSOR} content={tooltip} isAnimationActive={false} />
          <Line
            type="stepAfter"
            dataKey="p"
            name="Lo que habrías puesto"
            stroke={PUESTO}
            strokeWidth={2}
            strokeLinejoin="round"
            dot={false}
            connectNulls
            activeDot={false}
            isAnimationActive={false}
          />
          {series.map((s, i) => (
            <Line
              key={s.resultado.clave}
              type="linear"
              dataKey={`s${i}`}
              name={s.resultado.nombre}
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
          {series.map((s) => (
            <ReferenceDot
              key={`peor-${s.resultado.clave}`}
              x={Date.parse(`${s.resultado.peor_momento_fecha}T00:00:00Z`)}
              y={s.resultado.peor_momento_valor}
              r={5}
              fill="var(--superficie)"
              stroke={colorSerie(s.hueco)}
              strokeWidth={2.5}
              ifOverflow="visible"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Figura>
  );
}
