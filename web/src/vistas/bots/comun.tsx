"use client";

import { CirclePause, FlaskConical, OctagonAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { EstadoBot, EvidenciaBot, PuntoBot, ResumenBot } from "@/api/tipos";
import { Chip, clases } from "@/componentes/ui";
import { formatoImporte, signoDecimal } from "@/lib/decimal";
import { SIN_DATO, fraccion, fraccionCoherente } from "@/lib/formato";

export const NOTA_BOTS = "Dinero ficticio. Los bots solo funcionan mientras el panel está abierto.";

/** "1.234,56 USDC" desde un Decimal en cadena, con el menos tipografico. */
export function usdc(v: string | null | undefined, opciones: { conSigno?: boolean; decimales?: number } = {}): string {
  if (v === null || v === undefined) return SIN_DATO;
  return `${formatoImporte(v, opciones).replace(/^-/, "−")} USDC`;
}

/** La nota que acompana a todo lo de Bots (docs/panel-v3-vivo.md, seccion 3). */
export function NotaBots({ texto, className }: { texto?: string | null; className?: string }) {
  return (
    <p className={clases("inline-flex items-start gap-1.5 rounded-xl bg-pruebas-suave px-3 py-2 text-sm font-medium text-pruebas-tinta", className)}>
      <FlaskConical aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2} />
      {texto || NOTA_BOTS}
    </p>
  );
}

/** En marcha · Parado · Con error: icono + palabra, el color nunca va solo. */
export function EstadoChip({ estado, className }: { estado: EstadoBot; className?: string }) {
  if (estado === "en_marcha") {
    return (
      <Chip tono="sube" className={className} icono={<span aria-hidden="true" className="h-2 w-2 rounded-full bg-sube" />}>
        En marcha
      </Chip>
    );
  }
  if (estado === "parado") {
    return (
      <Chip tono="neutro" className={className} icono={<CirclePause aria-hidden="true" className="h-3.5 w-3.5" />}>
        Parado
      </Chip>
    );
  }
  return (
    <Chip tono="real" className={className} icono={<OctagonAlert aria-hidden="true" className="h-3.5 w-3.5" />}>
      Con error
    </Chip>
  );
}

/** La evidencia de la plantilla, en la tarjeta del bot (no solo al crearlo). */
export function ChipEvidenciaBot({ evidencia, className }: { evidencia: EvidenciaBot; className?: string }) {
  const corto = evidencia.tipo === "ninguna" ? "Sin pruebas: experimento" : evidencia.tipo === "prueba_real" ? "En prueba real" : "Probada sobre el pasado";
  return (
    <Chip tono={evidencia.tipo === "ninguna" ? "pruebas" : "marca"} className={className}>
      {corto}
    </Chip>
  );
}

function Grande({ pct, signo, tamano, children }: { pct: number | null; signo: -1 | 0 | 1 | null; tamano: "normal" | "grande"; children?: ReactNode }) {
  const texto = signo === null || pct === null ? SIN_DATO : fraccionCoherente(pct, signo);
  return (
    <p
      className={clases(
        "mt-0.5 leading-none font-semibold tracking-tight",
        tamano === "grande" ? "text-[2rem] sm:text-[2.75rem]" : "text-[1.75rem] sm:text-[2rem]",
        signo === 1 ? "text-sube-texto" : signo === -1 ? "text-baja-texto" : "text-tinta",
      )}
    >
      {texto}
      {children}
    </p>
  );
}

const signoDe = (x: number | null | undefined): -1 | 0 | 1 | null => (x === null || x === undefined || !Number.isFinite(x) ? null : x > 0.00005 ? 1 : x < -0.00005 ? -1 : 0);

/**
 * Lo que ha generado el bot y lo que habria hecho "solo mantener" desde el mismo momento, AL
 * MISMO TAMANO (docs/panel-v2.md, principio 2: nunca una rentabilidad sin su comparacion). Debajo,
 * en una frase, quien va por delante, y si es pronto para sacar conclusiones.
 */
