"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";

import type { PuntoBot } from "@/api/tipos";
import { CajaTooltip, EJE, Figura, REJILLA, TeclaLinea, colorSerie, ejeRedondo, formatoMarcasY } from "@/componentes/graficas/comun";

const FECHA_HORA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const DIA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });
const HORA = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });
const sinPunto = (t: string) => t.replace(/\.(?=\s|$)/g, "");

const usd = (v: number) => `${v.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" })} USDC`;

/** Marcas del eje de tiempo en la hora de quien mira: horas si es menos de dos dias, dias si no. */
function marcas(t0: number, t1: number): { ticks: number[]; formato: (t: number) => string } {
  const span = t1 - t0;
  const dias = span / 86_400_000;
  if (dias < 2) {
    const paso = [1, 2, 3, 6, 12].map((h) => h * 3_600_000).find((p) => span / p <= 6) ?? 12 * 3_600_000;
    const ticks: number[] = [];
    const inicio = new Date(t0);
    inicio.setMinutes(0, 0, 0);
    for (let t = inicio.getTime() + 3_600_000; t <= t1; t += 3_600_000) {
      const h = new Date(t).getHours();
      if ((h * 3_600_000) % paso === 0) ticks.push(t);
    }
    return { ticks, formato: (t) => HORA.format(new Date(t)) };
  }
  const paso = [1, 2, 3, 7, 14].find((d) => dias / d <= 7) ?? 14;
  const ticks: number[] = [];
  const inicio = new Date(t0);
  inicio.setHours(0, 0, 0, 0);
  for (let t = inicio.getTime() + 86_400_000, i = 0; t <= t1; t += 86_400_000, i++) if (i % paso === 0) ticks.push(t);
  return { ticks, formato: (t) => sinPunto(DIA.format(new Date(t))) };
}

interface Fila {
  t: number;
  bot: number | null;
  mantener: number | null;
}

/**
 * La curva del bot frente a "solo mantener" (docs/panel-v3-vivo.md, seccion 3), en USDC y en UN
 * solo eje (nunca dos escalas). Dos series: el bot en el hueco 1 (azul, el mismo que la curva
 * pequena de su tarjeta) y "mantener" en el hueco 2. Leyenda siempre, etiqueta al final de cada
 * linea, un filete en el capital puesto, cruz con tooltip y la tabla gemela.
 */
