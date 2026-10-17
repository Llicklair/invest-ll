import type { Metadata } from "next";
import { Suspense } from "react";

import { Desplegar } from "@/vistas/bots/Desplegar";

export const metadata: Metadata = { title: "Desplegar un bot" };

// ?estrategia=, ?modo= y ?exchange= llegan en la consulta (desde una estrategia a medida o desde
// Ajustes · Conexiones): el panel es un export estatico.
export default function Pagina() {
  return (
    <Suspense>
      <Desplegar />
    </Suspense>
  );
}
