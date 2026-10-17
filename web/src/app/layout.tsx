import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Cabecera } from "@/componentes/Cabecera";
import { ProveedorCostes } from "@/contexto/costes";
import { ProveedorEstado } from "@/contexto/estado";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "INVEST LL", template: "%s · INVEST LL" },
  description: "El panel de INVEST LL: no puede mentirte sobre sus propios resultados.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

// Aplica el tema guardado antes de pintar, para que no parpadee al cargar.
const TEMA_ANTES_DE_PINTAR = `try{var t=localStorage.getItem("invest-ll.tema");if(t==="claro")document.documentElement.dataset.theme="light";else if(t==="oscuro")document.documentElement.dataset.theme="dark";}catch(e){}`;

export default function Raiz({ children }: { children: ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: TEMA_ANTES_DE_PINTAR }} />
      </head>
      <body className="min-h-screen">
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-superficie focus:px-3 focus:py-2"
        >
          Saltar al contenido
        </a>
        <ProveedorEstado>
          <ProveedorCostes>
            <Cabecera />
            <main id="contenido" className="mx-auto max-w-7xl px-4 pt-6 pb-16">
              {children}
            </main>
            <footer className="mx-auto max-w-7xl border-t border-borde px-4 py-4 text-xs text-tinta-2">
              INVEST LL · un sistema que no puede mentirte sobre sus propios resultados. Las cifras de
              mercado llevan siempre su fecha; las valoraciones no son hechos.
            </footer>
          </ProveedorCostes>
        </ProveedorEstado>
      </body>
    </html>
  );
}