export function CifrasBot({ bot, tamano = "normal" }: { bot: Pick<ResumenBot, "ganancia" | "ganancia_pct" | "mantener_pct" | "dias">; tamano?: "normal" | "grande" }) {
  const sg = bot.ganancia === null ? null : signoDecimal(bot.ganancia);
  const sm = signoDe(bot.mantener_pct);
  const dif = bot.ganancia_pct !== null && bot.mantener_pct !== null ? bot.ganancia_pct - bot.mantener_pct : null;
  const puntos = dif === null ? null : Math.abs(dif * 100).toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  let veredicto: string | null = null;
  if (dif !== null && puntos !== null) {
    if (puntos === "0,0") veredicto = "Por ahora, lo mismo que solo mantener.";
    else if (dif > 0) veredicto = `Por ahora, el bot va ${puntos} ${puntos === "1,0" ? "punto" : "puntos"} por delante de solo mantener.`;
    else veredicto = `Por ahora, solo mantener habría ganado ${puntos} ${puntos === "1,0" ? "punto" : "puntos"} más.`;
  }
  const pronto = bot.dias < 7 ? ` Lleva ${bot.dias < 1 ? "menos de un día" : `${Math.floor(bot.dias)} ${Math.floor(bot.dias) === 1 ? "día" : "días"}`}: es pronto para sacar conclusiones.` : "";
  return (
    <div>
      <div className={clases("grid grid-cols-2 gap-3", tamano === "grande" && "sm:gap-6")}>
        <div className={clases("rounded-xl bg-superficie-2 px-3 py-2.5", tamano === "grande" && "sm:px-5 sm:py-4")}>
          <p className="text-sm text-tinta-suave">Ha generado</p>
          <Grande pct={bot.ganancia_pct} signo={sg} tamano={tamano} />
          <p className="cifras mt-1 text-sm font-medium text-tinta">{usdc(bot.ganancia, { conSigno: true })}</p>
        </div>
        <div className={clases("rounded-xl bg-superficie-2 px-3 py-2.5", tamano === "grande" && "sm:px-5 sm:py-4")}>
          <p className="text-sm text-tinta-suave">Si solo hubieras mantenido</p>
          <Grande pct={bot.mantener_pct} signo={sm} tamano={tamano} />
          <p className="mt-1 text-sm text-tinta-suave">desde el mismo momento</p>
        </div>
      </div>
      {veredicto || pronto ? (
        <p className="mt-2 text-sm leading-relaxed text-tinta">
          {veredicto}
          <span className="text-tinta-suave">{pronto}</span>
        </p>
      ) : null}
    </div>
  );
}

/** Una cifra pequena de la tarjeta (hoy, peor caida, dias, operaciones). */
export function Dato({ etiqueta, children, className }: { etiqueta: string; children: ReactNode; className?: string }) {
  return (
    <div className={clases("min-w-0", className)}>
      <dt className="text-xs text-tinta-suave">{etiqueta}</dt>
      <dd className="cifras text-[0.9375rem] font-semibold text-tinta">{children}</dd>
    </div>
  );
}

export function PctColor({ valor }: { valor: number | null | undefined }) {
  const s = signoDe(valor);
  return <span className={s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : undefined}>{valor === null || valor === undefined ? SIN_DATO : fraccion(valor, 1)}</span>;
}

/** Dias en marcha, en llano: "12 días", "5 horas". */
export function diasTexto(dias: number): string {
  if (dias < 1 / 24) return "menos de una hora";
  if (dias < 1) {
    const h = Math.max(1, Math.round(dias * 24));
    return `${h} ${h === 1 ? "hora" : "horas"}`;
  }
  const d = Math.floor(dias);
  return `${d} ${d === 1 ? "día" : "días"}`;
}

/**
 * La curva pequena de la tarjeta (SVG propio): lo que vale el bot, en el color de su serie (el
 * mismo azul que en la ficha), con un lavado al 10 % y un filete en el capital puesto para ver
 * de un vistazo si esta por encima o por debajo. Es redundante con las cifras de al lado: se
 * oculta a los lectores de pantalla.
 */
export function MiniCurva({ curva, capital, alto = 56, className }: { curva: readonly PuntoBot[]; capital: number; alto?: number; className?: string }) {
  const ancho = 300;
  if (curva.length < 2) {
    return <div aria-hidden="true" className={clases("flex items-center justify-center rounded-lg bg-superficie-2 text-xs text-tinta-suave", className)} style={{ height: alto }}>Aún sin curva</div>;
  }
  const t0 = Date.parse(curva[0]?.at ?? "");
  const t1 = Date.parse(curva[curva.length - 1]?.at ?? "");
  const valores = curva.map((p) => p.valor);
  // Como poco un 1 % arriba y abajo del capital: un -0,2 % no puede parecer un desplome.
  const min = Math.min(capital * 0.99, ...valores);
  const max = Math.max(capital * 1.01, ...valores);
  const m = 4;
  const rango = max - min || 1;
  const x = (at: string) => m + ((Date.parse(at) - t0) / (t1 - t0 || 1)) * (ancho - 2 * m);
  const y = (v: number) => m + (1 - (v - min) / rango) * (alto - 2 * m);
  const camino = curva.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.at).toFixed(1)},${y(p.valor).toFixed(1)}`).join("");
  const ultimo = curva[curva.length - 1];
  const yCapital = y(capital);
  return (
    <svg viewBox={`0 0 ${ancho} ${alto}`} preserveAspectRatio="none" aria-hidden="true" className={clases("block w-full", className)} style={{ height: alto }}>
      <path d={`${camino}L${x(ultimo?.at ?? "").toFixed(1)},${alto - m}L${m},${alto - m}Z`} fill="var(--serie-1)" opacity="0.1" />
      <line x1={m} x2={ancho - m} y1={yCapital} y2={yCapital} stroke="var(--eje)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      <path d={camino} fill="none" stroke="var(--serie-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
