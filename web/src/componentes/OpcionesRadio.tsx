"use client";

import { useId, type ReactNode } from "react";

import { clases } from "./ui";

/**
 * Una pregunta con respuestas en tarjeta (radios nativos: las flechas del teclado cambian de
 * opcion y el lector de pantalla anuncia "1 de 4"). Objetivos de 56 px de alto.
 */
export function OpcionesRadio<V extends string>({
  pregunta,
  ayuda,
  opciones,
  valor,
  onCambio,
  error,
  columnas = 1,
}: {
  pregunta: ReactNode;
  ayuda?: ReactNode;
  opciones: readonly { valor: V; texto: string; detalle?: string }[];
  valor: V | undefined;
  onCambio: (v: V) => void;
  error?: string | null;
  columnas?: 1 | 2 | 3;
}) {
  const nombre = useId();
  const idError = `${nombre}-error`;
  return (
    <fieldset className="min-w-0" aria-describedby={error ? idError : undefined} aria-invalid={error ? true : undefined}>
      <legend className="titular text-xl leading-snug font-medium text-tinta">{pregunta}</legend>
      {ayuda ? <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">{ayuda}</p> : null}
      <div className={clases("mt-4 grid gap-2", columnas === 2 && "sm:grid-cols-2", columnas === 3 && "lg:grid-cols-3")}>
        {opciones.map((o) => {
          const elegida = o.valor === valor;
          return (
            <label
              key={o.valor}
              className={clases(
                "flex min-h-14 cursor-pointer items-center gap-3.5 rounded-xl border px-4 py-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco",
                elegida ? "border-marca bg-marca-suave" : "border-linea bg-superficie hover:border-linea-control/60 hover:bg-superficie-2",
              )}
            >
              <input
                type="radio"
                name={nombre}
                value={o.valor}
                checked={elegida}
                onChange={() => onCambio(o.valor)}
                className="peer sr-only"
              />
              <span
                aria-hidden="true"
                className={clases(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2",
                  elegida ? "border-marca" : "border-linea-control",
                )}
              >
                {elegida ? <span className="h-2.5 w-2.5 rounded-full bg-marca" /> : null}
              </span>
              <span className="min-w-0">
                <span className={clases("block text-[0.9375rem] text-tinta", elegida && "font-semibold")}>{o.texto}</span>
                {o.detalle ? <span className="mt-0.5 block text-sm text-tinta-suave">{o.detalle}</span> : null}
              </span>
            </label>
          );
        })}
      </div>
      {error ? (
        <p id={idError} className="mt-2 text-sm font-medium text-real-tinta">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
