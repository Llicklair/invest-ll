"use client";

import { Activity, Banknote, History, PencilLine, Sparkles, UserRound } from "lucide-react";
import { useMemo } from "react";

import type { AutorEstrategia, EstadoEstrategia, ResultadoPrueba } from "@/api/tipos";
import { Chip, clases } from "@/componentes/ui";
import { formatoImporte } from "@/lib/decimal";
import { fecha, fraccion, signoVisible } from "@/lib/formato";
import { useGuardado } from "@/lib/almacen";
import { nombreExchange } from "@/lib/nombres";
import { nombreIntervalo } from "@/lib/vivo";

const ESTADO: Record<EstadoEstrategia, { texto: string; tono: "neutro" | "marca" | "destaque" | "real"; Icono: typeof History }> = {
  borrador: { texto: "Borrador", tono: "neutro", Icono: PencilLine },
  probada: { texto: "Probada sobre el pasado", tono: "marca", Icono: History },
  ficticio: { texto: "En ficticio", tono: "destaque", Icono: Activity },
  real: { texto: "Con dinero real", tono: "real", Icono: Banknote },
};

/** Borrador · probada · en ficticio · real: el camino de una estrategia, con icono y palabra. */
export function ChipEstadoEstrategia({ estado, className }: { estado: EstadoEstrategia; className?: string }) {
  const e = ESTADO[estado];
  return (
    <Chip tono={e.tono} className={className} icono={<e.Icono aria-hidden="true" className="h-3.5 w-3.5" />}>
      {e.texto}
    </Chip>
  );
}

export function ChipAutor({ autor }: { autor: AutorEstrategia }) {
  return autor === "claude" ? (
    <Chip icono={<Sparkles aria-hidden="true" className="h-3.5 w-3.5" />}>Diseñada con Claude</Chip>
  ) : (
    <Chip icono={<UserRound aria-hidden="true" className="h-3.5 w-3.5" />}>Escrita por ti</Chip>
  );
}

/** "+14,2 %" con color solo si lo que se ve no es cero. */
function Pct({ valor, neutro = false, className }: { valor: number | null | undefined; neutro?: boolean; className?: string }) {
  const texto = fraccion(valor ?? null, 1);
  const s = signoVisible(valor ?? null, texto);
  return <span className={clases(!neutro && s === 1 && "text-sube-texto", !neutro && s === -1 && "text-baja-texto", className)}>{texto}</span>;
}

/** "1 año en Binance, del 17 oct 2025 al 17 oct 2026, con 1.000 USDC". */
export function periodoPrueba(p: ResultadoPrueba): string {
  const dias = (Date.parse(p.hasta) - Date.parse(p.desde)) / 86_400_000;
  const largo = dias >= 360 && dias <= 370 ? "Un año" : dias > 370 ? `${(dias / 365).toLocaleString("es-ES", { maximumFractionDigits: 1 })} años` : `${Math.round(dias)} días`;
  return `${largo} en ${nombreExchange(p.exchange)}, del ${fecha(p.desde)} al ${fecha(p.hasta)}, con ${formatoImporte(p.capital, { decimales: 0 })} USDC`;
}

/**
 * Lo que habria hecho la estrategia sobre el pasado y lo que habria hecho "solo mantener", AL
 * MISMO TAMANO, con la peor caida tan grande como el resultado (docs/panel-v2.md, principio 2:
 * nunca una rentabilidad sin su peor momento ni sin "dejarlo quieto").
 */
export function CifrasPrueba({ p, tamano = "normal" }: { p: ResultadoPrueba; tamano?: "normal" | "grande" }) {
  const grande = tamano === "grande";
  const cifra = clases("cifras mt-0.5 leading-none font-semibold tracking-tight", grande ? "text-[1.75rem] sm:text-[2.5rem]" : "text-[1.5rem]");
  const dif = (p.ganancia_pct - p.mantener_pct) * 100;
  const puntos = Math.abs(dif).toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const difCaida = (p.peor_caida - p.mantener_peor_caida) * 100;
  const puntosCaida = Math.abs(difCaida).toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const veredicto =
    puntos === "0,0" ? "Sobre este pasado, lo mismo que solo mantener" : dif > 0 ? `Sobre este pasado, ${puntos} puntos más que solo mantener` : `Sobre este pasado, ${puntos} puntos menos que solo mantener`;
  const caida =
    puntosCaida === "0,0" ? "y la misma peor caída." : difCaida > 0 ? `y en su peor momento cayó ${puntosCaida} puntos menos.` : `y en su peor momento cayó ${puntosCaida} puntos más.`;
  const columna = (titulo: string, resultado: number, peor: number, pie: string) => (
    <div className={clases("rounded-xl bg-superficie-2 px-3 py-3", grande && "sm:px-5 sm:py-4")}>
      <p className="text-sm font-medium text-tinta">{titulo}</p>
      <dl className="mt-2 grid grid-cols-2 gap-3">
        <div>
          <dt className="text-xs text-tinta-suave">Resultado</dt>
          <dd className={cifra}>
            <Pct valor={resultado} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-tinta-suave">En el peor momento</dt>
          <dd className={clases(cifra, "text-tinta")}>
            <Pct valor={peor} neutro />
          </dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-tinta-suave">{pie}</p>
    </div>
  );
  return (
    <div>
      <div className={clases("grid gap-3", grande ? "md:grid-cols-2 md:gap-4" : "sm:grid-cols-2")}>
        {columna("La estrategia", p.ganancia_pct, p.peor_caida, `Acabó en ${formatoImporte(p.valor_final)} USDC, con comisiones.`)}
        {columna(p.monedas.length > 1 ? "Si solo hubieras mantenido sus monedas" : `Si solo hubieras mantenido ${p.monedas[0] ?? ""}`, p.mantener_pct, p.mantener_peor_caida, "El mismo capital, comprando al principio y sin hacer nada más.")}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-tinta">
        {veredicto}, {caida} <span className="text-tinta-suave">El pasado no es una promesa.</span>
      </p>
    </div>
  );
}

