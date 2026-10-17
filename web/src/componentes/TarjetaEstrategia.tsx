"use client";

import { Bot, History, Info, Hand, Sparkles, TriangleAlert, Timer } from "lucide-react";
import type { ReactNode } from "react";

import type { Estrategia, ResultadoSimulado } from "@/api/tipos";
import { eurosNum, fecha, mesYAnio } from "@/lib/formato";

import { MedidorRiesgo } from "./MedidorRiesgo";
import { TeclaLinea } from "./graficas/comun";
import { Chip, Esqueleto, Tarjeta, clases } from "./ui";

export function textoEjecucion(e: Pick<Estrategia, "ejecucion">): { corto: string; largo: string } {
  return e.ejecucion === "binance"
    ? { corto: "Automático en Binance", largo: "Automático en Binance (tú confirmas cada orden)" }
    : { corto: "Lo compras tú", largo: "Lo compras tú en tu bróker; te decimos qué y cuánto" };
}

export function Ejecucion({ estrategia, className }: { estrategia: Estrategia; className?: string }) {
  const Icono = estrategia.ejecucion === "binance" ? Bot : Hand;
  return (
    <p className={clases("flex items-start gap-2 text-[0.9375rem] text-tinta", className)}>
      <Icono aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-tinta-suave" strokeWidth={1.75} />
      {textoEjecucion(estrategia).largo}
    </p>
  );
}

export function ChipEvidencia({ estrategia }: { estrategia: Estrategia }) {
  const real = estrategia.evidencia.tipo === "prueba_real";
  return (
    <Chip
      tono={real ? "sube" : "neutro"}
      icono={real ? <Timer aria-hidden="true" className="h-3.5 w-3.5" /> : <History aria-hidden="true" className="h-3.5 w-3.5" />}
    >
      {estrategia.evidencia.texto}
    </Chip>
  );
}

/** Una de las dos cifras de la tarjeta: resultado y peor momento van SIEMPRE al mismo tamano. */
function Cifra({ etiqueta, valor, detalle }: { etiqueta: string; valor: ReactNode; detalle: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-superficie-2 px-3 py-3 sm:px-4">
      <p className="min-h-[2.5em] text-[0.8125rem] leading-tight text-tinta-suave sm:min-h-0 sm:text-sm">{etiqueta}</p>
      <p className="titular mt-0.5 text-[1.5rem] leading-tight font-medium text-tinta sm:text-[1.75rem]">{valor}</p>
      <p className="mt-1 text-[0.8125rem] leading-snug text-tinta-suave sm:text-sm">{detalle}</p>
    </div>
  );
}

/**
 * Una estrategia del catalogo, contada para quien no sabe de inversiones: que es, cuanto se
 * mueve, que habria pasado CON SUS NUMEROS (y su peor momento al lado, igual de grande), quien
 * la ejecuta y que pruebas hay de que funciona.
 */
