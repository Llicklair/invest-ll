import type { Metadata, Viewport } from "next";
import { Fraunces, Inter } from "next/font/google";
import type { ReactNode } from "react";

import { Marco } from "@/componentes/Marco";
import { ProveedorCostes } from "@/contexto/costes";
import { ProveedorEstado } from "@/contexto/estado";
import { ProveedorModo } from "@/contexto/modo";

import "./globals.css";

// Las dos familias se descargan al compilar y viajan dentro de `out/`: el panel no pide nada a
// Google al abrirse (y funciona sin internet).
const fraunces = Fraunces({
  subsets: ["latin"],
  axes: ["SOFT", "WONK", "opsz"],
  variable: "--fuente-fraunces",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--fuente-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "INVEST LL", template: "%s · INVEST LL" },
  description: "Qué hacer con tu dinero, explicado sin jerga. Un sistema que no puede mentirte sobre sus propios resultados.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f3ee" },
    { media: "(prefers-color-scheme: dark)", color: "#121311" },
  ],
};

// Aplica el tema guardado antes de pintar, para que no parpadee al cargar.
const TEMA_ANTES_DE_PINTAR = `try{var t=localStorage.getItem("invest-ll.tema");if(t==="claro")document.documentElement.dataset.theme="light";else if(t==="oscuro")document.documentElement.dataset.theme="dark";}catch(e){}`;

export default function Raiz({ children }: { children: ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning className={`${fraunces.variable} ${inter.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: TEMA_ANTES_DE_PINTAR }} />
      </head>
      <body className="min-h-screen">
        <ProveedorEstado>
          <ProveedorModo>
            <ProveedorCostes>
              <Marco>{children}</Marco>
            </ProveedorCostes>
          </ProveedorModo>
        </ProveedorEstado>
      </body>
    </html>
  );
}