/** Las cifras pequenas de una prueba: operaciones, comisiones, tiempo dentro, velas. */
export function DatosPrueba({ p }: { p: ResultadoPrueba }) {
  return (
    <dl className="cifras grid grid-cols-2 gap-x-4 gap-y-3 rounded-tarjeta border border-linea bg-superficie p-4 text-[0.9375rem] sm:grid-cols-4">
      <div>
        <dt className="text-xs text-tinta-suave">Operaciones</dt>
        <dd className="font-semibold text-tinta">{p.operaciones.toLocaleString("es-ES")}</dd>
      </div>
      <div>
        <dt className="text-xs text-tinta-suave">Comisiones pagadas</dt>
        <dd className="font-semibold text-tinta">{formatoImporte(p.comisiones)} USDC</dd>
      </div>
      <div>
        <dt className="text-xs text-tinta-suave">Tiempo invertido</dt>
        <dd className="font-semibold text-tinta">
          {Math.round(p.tiempo_dentro * 100)} %<span className="font-normal text-tinta-suave"> (el resto, en USDC)</span>
        </dd>
      </div>
      <div>
        <dt className="text-xs text-tinta-suave">Velas</dt>
        <dd className="font-semibold text-tinta">De {nombreIntervalo(p.intervalo)}</dd>
      </div>
    </dl>
  );
}

/** Una linea con la ultima prueba (la biblioteca y el panel de "Disenar con Claude"). */
export function LineaPrueba({ p }: { p: ResultadoPrueba | null }) {
  if (!p) return <p className="text-sm text-tinta-suave">Sin probar todavía sobre el pasado.</p>;
  return (
    <p className="cifras text-sm leading-relaxed text-tinta">
      Sobre el pasado: <Pct valor={p.ganancia_pct} className="font-semibold" />{" "}
      <span className="text-tinta-suave">(solo mantener: {fraccion(p.mantener_pct, 1)})</span> · en el peor momento{" "}
      <span className="font-semibold">{fraccion(p.peor_caida, 1)}</span> <span className="text-tinta-suave">(mantener: {fraccion(p.mantener_peor_caida, 1)})</span>
    </p>
  );
}

/** Los nombres llanos de las herramientas del conector (docs/panel-v4-real.md §2.1). */
const HERRAMIENTAS: Record<string, string> = {
  exchanges: "miró tus exchanges",
  monedas: "miró las monedas",
  velas: "leyó velas",
  esquema: "leyó el formato",
  validar: "la validó",
  probar: "la probó sobre el pasado",
  guardar: "la guardó",
  estrategias: "miró tus estrategias",
  desplegar_ficticio: "la desplegó en ficticio",
  bots: "miró tus bots",
  parar_bot: "paró un bot",
};

export function nombreHerramienta(h: string): string {
  return HERRAMIENTAS[h] ?? h;
}

// -- Conversaciones recordadas (en este navegador) ---------------------------------------------

export interface Conversacion {
  sesion: string;
  titulo: string;
  at: string;
}

const CLAVE_CONVERSACIONES = "invest-ll.disenos";

function leerConversaciones(texto: string): Conversacion[] {
  try {
    const v: unknown = JSON.parse(texto);
    if (!Array.isArray(v)) return [];
    return v.filter(
      (c): c is Conversacion =>
        typeof c === "object" && c !== null && typeof (c as Conversacion).sesion === "string" && typeof (c as Conversacion).titulo === "string" && typeof (c as Conversacion).at === "string",
    );
  } catch {
    return [];
  }
}

/**
 * Las conversaciones de "Disenar con Claude" que se han tenido en ESTE navegador: la API no tiene
 * una ruta que las liste, asi que se recuerdan aqui (solo su id, su primera frase y su fecha).
 */
export function useConversaciones(): [Conversacion[], (c: Conversacion) => void, (sesion: string) => void] {
  const [texto, fijar] = useGuardado("local", CLAVE_CONVERSACIONES, "[]");
  const lista = useMemo(() => leerConversaciones(texto), [texto]);
  const recordar = (c: Conversacion) => {
    const resto = lista.filter((x) => x.sesion !== c.sesion);
    fijar(JSON.stringify([c, ...resto].slice(0, 20)));
  };
  const olvidar = (sesion: string) => fijar(JSON.stringify(lista.filter((x) => x.sesion !== sesion)));
  return [lista, recordar, olvidar];
}

