import type { Metadata } from "next";
import { Suspense } from "react";

import { Disenar } from "@/vistas/medida/Disenar";

export const metadata: Metadata = { title: "Diseñar con Claude" };

// La conversacion va en la consulta (?sesion=): el panel es un export estatico.
export default function Pagina() {
  return (
    <Suspense>
      <Disenar />
    </Suspense>
  );
}
