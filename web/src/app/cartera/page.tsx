import type { Metadata } from "next";

import { Redirigir } from "@/componentes/Redirigir";

export const metadata: Metadata = { title: "Cartera" };

// Ruta vieja (docs/panel-v5.md, seccion 2): ahora vive en /plan/cartera/.
export default function Pagina() {
  return <Redirigir a="/plan/cartera/" que="La cartera" />;
}
