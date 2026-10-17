"use client";

import type { ResultadoSimulado } from "@/api/tipos";
import { GraficaTusNumeros } from "@/componentes/graficas/TusNumeros";
import { TeclaLinea, colorSerie } from "@/componentes/graficas/comun";
import { Hoja } from "@/componentes/Hoja";
import { Cargando, ErrorApiVista, Segmentado } from "@/componentes/ui";
import type { ErrorApi } from "@/api/cliente";
import { eurosNum, fecha, mesYAnio } from "@/lib/formato";

import { ANIOS } from "./estado";

interface Fila {
  etiqueta: string;
  valor: (r: ResultadoSimulado) => string;
  detalle?: (r: ResultadoSimulado) => string;
}

const FILAS: Fila[] = [
  { etiqueta: "Tendrías", valor: (r) => eurosNum(r.valor_final) },
  { etiqueta: "Pusiste", valor: (r) => eurosNum(r.aportado) },
  {
    etiqueta: "En el peor momento",
    valor: (r) => eurosNum(r.peor_momento_valor),
    detalle: (r) => `${mesYAnio(r.peor_momento_fecha)}, con ${eurosNum(r.peor_momento_aportado)} puestos`,
  },
  {
    etiqueta: "Meses por debajo de lo puesto",
    valor: (r) => `${r.meses_por_debajo} ${r.meses_por_debajo === 1 ? "mes" : "meses"}`,
  },
];

/**
 * Comparar 2-4 estrategias: en la misma grafica y en una tabla de cuatro filas en llano
 * (docs/panel-v2.md, 4.2). En el movil la tabla se convierte en una tarjeta por estrategia.
 */
export function Comparador({
  abierto,
  onCerrar,
  resultados,
  huecos,
  desdeAnio,
  onAnio,
  cargando,
  error,
  ejemplo,
}: {
  abierto: boolean;
  onCerrar: () => void;
  resultados: ResultadoSimulado[];
  huecos: Record<string, number>;
  desdeAnio: number;
  onAnio: (a: number) => void;
  cargando: boolean;
  error: ErrorApi | null;
  ejemplo: boolean;
}) {
  return (
    <Hoja
      abierta={abierto}
      onCerrar={onCerrar}
      ancho="ancho"
      titulo="Comparar"
      bajada={`${ejemplo ? "Con 10.000 € de ejemplo" : "Con tus números"}, si hubieras empezado en ${desdeAnio}.`}
    >
      <div className="space-y-6">
        <Segmentado
          repartido
          etiqueta="Empezar en"
          opciones={ANIOS.map((a) => ({ valor: String(a), texto: String(a) }))}
          valor={String(desdeAnio)}
          onCambio={(v) => onAnio(Number(v))}
        />
        {error ? <ErrorApiVista error={error} /> : null}
        {resultados.length ? (
          <>
            <GraficaTusNumeros
              series={resultados.map((r) => ({ resultado: r, hueco: huecos[r.clave] ?? 0 }))}
              atenuada={cargando}
              alto={280}
              pie={<>Desde el {fecha(resultados[0]?.desde)}. Probadas sobre el pasado, con comisiones: no es una promesa.</>}
            />

            <div className="hidden overflow-x-auto rounded-xl border border-linea sm:block">
              <table className="cifras w-full text-left text-[0.9375rem]">
                <caption className="sr-only">Comparación en cuatro filas</caption>
                <thead>
                  <tr className="bg-superficie-2">
                    <th scope="col" className="px-4 py-3 font-medium text-tinta-suave">
                      <span className="sr-only">Qué</span>
                    </th>
                    {resultados.map((r) => (
                      <th key={r.clave} scope="col" className="px-4 py-3 font-semibold text-tinta">
                        <span className="flex items-center gap-2">
                          <TeclaLinea color={colorSerie(huecos[r.clave] ?? 0)} />
                          {r.nombre}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-linea">
                  {FILAS.map((f) => (
                    <tr key={f.etiqueta}>
                      <th scope="row" className="px-4 py-3 font-normal text-tinta-suave">
                        {f.etiqueta}
                      </th>
                      {resultados.map((r) => (
                        <td key={r.clave} className="px-4 py-3 align-top">
                          <span className="font-semibold text-tinta">{f.valor(r)}</span>
                          {f.detalle ? <span className="block text-sm text-tinta-suave">{f.detalle(r)}</span> : null}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="space-y-3 sm:hidden">
              {resultados.map((r) => (
                <li key={r.clave} className="rounded-xl border border-linea p-4">
                  <p className="flex items-center gap-2 font-semibold text-tinta">
                    <TeclaLinea color={colorSerie(huecos[r.clave] ?? 0)} />
                    {r.nombre}
                  </p>
                  <dl className="mt-2 space-y-1.5">
                    {FILAS.map((f) => (
                      <div key={f.etiqueta} className="flex items-baseline justify-between gap-3">
                        <dt className="text-sm text-tinta-suave">{f.etiqueta}</dt>
                        <dd className="cifras text-right font-semibold text-tinta">
                          {f.valor(r)}
                          {f.detalle ? <span className="block text-xs font-normal text-tinta-suave">{f.detalle(r)}</span> : null}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>
          </>
        ) : cargando ? (
          <Cargando texto="Calculando…" />
        ) : null}
      </div>
    </Hoja>
  );
}
