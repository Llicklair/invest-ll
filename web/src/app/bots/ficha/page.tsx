import type { Metadata } from "next";
import { Suspense } from "react";

import { FichaBot } from "@/vistas/bots/FichaBot";

export const metadata: Metadata = { title: "Ficha del bot" };

// El id va en la consulta (?id=): el panel es un export estatico y no hay una pagina por bot.
export default function Pagina() {
  return (
    <Suspense>
      <FichaBot />
    </Suspense>
  );
}
