"use client";

import { Clock, FlaskConical, RefreshCw, TriangleAlert, WifiOff } from "lucide-react";

import { useConexionVivo, type EstadoConexion } from "@/api/vivo";
import { horaSegundos } from "@/lib/vivo";

import { clases } from "./ui";

interface Lectura {
  palabra: string;
  detalle: string | null;
  tono: "vivo" | "aviso" | "neutro" | "critico";
}

function leer({ conexion, fuente }: EstadoConexion): Lectura {
  switch (conexion.tipo) {
    case "conectando":
      return { palabra: "Conectando…", detalle: null, tono: "neutro" };
    case "en-vivo":
      if (fuente && !fuente.conectado) return { palabra: "Sin datos de Hyperliquid", detalle: fuente.aviso, tono: "aviso" };
      return { palabra: "En vivo", detalle: null, tono: "vivo" };
    case "reconectando":
      return { palabra: "Reconectando…", detalle: "Se cortó la conexión en directo; el panel reintenta solo.", tono: "aviso" };
    case "sondeo":
      return {
        palabra: `Cada ${Math.round(conexion.cadaMs / 1000)} s`,
        detalle: fuente && !fuente.conectado ? fuente.aviso : "Sin conexión en directo: el panel pregunta cada pocos segundos.",
        tono: fuente && !fuente.conectado ? "aviso" : "neutro",
      };
    case "sin-conexion":
      return { palabra: "Sin conexión", detalle: conexion.detalle, tono: "critico" };
  }
}

const ESTILO = {
  vivo: "bg-sube-suave text-sube-texto",
  aviso: "bg-pruebas-suave text-pruebas-tinta",
  neutro: "bg-superficie-2 text-tinta-suave",
  critico: "bg-real-suave text-real-tinta",
} as const;

/**
 * El estado de los datos en vivo, siempre a la vista y honesto (docs/panel-v3-vivo.md, regla 2):
 * si llegan en directo, si se esta reconectando o preguntando cada pocos segundos, la fuente y la
 * hora de los datos que se ven. Icono + palabra: el color nunca va solo. Solo la palabra es una
 * region viva (se anuncia al cambiar); la hora, que cambia cada segundo, no.
 */
export function EstadoEnVivo({ className, conDetalle = false }: { className?: string; conDetalle?: boolean }) {
  const estado = useConexionVivo();
  const l = leer(estado);
  const Icono = l.tono === "critico" ? WifiOff : l.tono === "aviso" ? (estado.conexion.tipo === "reconectando" ? RefreshCw : TriangleAlert) : estado.conexion.tipo === "sondeo" ? Clock : null;
  const fuente = estado.fuente?.fuente ?? "Hyperliquid";
  return (
    <div className={clases("min-w-0", className)}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm" title={l.detalle ?? undefined}>
        <span className={clases("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold", ESTILO[l.tono])}>
          {Icono ? (
            <Icono aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2.25} />
          ) : (
            <span aria-hidden="true" className={clases("h-2 w-2 rounded-full", l.tono === "vivo" ? "bg-sube" : "bg-tinta-suave")} />
          )}
          <span role="status" aria-live="polite">
            {l.palabra}
          </span>
        </span>
        <span className="cifras text-tinta-suave">
          {fuente} · {estado.ultimoDato === null ? "sin datos aún" : `datos de las ${horaSegundos(estado.ultimoDato)}`}
        </span>
      </p>
      {conDetalle && l.detalle ? <p className="mt-1 text-sm text-tinta-suave">{l.detalle}</p> : null}
    </div>
  );
}

/** El rotulo unico de Operar y Bots: de donde salen los precios y que el dinero no es de verdad. */
export function RotuloFicticio({ className, texto = "Precios en vivo de Hyperliquid. Dinero ficticio." }: { className?: string; texto?: string }) {
  return (
    <p className={clases("inline-flex items-center gap-1.5 rounded-full bg-pruebas-suave px-3 py-1 text-sm font-semibold text-pruebas-tinta", className)}>
      <FlaskConical aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
      {texto}
    </p>
  );
}
