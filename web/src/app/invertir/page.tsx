import type { Metadata } from "next";

import { Redirigir } from "@/componentes/Redirigir";

export const metadata: Metadata = { title: "Invertir" };

// Ruta vieja (docs/panel-v5.md, seccion 2): ahora vive en /plan/invertir/.
export default function Pagina() {
  return <Redirigir a="/plan/invertir/" que="Invertir" />;
}
