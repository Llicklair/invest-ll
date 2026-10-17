import type { Metadata } from "next";

import { Redirigir } from "@/componentes/Redirigir";

export const metadata: Metadata = { title: "Mercados" };

// Ruta vieja (docs/panel-v5.md, seccion 2): ahora vive en /operar/mercados/.
export default function Pagina() {
  return <Redirigir a="/operar/mercados/" que="El mercado" />;
}
