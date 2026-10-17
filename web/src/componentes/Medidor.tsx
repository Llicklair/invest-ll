import { OctagonAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { clases } from "./ui";

export type NivelMedidor = "normal" | "cerca" | "lleno";

/** A partir de que parte del limite se avisa (el 75 %) y cuando se ha llegado. */
export function nivelDe(fraccion: number): NivelMedidor {
  if (fraccion >= 1) return "lleno";
  if (fraccion >= 0.75) return "cerca";
  return "normal";
}

const RELLENO: Record<NivelMedidor, string> = { normal: "bg-marca", cerca: "bg-pruebas", lleno: "bg-real" };
// La pista es un paso mas claro de la MISMA rampa (skill dataviz, "Meter"): el estado se lee en
// toda la barra, no solo en lo relleno.
const PISTA: Record<NivelMedidor, string> = { normal: "bg-marca-suave", cerca: "bg-pruebas-suave", lleno: "bg-real-suave" };

/**
 * Lo consumido de un limite: una barra fina con su cifra en palabras al lado (la barra es
 * redundante: lo que manda es el texto). El color cambia al acercarse (azafran desde el 75 %, rojo
 * al llegar) y entonces lleva icono y palabra: el color nunca va solo.
 */
export function Medidor({
  etiqueta,
  fraccion,
  texto,
  detalle,
  className,
}: {
  etiqueta: string;
  /** Lo consumido, de 0 a 1 (puede pasar de 1). `null` si no se sabe. */
  fraccion: number | null;
  /** La cifra en llano: "250 de 500 USDC". */
  texto: ReactNode;
  /** Lo que pasa al llegar, en una frase. */
  detalle?: ReactNode;
  className?: string;
}) {
  const f = fraccion === null || !Number.isFinite(fraccion) ? null : Math.max(0, fraccion);
  const nivel = f === null ? "normal" : nivelDe(f);
  const ancho = f === null ? 0 : Math.min(1, f) * 100;
  const Icono = nivel === "lleno" ? OctagonAlert : TriangleAlert;
  const palabra = nivel === "lleno" ? "Al límite" : nivel === "cerca" ? "Cerca del límite" : null;
  return (
    <div className={clases("min-w-0", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="text-sm text-tinta-suave">{etiqueta}</span>
        <span className="cifras text-sm font-semibold text-tinta">{texto}</span>
      </div>
      <div
        role="meter"
        aria-label={etiqueta}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={f === null ? undefined : Math.round(Math.min(1, f) * 100)}
        aria-valuetext={typeof texto === "string" ? texto : undefined}
        className={clases("mt-1.5 h-2 w-full overflow-hidden rounded-full", PISTA[nivel])}
      >
        <div className={clases("h-full rounded-full", RELLENO[nivel])} style={{ width: `${ancho}%`, minWidth: ancho > 0 ? 4 : 0 }} />
      </div>
      {palabra || detalle ? (
        <p className="mt-1 flex items-start gap-1.5 text-xs leading-relaxed text-tinta-suave">
          {palabra ? (
            <span className={clases("inline-flex shrink-0 items-center gap-1 font-semibold", nivel === "lleno" ? "text-real-tinta" : "text-pruebas-tinta")}>
              <Icono aria-hidden="true" className="h-3.5 w-3.5" />
              {palabra}.
            </span>
          ) : null}
          {detalle ? <span>{detalle}</span> : null}
        </p>
      ) : null}
    </div>
  );
}
