"use client";

import { Check } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { clases } from "./ui";

/**
 * Pasos con su progreso a la vista ("Paso 2 de 3 · Te proponemos"). Los pasos ya hechos se
 * pueden volver a abrir; los siguientes, no hasta llegar. Al cambiar de paso, el foco va a su
 * titulo: con teclado o lector de pantalla se sabe donde se esta.
 */
export function Asistente({
  pasos,
  actual,
  alcanzado,
  onIr,
  children,
  etiqueta,
}: {
  pasos: readonly string[];
  /** Indice del paso que se ve (0..n-1). */
  actual: number;
  /** Hasta que paso se ha llegado (los anteriores se pueden reabrir). */
  alcanzado: number;
  onIr: (paso: number) => void;
  children: ReactNode;
  etiqueta: string;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  const primero = useRef(true);

  useEffect(() => {
    if (primero.current) {
      primero.current = false;
      return;
    }
    titulo.current?.focus();
  }, [actual]);

  return (
    <div>
      <nav aria-label={etiqueta} className="mb-8">
        <ol className="flex gap-2">
          {pasos.map((p, i) => {
            const hecho = i < actual;
            const es = i === actual;
            const abrible = i <= alcanzado && !es;
            const contenido = (
              <>
                <span
                  className={clases(
                    "block h-1.5 w-full rounded-full",
                    hecho || es ? "bg-marca" : i <= alcanzado ? "bg-marca/40" : "bg-linea",
                  )}
                  aria-hidden="true"
                />
                <span
                  className={clases(
                    "mt-2 flex items-center gap-1.5 text-sm",
                    es ? "font-semibold text-tinta" : "text-tinta-suave",
                  )}
                >
                  {hecho ? <Check aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2.5} /> : null}
                  <span className="hidden sm:inline">{i + 1}. </span>
                  <span className={es ? undefined : "hidden sm:inline"}>{p}</span>
                </span>
              </>
            );
            return (
              <li key={p} className="min-w-0 flex-1">
                {abrible ? (
                  <button
                    type="button"
                    onClick={() => onIr(i)}
                    className="block min-h-11 w-full text-left hover:opacity-80"
                    aria-label={`Volver al paso ${i + 1}: ${p}`}
                  >
                    {contenido}
                  </button>
                ) : (
                  <div className="min-h-11" aria-current={es ? "step" : undefined}>
                    {contenido}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        <h2 ref={titulo} tabIndex={-1} className="sr-only">
          Paso {actual + 1} de {pasos.length}: {pasos[actual]}
        </h2>
      </nav>
      {children}
    </div>
  );
}
