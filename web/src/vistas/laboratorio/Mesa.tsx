"use client";

import { useState } from "react";

import type { FilaRendimiento } from "@/api/tipos";
import { Sparkline } from "@/componentes/graficas/Sparkline";
import { MarcoTabla, Td, TdVariacion, Th } from "@/componentes/tabla";
import { clases } from "@/componentes/ui";
import { fecha, numero } from "@/lib/formato";

type Clave = keyof FilaRendimiento;

interface Columna {
  clave: Clave;
  texto: string;
  tipo: "texto" | "precio" | "variacion" | "sparkline" | "fecha";
  destacada?: boolean;
}

/**
 * La forma de CoinMarketCap sin sus anzuelos: densidad, variaciones por ventana, una sparkline
 * por fila y ordenacion por cabecera. Ni 1h%, ni tendencias, ni ganadores del dia.
 */
const COLUMNAS: Columna[] = [
  { clave: "activo", texto: "activo", tipo: "texto" },
  { clave: "que_es", texto: "qué es", tipo: "texto" },
  { clave: "ultimo", texto: "precio", tipo: "precio" },
  { clave: "var_1d", texto: "1 día", tipo: "variacion" },
  { clave: "var_1s", texto: "1 semana", tipo: "variacion" },
  { clave: "var_1m", texto: "1 mes", tipo: "variacion" },
  { clave: "var_3m", texto: "3 meses", tipo: "variacion" },
  { clave: "ytd", texto: "YTD", tipo: "variacion" },
  { clave: "var_1a", texto: "1 año", tipo: "variacion" },
  { clave: "var_5a", texto: "5 años", tipo: "variacion" },
  { clave: "desde_maximo", texto: "desde máximo", tipo: "variacion", destacada: true },
  { clave: "sparkline", texto: "3 meses (gráfico)", tipo: "sparkline" },
  { clave: "datos_hasta", texto: "datos hasta", tipo: "fecha" },
];

type Orden = { clave: Clave; ascendente: boolean } | null;

function comparar(a: FilaRendimiento, b: FilaRendimiento, orden: NonNullable<Orden>): number {
  const x = a[orden.clave];
  const y = b[orden.clave];
  // Los huecos (sin historico suficiente) van siempre al final: no son un 0%.
  if (x === null && y === null) return 0;
  if (x === null) return 1;
  if (y === null) return -1;
  let r = 0;
  if (typeof x === "number" && typeof y === "number") r = x - y;
  else r = String(x).localeCompare(String(y), "es");
  return orden.ascendente ? r : -r;
}

export function Mesa({
  titulo,
  filas,
  elegido,
  onElegir,
}: {
  titulo: string;
  filas: readonly FilaRendimiento[];
  elegido: string | null;
  onElegir: (activo: string) => void;
}) {
  const [orden, setOrden] = useState<Orden>(null);
  const ordenadas = orden ? [...filas].sort((a, b) => comparar(a, b, orden)) : filas;

  const alternar = (clave: Clave) =>
    setOrden((o) =>
      o && o.clave === clave
        ? o.ascendente
          ? { clave, ascendente: false }
          : null
        : { clave, ascendente: clave === "activo" || clave === "que_es" },
    );

  return (
    <div className="space-y-1.5">
      <h3 className="text-[0.9375rem] font-semibold text-tinta">
        {titulo} <span className="font-normal text-tinta-suave">— {filas.length} activo(s)</span>
      </h3>
      <MarcoTabla etiqueta={`Rendimiento por periodo: ${titulo.toLowerCase()}`}>
        <thead>
          <tr>
            {COLUMNAS.map((c) => {
              const activa = orden?.clave === c.clave;
              const ordenable = c.tipo !== "sparkline";
              return (
                <Th
                  key={c.clave}
                  numerica={c.tipo === "precio" || c.tipo === "variacion"}
                  aria-sort={activa ? (orden?.ascendente ? "ascending" : "descending") : undefined}
                  className={clases(c.destacada && "bg-superficie-2 text-tinta")}
                >
                  {ordenable ? (
                    <button
                      type="button"
                      onClick={() => alternar(c.clave)}
                      className={clases("inline-flex items-center gap-1 hover:text-tinta", c.destacada && "font-bold")}
                      title={`Ordenar por ${c.texto}`}
                    >
                      {c.texto}
                      <span aria-hidden="true" className="w-2 text-tinta-suave">
                        {activa ? (orden?.ascendente ? "▲" : "▼") : ""}
                      </span>
                    </button>
                  ) : (
                    c.texto
                  )}
                </Th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {ordenadas.map((f) => {
            const seleccionada = f.activo === elegido;
            const primero = f.sparkline[0];
            const ultimo = f.sparkline[f.sparkline.length - 1];
            return (
              <tr
                key={f.activo}
                onClick={() => onElegir(f.activo)}
                className={clases("cursor-pointer hover:bg-superficie-2", seleccionada && "bg-superficie-2")}
              >
                <Td>
                  <button
                    type="button"
                    aria-pressed={seleccionada}
                    aria-label={`Ver la gráfica de ${f.activo}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onElegir(f.activo);
                    }}
                    className="font-semibold text-tinta underline-offset-2 hover:underline"
                  >
                    {f.activo}
                  </button>
                </Td>
                <Td className="text-tinta-suave">{f.que_es}</Td>
                <Td numerica>{numero(f.ultimo, 2)}</Td>
                <TdVariacion valor={f.var_1d} />
                <TdVariacion valor={f.var_1s} />
                <TdVariacion valor={f.var_1m} />
                <TdVariacion valor={f.var_3m} />
                <TdVariacion valor={f.ytd} />
                <TdVariacion valor={f.var_1a} />
                <TdVariacion valor={f.var_5a} />
                <TdVariacion valor={f.desde_maximo} className="bg-superficie-2 font-bold" />
                <Td>
                  <Sparkline valores={f.sparkline} />
                  <span className="sr-only">
                    {primero !== undefined && ultimo !== undefined
                      ? `Últimas ${f.sparkline.length} sesiones: de ${numero(primero, 2)} a ${numero(ultimo, 2)}`
                      : "Sin datos para la minigráfica"}
                  </span>
                </Td>
                <Td className="text-tinta-suave">{fecha(f.datos_hasta)}</Td>
              </tr>
            );
          })}
        </tbody>
      </MarcoTabla>
    </div>
  );
}

