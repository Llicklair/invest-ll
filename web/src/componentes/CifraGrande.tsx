import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";

import { formatoImporte, signoDecimal } from "@/lib/decimal";
import { euros, fraccion, menos, SIN_DATO } from "@/lib/formato";

import { clases } from "./ui";

/**
 * La cifra que manda en una pantalla (valor + variacion + fecha). Fraunces, grande y con el "€"
 * mas pequeno para que el numero se lea primero. Una por vista.
 *
 * Las cifras grandes van con figuras proporcionales (la skill dataviz: las tabulares dejan un
 * "121" desgarbado a este tamano); las tabulares, en lo que se alinea en columna.
 */
export function CifraGrande({
  etiqueta,
  valor,
  variacion,
  pie,
  marca,
  tamano = "grande",
}: {
  etiqueta: ReactNode;
  /** Importe exacto (Decimal en cadena); `null` = no se puede calcular. */
  valor: string | null;
  variacion?: ReactNode;
  /** La fecha de los datos y lo que haga falta saber para leer la cifra. */
  pie?: ReactNode;
  /** Una etiqueta junto a la cifra ("dinero ficticio"). */
  marca?: ReactNode;
  tamano?: "grande" | "media";
}) {
  const texto = valor === null ? null : menos(formatoImporte(valor, { decimales: 2 }));
  const [entera, decimales] = texto ? texto.split(",") : [null, null];
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[0.9375rem] font-medium text-tinta-suave">{etiqueta}</p>
        {marca}
      </div>
      <p
        className={clases(
          "titular mt-1 leading-none font-medium tracking-tight text-tinta",
          tamano === "grande" ? "text-[2.75rem] sm:text-[3.5rem]" : "text-[2.25rem]",
        )}
      >
        {entera === null ? (
          <span className="text-[0.55em] text-tinta-suave">No se puede sumar</span>
        ) : (
          <>
            {entera}
            <span className="text-[0.55em] text-tinta-suave">
              ,{decimales}
              {" "}€
            </span>
          </>
        )}
      </p>
      {variacion ? <div className="mt-3">{variacion}</div> : null}
      {pie ? <div className="mt-2 text-sm text-tinta-suave">{pie}</div> : null}
    </div>
  );
}

/**
 * Lo que se gana o se pierde: siempre con signo, flecha y PALABRA, ademas del color (el color
 * nunca va solo). `importe` es exacto (Decimal); `pct` es una fraccion que solo se pinta.
 */
export function Variacion({
  importe,
  pct,
  coletilla,
  className,
}: {
  importe: string | null;
  pct?: number | null;
  /** "si vendieras hoy", "este mes"... */
  coletilla?: ReactNode;
  className?: string;
}) {
  const s = importe === null ? null : signoDecimal(importe);
  if (importe === null || s === null) {
    return <p className={clases("text-[0.9375rem] text-tinta-suave", className)}>Sin datos para saber cuánto ganas o pierdes.</p>;
  }
  const Icono = s > 0 ? ArrowUpRight : s < 0 ? ArrowDownRight : Minus;
  const palabra = s > 0 ? "Ganas" : s < 0 ? "Pierdes" : "Ni ganas ni pierdes";
  const color = s > 0 ? "text-sube-texto" : s < 0 ? "text-baja-texto" : "text-tinta-suave";
  const fondo = s > 0 ? "bg-sube-suave" : s < 0 ? "bg-baja-suave" : "bg-superficie-2";
  return (
    <p className={clases("flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9375rem]", className)}>
      <span className={clases("inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold", fondo, color)}>
        <Icono aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
        {palabra}
        {s !== 0 ? (
          <span className="cifras">
            {" "}
            {euros(importe, { conSigno: true })}
            {pct !== undefined && pct !== null ? ` (${fraccion(pct, 1)})` : ""}
          </span>
        ) : null}
      </span>
      {coletilla ? <span className="text-tinta-suave">{coletilla}</span> : null}
    </p>
  );
}

/** Una variacion de mercado en %, en linea ("Bitcoin sube un 2,1 % en un mes"). */
export function CambioPct({ pct, className, neutro = false }: { pct: number | null; className?: string; neutro?: boolean }) {
  if (pct === null || !Number.isFinite(pct)) return <span className={clases("text-tinta-suave", className)}>{SIN_DATO}</span>;
  const s = pct > 0 ? 1 : pct < 0 ? -1 : 0;
  const Icono = s > 0 ? ArrowUpRight : s < 0 ? ArrowDownRight : Minus;
  return (
    <span
      className={clases(
        "cifras inline-flex items-center gap-0.5 font-semibold",
        neutro ? "text-tinta" : s > 0 ? "text-sube-texto" : s < 0 ? "text-baja-texto" : "text-tinta-suave",
        className,
      )}
    >
      <Icono aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
      <span className="sr-only">{s > 0 ? "sube" : s < 0 ? "baja" : "igual"}</span>
      {menos(`${pct > 0 ? "+" : ""}${pct.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`)}
      {" "}%
    </span>
  );
}
