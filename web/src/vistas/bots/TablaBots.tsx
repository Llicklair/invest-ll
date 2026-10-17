"use client";

import { TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import type { ResumenBot } from "@/api/tipos";
import { clases } from "@/componentes/ui";
import { fraccion, haceCuanto, signoImporteVisible, signoVisible } from "@/lib/formato";
import { useAhora } from "@/lib/reloj";

import { EstadoChip, MiniCurva, PctColor, usdc } from "./comun";
import { ChipModo, pausadoSolo } from "./real";

/**
 * Una cifra que destella al cambiar: verde si sube, roja si baja (como en un exchange). Se
 * compara al pintar (patron de React para estado que depende de una prop), y la `key` vuelve a
 * montar el trozo para que la animacion empiece de nuevo.
 */
function CifraViva({ valor, children, className }: { valor: string | null; children: ReactNode; className?: string }) {
  const [previo, setPrevio] = useState(valor);
  const [hacia, setHacia] = useState<"sube" | "baja" | null>(null);
  if (valor !== previo) {
    setPrevio(valor);
    setHacia(valor !== null && previo !== null ? (Number(valor) > Number(previo) ? "sube" : "baja") : null);
  }
  return (
    <span key={valor ?? "—"} className={clases("-mx-1 rounded px-1", hacia && `destello-${hacia}`, className)}>
      {children}
    </span>
  );
}

/** Puntos por encima (o por debajo) de solo mantener: "+2,1 p." */
function FrenteAMantener({ bot }: { bot: ResumenBot }) {
  if (bot.ganancia_pct === null || bot.mantener_pct === null) return <span className="text-tinta-suave">—</span>;
  const d = bot.ganancia_pct - bot.mantener_pct;
  const texto = `${fraccion(d, 1).replace(/\s*%$/, "")} p.`;
  const s = signoVisible(d, texto);
  return (
    <span className={s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : undefined} title="Puntos de ganancia por encima (o por debajo) de solo mantener sus monedas">
      {texto}
    </span>
  );
}

function FilaBot({ bot, ahora }: { bot: ResumenBot; ahora: number }) {
  const s = signoImporteVisible(bot.ganancia);
  const problema = bot.estado === "error" || pausadoSolo(bot);
  return (
    <tr className="relative border-t border-linea hover:bg-superficie-2/60">
      <th scope="row" className="min-w-[11rem] py-3 pr-3 pl-4 text-left font-normal @max-md:min-w-0 @max-md:pr-2 @md:pl-5">
        <Link
          href={`/bots/ficha/?id=${encodeURIComponent(bot.id)}`}
          className="font-semibold text-tinta after:absolute after:inset-0 hover:underline focus-visible:outline-none"
        >
          {bot.nombre}
        </Link>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-tinta-suave">
          {bot.modo !== "ficticio" ? <ChipModo modo={bot.modo} exchange={bot.exchange} /> : null}
          {bot.nombre_plantilla} · {bot.monedas.join(", ")}
        </span>
        {bot.aviso || bot.motivo_error ? (
          <span className={clases("mt-1 flex items-start gap-1 text-sm", problema ? "text-real-tinta" : "text-pruebas-tinta")}>
            <TriangleAlert aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="line-clamp-2">{bot.motivo_error ?? bot.aviso}</span>
          </span>
        ) : null}
      </th>
      <td className="px-3 py-3 @max-2xl:hidden">
        <EstadoChip estado={bot.estado} />
      </td>
      <td className="cifras px-3 py-3 text-right font-medium whitespace-nowrap text-tinta">
        <CifraViva valor={bot.valor}>{usdc(bot.valor)}</CifraViva>
      </td>
      <td className="cifras px-3 py-3 text-right whitespace-nowrap">
        <span className={clases("block font-medium", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "text-tinta")}>
          <PctColor valor={bot.ganancia_pct} />
        </span>
        <span className="block text-sm text-tinta-suave @max-md:hidden">{usdc(bot.ganancia, { conSigno: true })}</span>
      </td>
      <td className="cifras px-3 py-3 text-right whitespace-nowrap @max-3xl:hidden">
        <FrenteAMantener bot={bot} />
      </td>
      <td className="cifras px-3 py-3 text-right whitespace-nowrap @max-lg:hidden">
        <PctColor valor={bot.ganancia_24h_pct} />
      </td>
      <td className="w-32 px-3 py-3 @max-5xl:hidden">
        <MiniCurva curva={bot.curva} capital={Number(bot.capital)} alto={32} />
      </td>
      <td className="py-3 pr-4 pl-3 text-right text-sm whitespace-nowrap text-tinta-suave @max-md:hidden @md:pr-5">
        {bot.ultima_actividad ? haceCuanto(bot.ultima_actividad, ahora) : "sin operar aún"}
        <span className="block">{bot.operaciones.toLocaleString("es-ES")} op.</span>
      </td>
    </tr>
  );
}

/**
 * Los bots en una tabla en directo (docs/panel-v5.md §4), como las vaults de Hyperliquid: lo que
 * vale cada uno (destella al cambiar), lo que gana, frente a solo mantener, hoy, su curva y cuánto
 * hace de su último movimiento. Las columnas se quedan según el sitio que tiene la tabla (al lado
 * del feed cabe menos que sola), no según la ventana.
 */
export function TablaBots({ bots, etiqueta }: { bots: readonly ResumenBot[]; etiqueta: string }) {
  const ahora = useAhora();
  return (
    <div className="@container overflow-x-auto">
      <table className="w-full text-[0.9375rem]">
        <caption className="sr-only">{etiqueta}</caption>
        <thead className="text-xs text-tinta-suave">
          <tr>
            <th scope="col" className="pb-2 pl-4 text-left font-medium sm:pl-5">
              Bot
            </th>
            <th scope="col" className="px-3 pb-2 text-left font-medium @max-2xl:hidden">
              Estado
            </th>
            <th scope="col" className="px-3 pb-2 text-right font-medium">
              Vale
            </th>
            <th scope="col" className="px-3 pb-2 text-right font-medium">
              Ganancia
            </th>
            <th scope="col" className="px-3 pb-2 text-right font-medium @max-3xl:hidden">
              Frente a mantener
            </th>
            <th scope="col" className="px-3 pb-2 text-right font-medium @max-lg:hidden">
              Hoy
            </th>
            <th scope="col" className="px-3 pb-2 font-medium @max-5xl:hidden">
              <span className="sr-only">Curva</span>
            </th>
            <th scope="col" className="pr-4 pb-2 pl-3 text-right font-medium @max-md:hidden @md:pr-5">
              Último movimiento
            </th>
          </tr>
        </thead>
        <tbody>
          {bots.map((b) => (
            <FilaBot key={b.id} bot={b} ahora={ahora} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
