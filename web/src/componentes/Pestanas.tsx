"use client";

import { useRef, type KeyboardEvent } from "react";

import { clases } from "./ui";

/**
 * Pestanas accesibles (patron tablist del WAI-ARIA): Tab entra en la pestana activa, las flechas
 * cambian de una a otra, Inicio/Fin van a la primera/ultima. En movil se desplazan de lado.
 */
export function Pestanas<C extends string>({
  etiqueta,
  pestanas,
  actual,
  onCambio,
  idPanel,
}: {
  etiqueta: string;
  pestanas: readonly { clave: C; texto: string }[];
  actual: C;
  onCambio: (c: C) => void;
  idPanel: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const indice = Math.max(0, pestanas.findIndex((p) => p.clave === actual));

  const teclas = (e: KeyboardEvent<HTMLDivElement>) => {
    let siguiente: number | null = null;
    if (e.key === "ArrowRight") siguiente = (indice + 1) % pestanas.length;
    if (e.key === "ArrowLeft") siguiente = (indice - 1 + pestanas.length) % pestanas.length;
    if (e.key === "Home") siguiente = 0;
    if (e.key === "End") siguiente = pestanas.length - 1;
    if (siguiente === null) return;
    e.preventDefault();
    const p = pestanas[siguiente];
    if (p) {
      onCambio(p.clave);
      refs.current[siguiente]?.focus();
    }
  };

  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
      <div role="tablist" aria-label={etiqueta} onKeyDown={teclas} className="flex min-w-max gap-1 border-b border-linea">
        {pestanas.map((p, i) => {
          const activa = p.clave === actual;
          return (
            <button
              key={p.clave}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`pestana-${p.clave}`}
              aria-selected={activa}
              aria-controls={idPanel}
              tabIndex={activa ? 0 : -1}
              onClick={() => onCambio(p.clave)}
              className={clases(
                "-mb-px min-h-12 border-b-2 px-4 text-[0.9375rem] whitespace-nowrap",
                activa ? "border-marca font-semibold text-tinta" : "border-transparent text-tinta-suave hover:text-tinta",
              )}
            >
              {p.texto}
            </button>
          );
        })}
      </div>
    </div>
  );
}
