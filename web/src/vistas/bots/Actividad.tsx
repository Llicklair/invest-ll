"use client";

import { ArrowDownRight, ArrowUpRight, Banknote, CirclePause, CircleQuestionMark, Clock, Info, OctagonAlert, Play, Scale, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { MovimientoBot } from "@/api/tipos";
import { useAlmacenVivo, useVivo } from "@/api/vivo";
import { Esqueleto, clases } from "@/componentes/ui";
import { formatoImporte } from "@/lib/decimal";
import { haceCuanto, momento, signoImporteVisible } from "@/lib/formato";
import { useAhora } from "@/lib/reloj";

import { usdc } from "./comun";

const ICONO: Record<MovimientoBot["tipo"], typeof Play> = {
  compra: ArrowDownRight,
  venta: ArrowUpRight,
  arranque: Play,
  parada: CirclePause,
  error: OctagonAlert,
  hueco: Clock,
  info: Info,
  limite: ShieldAlert,
  desconocido: CircleQuestionMark,
  conciliacion: Scale,
  real: Banknote,
};
const PALABRA: Record<MovimientoBot["tipo"], string> = {
  compra: "Compra",
  venta: "Venta",
  arranque: "Arranque",
  parada: "Parada",
  error: "Error",
  hueco: "Hueco",
  info: "Aviso",
  limite: "Límite",
  desconocido: "Sin confirmar",
  conciliacion: "No cuadra",
  real: "Dinero real",
};
const TONO: Record<MovimientoBot["tipo"], string> = {
  compra: "bg-sube-suave text-sube-texto",
  venta: "bg-baja-suave text-baja-texto",
  arranque: "bg-marca-suave text-marca",
  parada: "bg-superficie-2 text-tinta-suave",
  error: "bg-real-suave text-real-tinta",
  hueco: "bg-pruebas-suave text-pruebas-tinta",
  info: "bg-superficie-2 text-tinta-suave",
  limite: "bg-pruebas-suave text-pruebas-tinta",
  desconocido: "bg-real-suave text-real-tinta",
  conciliacion: "bg-real-suave text-real-tinta",
  real: "bg-real-suave text-real-tinta",
};

/**
 * Lo que dejó una venta frente al coste medio de lo que tenía (como lo cuenta un exchange): una
 * venta puede salir en negativo aunque ese escalón se comprara más barato, si antes compró más caro.
 */
function Resultado({ valor }: { valor: string }) {
  const s = signoImporteVisible(valor);
  return (
    <span title="Lo cobrado, menos la comisión y lo que le costó de media lo vendido">
      frente a su coste medio:{" "}
      <span className={clases("font-semibold", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "text-tinta")}>{usdc(valor, { conSigno: true })}</span>
    </span>
  );
}

function FilaMovimiento({ m, ahora, nuevo, conBot }: { m: MovimientoBot; ahora: number; nuevo: boolean; conBot: boolean }) {
  const Icono = ICONO[m.tipo];
  const operacion = m.tipo === "compra" || m.tipo === "venta";
  return (
    <li className={clases("flex items-start gap-3 px-4 py-3 sm:px-5", nuevo && "destello-nuevo")}>
      <span className={clases("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", TONO[m.tipo])} aria-hidden="true">
        <Icono className="h-4 w-4" strokeWidth={2} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2 text-[0.9375rem] text-tinta">
          {conBot ? (
            <Link href={`/bots/ficha/?id=${encodeURIComponent(m.bot_id)}`} className="font-semibold hover:underline">
              {m.bot_nombre}
            </Link>
          ) : (
            <span className="font-semibold">{PALABRA[m.tipo]}</span>
          )}
          <time dateTime={m.at} title={momento(m.at)} className="text-sm text-tinta-suave">
            {haceCuanto(m.at, ahora)}
          </time>
        </p>
        <p className="mt-0.5 text-[0.9375rem] leading-relaxed text-tinta">
          {conBot && !operacion ? <span className="font-medium">{PALABRA[m.tipo]}. </span> : null}
          {m.texto}
        </p>
        {operacion && m.importe ? (
          <p className="cifras mt-0.5 text-sm text-tinta-suave">
            {usdc(m.importe)}
            {m.comision ? ` · comisión ${formatoImporte(m.comision, { decimales: 2 })} USDC` : ""}
            {m.resultado ? (
              <>
                {" · "}
                <Resultado valor={m.resultado} />
              </>
            ) : null}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/**
 * "Ahora mismo" (docs/panel-v5.md §3 y §4): los movimientos de los bots según ocurren, lo nuevo
 * arriba y resaltado un momento. Llegan por el canal `actividad` del stream (hay que estar dentro
 * de un `ProveedorVivo` que lo pida). Con `botId`, solo los de ese bot. Las notas de la plantilla
 * ("Esperando historia…", que sale cada vez que se reabre el panel) solo van en el feed de un bot:
 * el de todos es de movimientos.
 */
export function FeedActividad({
  botId,
  limite = 12,
  titulo = "Ahora mismo",
  bajada,
  className,
}: {
  botId?: string;
  limite?: number;
  titulo?: string;
  bajada?: string;
  className?: string;
}) {
  const todos = useVivo("actividad");
  const almacen = useAlmacenVivo();
  const ahora = useAhora();
  const [mas, setMas] = useState(false);
  const lista = (todos ?? []).filter((m) => (botId === undefined ? m.tipo !== "info" : m.bot_id === botId));
  const vistos = mas ? lista : lista.slice(0, limite);
  return (
    <section aria-labelledby={`feed-${botId ?? "todos"}`} className={clases("overflow-hidden rounded-tarjeta border border-linea bg-superficie shadow-suave", className)}>
      <header className="flex items-start justify-between gap-3 border-b border-linea px-4 pt-4 pb-3 sm:px-5">
        <div>
          <h2 id={`feed-${botId ?? "todos"}`} className="flex items-center gap-2 titular text-lg font-semibold text-tinta">
            <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-sube motion-reduce:animate-none" />
            {titulo}
          </h2>
          <p className="mt-0.5 text-sm text-tinta-suave">{bajada ?? "Cada compra, venta y aviso, en cuanto pasa."}</p>
        </div>
      </header>
      {todos === null ? (
        <div className="space-y-3 p-4">
          <Esqueleto className="h-12" />
          <Esqueleto className="h-12" />
          <Esqueleto className="h-12" />
        </div>
      ) : !lista.length ? (
        <p className="px-4 py-6 text-[0.9375rem] text-tinta-suave sm:px-5">Aún no ha pasado nada. Lo primero que haga aparecerá aquí al momento.</p>
      ) : (
        <>
          {/* Un lector de pantalla oye lo nuevo sin tener que buscarlo (sin repetir la lista entera). */}
          <ol className="divide-y divide-linea" aria-live="polite" aria-relevant="additions">
            {vistos.map((m) => (
              <FilaMovimiento key={m.id} m={m} ahora={ahora} nuevo={almacen.recientes.has(m.id)} conBot={botId === undefined} />
            ))}
          </ol>
          {lista.length > limite ? (
            <button
              type="button"
              onClick={() => setMas((v) => !v)}
              aria-expanded={mas}
              className="w-full border-t border-linea px-4 py-3 text-left text-[0.9375rem] font-semibold text-marca hover:bg-superficie-2 sm:px-5"
            >
              {mas ? "Ver solo lo último" : `Ver los ${lista.length} movimientos`}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}
