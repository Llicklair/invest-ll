import type { Metadata } from "next";
import { Suspense } from "react";

import { Desplegar } from "@/vistas/bots/Desplegar";

export const metadata: Metadata = { title: "Desplegar un bot" };

// ?plantilla=, ?estrategia=, ?modo= y ?exchange= llegan en la consulta (desde Estrategias o desde
// Conexiones): el panel es un export estatico.
export default function Pagina() {
  return (
    <Suspense>
      <Desplegar />
    </Suspense>
  );
}
