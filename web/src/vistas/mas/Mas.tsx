"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { MAS } from "@/componentes/Marco";
import { Encabezado } from "@/componentes/ui";

/** Mas: lo que no es el camino principal (docs/panel-v2.md, 4.5). En el movil es la quinta pestana. */
export function Mas() {
  return (
    <div className="max-w-2xl">
      <Encabezado titulo="Más" />
      <ul className="space-y-3">
        {MAS.map((d) => {
          const Icono = d.icono;
          return (
            <li key={d.ruta}>
              <Link
                href={d.ruta}
                className="flex min-h-20 items-center gap-4 rounded-tarjeta border border-linea bg-superficie px-5 py-4 shadow-suave hover:bg-superficie-2"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-marca-suave text-marca" aria-hidden="true">
                  <Icono className="h-5 w-5" strokeWidth={1.75} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-lg font-semibold text-tinta">{d.texto}</span>
                  <span className="block text-[0.9375rem] text-tinta-suave">{d.bajada}</span>
                </span>
                <ChevronRight aria-hidden="true" className="h-5 w-5 shrink-0 text-tinta-suave" />
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-8 text-[0.9375rem] text-tinta-suave">
        ¿Dudas? El botón <strong className="font-semibold text-tinta">Pregunta</strong>, abajo a la derecha, te lo explica con tus
        datos.
      </p>
    </div>
  );
}
