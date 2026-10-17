import type { Metadata } from "next";
import { Suspense } from "react";

import { FichaEstrategia } from "@/vistas/medida/FichaEstrategia";

export const metadata: Metadata = { title: "Ficha de la estrategia" };

// El id va en la consulta (?id=): el panel es un export estatico y no hay una pagina por estrategia.
export default function Pagina() {
  return (
    <Suspense>
      <FichaEstrategia />
    </Suspense>
  );
}
