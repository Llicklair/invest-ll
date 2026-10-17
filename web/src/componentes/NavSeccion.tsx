"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { clases } from "./ui";

export interface PestanaSeccion {
  href: string;
  texto: string;
}

function normalizar(ruta: string): string {
  return ruta.endsWith("/") ? ruta : `${ruta}/`;
}

/**
 * Las pestanas de una seccion que junta varias pantallas (docs/panel-v5.md, seccion 2): Mi plan
 * (Tu plan, Invertir, Cartera), Estrategias (Plantillas, A medida, Laboratorio) y Operar (Operar,
 * Mercados). Son enlaces, no un tablist: cada pestana es su pagina y se puede enlazar. Activa, la
 * de ruta mas larga que encaje (A medida gana a Plantillas en /estrategias/medida/ficha/).
 */
export function NavSeccion({
  etiqueta,
  pestanas,
  extra,
  compacta = false,
}: {
  etiqueta: string;
  pestanas: readonly PestanaSeccion[];
  extra?: ReactNode;
  compacta?: boolean;
}) {
  const ruta = normalizar(usePathname());
  const activa = pestanas
    .filter((p) => ruta.startsWith(p.href))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (
    <nav
      aria-label={etiqueta}
      className={clases("flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-linea", compacta ? "mb-4" : "mb-8")}
    >
      <ul className="-mb-px flex min-w-0 gap-1 overflow-x-auto">
        {pestanas.map((p) => {
          const es = p.href === activa;
          return (
            <li key={p.href} className="shrink-0">
              <Link
                href={p.href}
                aria-current={es ? "page" : undefined}
                className={clases(
                  "inline-flex items-center border-b-2 px-4 text-[0.9375rem]",
                  compacta ? "min-h-10" : "min-h-12",
                  es ? "border-marca font-semibold text-tinta" : "border-transparent text-tinta-suave hover:text-tinta",
                )}
              >
                {p.texto}
              </Link>
            </li>
          );
        })}
      </ul>
      {extra ? <div className="pb-2">{extra}</div> : null}
    </nav>
  );
}

export const PESTANAS_PLAN: readonly PestanaSeccion[] = [
  { href: "/plan/", texto: "Tu plan" },
  { href: "/plan/invertir/", texto: "Invertir" },
  { href: "/plan/cartera/", texto: "Cartera" },
];

export const PESTANAS_ESTRATEGIAS: readonly PestanaSeccion[] = [
  { href: "/estrategias/", texto: "Plantillas" },
  { href: "/estrategias/medida/", texto: "A medida" },
  { href: "/estrategias/laboratorio/", texto: "Laboratorio" },
];

export const PESTANAS_OPERAR: readonly PestanaSeccion[] = [
  { href: "/operar/", texto: "Hyperliquid" },
  { href: "/operar/practica/", texto: "Práctica" },
  { href: "/operar/mercados/", texto: "Mercados" },
];