export function TarjetaEstrategia({
  estrategia: e,
  simulado,
  cargando,
  desdeAnio,
  ejemplo,
  recomendada,
  color,
  comparando,
  elegida,
  onElegir,
  onVerMas,
  bloqueoComparar,
}: {
  estrategia: Estrategia;
  simulado: ResultadoSimulado | null;
  cargando: boolean;
  desdeAnio: number;
  /** Se simula con 10.000 € de ejemplo porque la persona no ha puesto cifras. */
  ejemplo: boolean;
  recomendada: number | null;
  /** Color de su linea si esta en la grafica. */
  color: string | null;
  comparando: boolean;
  elegida: boolean;
  onElegir: (si: boolean) => void;
  onVerMas: () => void;
  bloqueoComparar?: string | null;
}) {
  const desde = simulado ? fecha(simulado.desde) : String(desdeAnio);
  return (
    <Tarjeta
      como="article"
      className={clases(
        "flex scroll-mt-24 flex-col gap-5 p-5 sm:p-6",
        recomendada !== null && "ring-2 ring-destaque/70",
        elegida && "ring-2 ring-marca",
      )}
      aria-labelledby={`titulo-${e.clave}`}
      id={`estrategia-${e.clave}`}
    >
      <div className="space-y-3">
        {recomendada !== null ? (
          <Chip tono="destaque" icono={<Sparkles aria-hidden="true" className="h-3.5 w-3.5" />}>
            Recomendada · {recomendada} % de tu plan
          </Chip>
        ) : null}
        <div className="flex items-start gap-3">
          <h3 id={`titulo-${e.clave}`} className="titular min-w-0 flex-1 text-[1.5rem] leading-tight font-semibold text-tinta">
            {e.nombre}
          </h3>
          {color ? (
            <span className="mt-2 flex items-center gap-1.5 text-xs text-tinta-suave">
              <TeclaLinea color={color} />
              en la gráfica
            </span>
          ) : null}
        </div>
        <p className="text-[0.9375rem] leading-relaxed text-tinta-suave">{e.frase}</p>
        <MedidorRiesgo nivel={e.riesgo} texto={e.riesgo_texto} />
      </div>

      {!e.disponible ? (
        <p className="flex gap-2 rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">
          <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-tinta-suave" />
          {e.motivo ?? "Faltan datos para calcularla."}
        </p>
      ) : simulado ? (
        <div className={clases("space-y-2", cargando && "opacity-50 transition-opacity")}>
          <p className="text-sm text-tinta-suave">
            {ejemplo ? "Con 10.000 € de ejemplo" : "Con tus números"} desde {desde}:
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Cifra etiqueta="Tendrías" valor={eurosNum(simulado.valor_final)} detalle={`Pusiste ${eurosNum(simulado.aportado)}`} />
            <Cifra
              etiqueta="En el peor momento"
              valor={eurosNum(simulado.peor_momento_valor)}
              detalle={`${mesYAnio(simulado.peor_momento_fecha)} · habías puesto ${eurosNum(simulado.peor_momento_aportado)}`}
            />
          </div>
          {simulado.aviso ? <p className="text-sm text-tinta-suave">{simulado.aviso}</p> : null}
        </div>
      ) : cargando ? (
        <div className="grid grid-cols-2 gap-2" aria-hidden="true">
          <Esqueleto className="h-[6.5rem]" />
          <Esqueleto className="h-[6.5rem]" />
        </div>
      ) : (
        <p className="text-[0.9375rem] text-tinta-suave">Sin cifras para estos números.</p>
      )}

      <div className="space-y-3">
        <Ejecucion estrategia={e} />
        <ChipEvidencia estrategia={e} />
      </div>

      {e.avisos.length ? (
        <ul className="space-y-1.5">
          {e.avisos.map((a) => (
            <li key={a} className="flex gap-2 text-sm leading-relaxed text-tinta-suave">
              <TriangleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-pruebas" strokeWidth={1.75} />
              {a}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-linea pt-4">
        <button
          type="button"
          onClick={onVerMas}
          className="inline-flex min-h-11 items-center rounded-xl px-1 text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline"
        >
          Ver cómo funciona
        </button>
        {comparando ? (
          <label
            className={clases(
              "inline-flex min-h-11 cursor-pointer items-center gap-2.5 rounded-xl border px-4 text-[0.9375rem] font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco",
              elegida ? "border-marca bg-marca-suave text-marca" : "border-linea-control/60 text-tinta",
              bloqueoComparar && !elegida && "cursor-not-allowed opacity-50",
            )}
            title={bloqueoComparar && !elegida ? bloqueoComparar : undefined}
          >
            <input
              type="checkbox"
              checked={elegida}
              disabled={Boolean(bloqueoComparar) && !elegida}
              onChange={(ev) => onElegir(ev.target.checked)}
              className="h-5 w-5 accent-[var(--marca)]"
            />
            Comparar
          </label>
        ) : null}
      </div>
    </Tarjeta>
  );
}
