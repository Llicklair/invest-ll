"use client";

import { useId, type ReactNode } from "react";

import { formatoImporte } from "@/lib/decimal";
import { leerImporte } from "@/lib/importe";

import { clases } from "./ui";

/**
 * Un importe en euros: teclado numerico en el movil, "€" a la vista, y atajos para no tener que
 * teclear ("1.000 €", "5.000 €"...). Acepta "1.000", "1000" o "12,50" (lib/importe.ts).
 */
export function CampoImporte({
  etiqueta,
  ayuda,
  valor,
  onCambio,
  error,
  atajos,
  grande = false,
  className,
  id: idPropio,
}: {
  etiqueta: ReactNode;
  ayuda?: ReactNode;
  valor: string;
  onCambio: (v: string) => void;
  error?: string | null;
  atajos?: readonly string[];
  grande?: boolean;
  className?: string;
  id?: string;
}) {
  const idAuto = useId();
  const id = idPropio ?? idAuto;
  const idAyuda = `${id}-ayuda`;
  const idError = `${id}-error`;
  const describe = [ayuda ? idAyuda : null, error ? idError : null].filter(Boolean).join(" ") || undefined;
  const actual = leerImporte(valor);
  return (
    <div className={clases("flex flex-col gap-2", className)}>
      <label htmlFor={id} className={clases("font-medium text-tinta", grande ? "titular text-xl leading-snug" : "text-[0.9375rem]")}>
        {etiqueta}
      </label>
      {ayuda ? (
        <p id={idAyuda} className="text-[0.9375rem] text-tinta-suave">
          {ayuda}
        </p>
      ) : null}
      <div className="relative max-w-xs">
        <input
          id={id}
          value={valor}
          onChange={(e) => onCambio(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={describe}
          placeholder="0"
          className={clases(
            "cifras w-full rounded-xl border bg-superficie pr-12 pl-4 text-tinta placeholder:text-tinta-suave/50 hover:border-linea-control aria-[invalid=true]:border-real",
            grande ? "min-h-14 text-2xl" : "min-h-12 text-lg",
            "border-linea-control/70",
          )}
        />
        <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-lg text-tinta-suave" aria-hidden="true">
          €
        </span>
      </div>
      {atajos?.length ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Cantidades rápidas">
          {atajos.map((a) => {
            const elegido = actual !== null && actual === a;
            return (
              <button
                key={a}
                type="button"
                onClick={() => onCambio(formatoImporte(a, { decimales: 0 }))}
                aria-pressed={elegido}
                className={clases(
                  "cifras min-h-11 rounded-full border px-4 text-[0.9375rem]",
                  elegido ? "border-marca bg-marca-suave font-semibold text-marca" : "border-linea text-tinta hover:bg-superficie-2",
                )}
              >
                {formatoImporte(a, { decimales: 0 })} €
              </button>
            );
          })}
        </div>
      ) : null}
      {error ? (
        <p id={idError} className="text-sm font-medium text-real-tinta">
          {error}
        </p>
      ) : null}
    </div>
  );
}
