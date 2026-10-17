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
/** Tu reparto: en el color del texto, que no es ninguno de los de las series ni el gris de lo puesto. */
const REPARTO = "var(--tinta)";
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
  combinado = null,
  titulo,
  pie,
  atenuada,
  alto = 320,
}: {
  series: readonly SerieSimulada[];
  /**
   * Tu reparto entero (`combinado`, contrato v2.1): la linea que importa, destacada (mas gruesa y
   * en el color de la tinta). Las de cada estrategia son "todo tu dinero en una sola".
   */
  combinado?: ResultadoSimulado | null;
  titulo?: ReactNode;
  pie?: ReactNode;
  atenuada?: boolean;
  alto?: number;
}) {
  // Filas por fecha: una columna por estrategia (s0, s1...), tu reparto (c) y lo puesto (p).
  // Lo puesto sale del reparto si lo hay: es el dinero que de verdad pondrias.
  const porFecha = new Map<number, { valores: (number | null)[]; combinado: number | null; puesto: number | null }>();
  const fila = (t: number) => {
    let f = porFecha.get(t);
    if (!f) {
      f = { valores: series.map(() => null), combinado: null, puesto: null };
      porFecha.set(t, f);
    }
    return f;
  };
  for (const p of combinado?.puntos ?? []) {
    const f = fila(Date.parse(`${p.fecha}T00:00:00Z`));
    f.combinado = p.valor;
    f.puesto = p.aportado;
  }
  series.forEach((s, i) => {
    for (const p of s.resultado.puntos) {
      const f = fila(Date.parse(`${p.fecha}T00:00:00Z`));
      f.valores[i] = p.valor;
      f.puesto ??= p.aportado;
    }
  });
  const tiempos = [...porFecha.keys()].sort((a, b) => a - b);
  const filas = tiempos.map((t) => {
    const f = porFecha.get(t);
    const fila: Record<string, number | null> = { t, p: f?.puesto ?? null, c: f?.combinado ?? null };
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

  const todas = combinado ? [combinado, ...series.map((s) => s.resultado)] : series.map((s) => s.resultado);
  const resumen = `Lo que habrías tenido: ${todas
    .map((r) => `${r.nombre} termina en ${eurosNum(r.valor_final)} y en su peor momento valió ${eurosNum(r.peor_momento_valor)} (${mesYAnio(r.peor_momento_fecha)})`)
    .join("; ")}. Lo que habrías puesto: ${eurosNum(puestoFinal)}.`;

  const tooltip = (p: TooltipContentProps) => {
    if (!p.active || typeof p.label !== "number") return null;
    const f = porFecha.get(p.label);
    return (
      <CajaTooltip
        titulo={fechaTexto(p.label)}
        filas={[
          ...(combinado ? [{ color: REPARTO, nombre: combinado.nombre, valor: eurosNum(f?.combinado) }] : []),
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
              {combinado ? (
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {combinado.nombre}
                </th>
              ) : null}
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
                  {combinado ? <td className="px-3 py-1 text-right font-semibold whitespace-nowrap">{eurosNum(f?.combinado)}</td> : null}
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
        {combinado ? (
          <li className="flex items-center gap-2">
            <TeclaLinea color={REPARTO} grosor={3.5} />
            <span className="font-semibold text-tinta">{combinado.nombre}</span>
            <span className="cifras font-semibold text-tinta">{eurosNum(combinado.valor_final)}</span>
          </li>
        ) : null}
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
          {combinado ? (
            <Line
              type="linear"
              dataKey="c"
              name={combinado.nombre}
              stroke={REPARTO}
              strokeWidth={3.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              dot={false}
              connectNulls
              activeDot={{ r: 5, fill: REPARTO, stroke: "var(--superficie)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ) : null}
          {combinado ? (
            <ReferenceDot
              x={Date.parse(`${combinado.peor_momento_fecha}T00:00:00Z`)}
              y={combinado.peor_momento_valor}
              r={6}
              fill="var(--superficie)"
              stroke={REPARTO}
              strokeWidth={3}
              ifOverflow="visible"
            />
          ) : null}
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