export function CurvaBot({
  curva,
  mantener,
  capital,
  nombre,
  atenuada,
}: {
  curva: readonly PuntoBot[];
  mantener: readonly PuntoBot[];
  capital: number;
  nombre: string;
  atenuada?: boolean;
}) {
  const porT = new Map<number, Fila>();
  for (const p of curva) {
    const t = Date.parse(p.at);
    porT.set(t, { t, bot: p.valor, mantener: porT.get(t)?.mantener ?? null });
  }
  for (const p of mantener) {
    const t = Date.parse(p.at);
    porT.set(t, { t, bot: porT.get(t)?.bot ?? null, mantener: p.valor });
  }
  const filas = [...porT.values()].sort((a, b) => a.t - b.t);
  const t0 = filas[0]?.t ?? 0;
  const t1 = filas[filas.length - 1]?.t ?? 0;
  const eje = marcas(t0, t1);
  const valores = filas.flatMap((f) => [f.bot, f.mantener]).filter((v): v is number => v !== null);
  // Como poco un 1 % arriba y abajo del capital: en un bot recien desplegado, un -0,2 % no puede
  // ocupar toda la altura y parecer un desplome.
  const ejeY = ejeRedondo([...valores, capital * 0.99, capital * 1.01]);
  const fmtY = formatoMarcasY(ejeY.ticks);
  const finBot = curva[curva.length - 1]?.valor ?? null;
  const finMantener = mantener[mantener.length - 1]?.valor ?? null;
  const series = [
    { clave: "bot" as const, nombre: "El bot", hueco: 0, fin: finBot },
    { clave: "mantener" as const, nombre: "Si solo hubieras mantenido", hueco: 1, fin: finMantener },
  ];
  // El ultimo punto de cada serie (la del bot llega por el stream y puede ir unos segundos por
  // delante de la de mantener, que llega con la ficha).
  const ultimoIndice = (clave: "bot" | "mantener") => {
    for (let i = filas.length - 1; i >= 0; i--) if (filas[i]?.[clave] !== null) return i;
    return -1;
  };
  const finales = { bot: ultimoIndice("bot"), mantener: ultimoIndice("mantener") };
  // Etiquetas al final solo si no se pisan.
  const rango = ejeY.dominio[1] - ejeY.dominio[0] || 1;
  const separadas = finBot !== null && finMantener !== null && Math.abs(finBot - finMantener) / rango > 0.07;

  const resumen = `${nombre}: lo que vale el bot y lo que valdría el mismo capital solo manteniendo, del ${sinPunto(FECHA_HORA.format(new Date(t0)))} a ahora. El bot vale ${finBot === null ? "—" : usd(finBot)}; manteniendo, ${finMantener === null ? "—" : usd(finMantener)}. Capital puesto: ${usd(capital)}.`;

  const tooltip = (p: TooltipContentProps) => {
    if (!p.active || typeof p.label !== "number") return null;
    const f = porT.get(p.label);
    return (
      <CajaTooltip
        titulo={sinPunto(FECHA_HORA.format(new Date(p.label)))}
        filas={series.map((s) => ({ color: colorSerie(s.hueco), nombre: s.nombre, valor: f?.[s.clave] === null || f?.[s.clave] === undefined ? "—" : usd(f[s.clave] ?? 0) }))}
      />
    );
  };

  return (
    <Figura
      titulo="Lo que vale el bot, frente a solo mantener"
      resumen={resumen}
      atenuada={atenuada}
      pie="El mismo capital, desde el mismo momento: comprando sus monedas al arrancar y sin hacer nada más. La línea fina es lo que pusiste."
      filasTabla={filas.length}
      tabla={() => (
        <table className="cifras w-full text-xs">
          <thead>
            <tr className="tabla-densa text-left text-tinta-suave">
              <th scope="col" className="px-2 py-1">Cuándo</th>
              <th scope="col" className="px-2 py-1 text-right">El bot</th>
              <th scope="col" className="px-2 py-1 text-right">Solo manteniendo</th>
            </tr>
          </thead>
          <tbody>
            {[...filas].reverse().map((f) => (
              <tr key={f.t} className="border-t border-linea">
                <td className="px-2 py-0.5">{sinPunto(FECHA_HORA.format(new Date(f.t)))}</td>
                <td className="px-2 py-0.5 text-right">{f.bot === null ? "—" : usd(f.bot)}</td>
                <td className="px-2 py-0.5 text-right">{f.mantener === null ? "—" : usd(f.mantener)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    >
      <ul className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-sm" aria-label="Leyenda">
        {series.map((s) => (
          <li key={s.clave} className="flex items-center gap-1.5">
            <TeclaLinea color={colorSerie(s.hueco)} />
            <span className="text-tinta">{s.nombre}</span>
            <span className="cifras font-semibold text-tinta">{s.fin === null ? "—" : usd(s.fin)}</span>
          </li>
        ))}
      </ul>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={filas} margin={{ top: 8, right: separadas ? 92 : 12, bottom: 4, left: 4 }}>
          <CartesianGrid {...REJILLA} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} ticks={eje.ticks} tickFormatter={eje.formato} minTickGap={24} {...EJE} />
          <YAxis domain={ejeY.dominio} ticks={ejeY.ticks} tickFormatter={fmtY} width={56} axisLine={false} {...EJE} />
          <ReferenceLine y={capital} stroke="var(--linea-control)" strokeWidth={1} ifOverflow="extendDomain" />
          <Tooltip cursor={{ stroke: "var(--tinta-suave)", strokeWidth: 1 }} content={tooltip} isAnimationActive={false} />
          {series.map((s) => (
            <Line
              key={s.clave}
              type="linear"
              dataKey={s.clave}
              name={s.nombre}
              stroke={colorSerie(s.hueco)}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              dot={false}
              connectNulls
              activeDot={{ r: 4, fill: colorSerie(s.hueco), stroke: "var(--superficie)", strokeWidth: 2 }}
              isAnimationActive={false}
              label={
                separadas
                  ? (props: { index?: number; x?: number | string; y?: number | string }) =>
                      props.index === finales[s.clave] && typeof props.x === "number" && typeof props.y === "number" && Number.isFinite(props.y) ? (
                        <text x={props.x + 8} y={props.y} dy={4} fontSize={11} fill="var(--tinta-suave)">
                          {s.clave === "bot" ? "El bot" : "Mantener"}
                        </text>
                      ) : (
                        <g />
                      )
                  : false
              }
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Figura>
  );
}
