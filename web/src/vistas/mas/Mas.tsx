"use client";

import { ChevronRight, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { EN_MAS_MOVIL, MAS } from "@/componentes/Marco";
import { Encabezado } from "@/componentes/ui";

function Lista({ destinos }: { destinos: readonly { ruta: string; texto: string; icono: LucideIcon; bajada: string }[] }) {
  return (
    <ul className="space-y-3">
      {destinos.map((d) => {
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
  );
}

/**
 * Mas: lo que no cabe en la barra inferior del movil (docs/panel-v2.md 4.5 y panel-v3-vivo.md 4).
 * Primero Invertir y Cartera, que en el movil dejan su hueco a Bots y Operar (Inicio lleva a los
 * dos); despues Mercado, Laboratorio y Ajustes.
 */
export function Mas() {
  return (
    <div className="max-w-2xl">
      <Encabezado titulo="Más" />
      <h2 className="mb-3 text-sm font-semibold tracking-wider text-tinta-suave uppercase">Tu dinero</h2>
      <Lista destinos={EN_MAS_MOVIL} />
      <h2 className="mt-8 mb-3 text-sm font-semibold tracking-wider text-tinta-suave uppercase">Para mirar y ajustar</h2>
      <Lista destinos={MAS} />
      <p className="mt-8 text-[0.9375rem] text-tinta-suave">
        ¿Dudas? El botón <strong className="font-semibold text-tinta">Pregunta</strong>, abajo a la derecha, te lo explica con tus
        datos.
      </p>
    </div>
  );
}
