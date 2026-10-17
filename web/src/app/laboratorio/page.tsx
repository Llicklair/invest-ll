import type { Metadata } from "next";

import { Redirigir } from "@/componentes/Redirigir";

export const metadata: Metadata = { title: "Laboratorio" };

// Ruta vieja (docs/panel-v5.md, seccion 2): ahora vive en /estrategias/laboratorio/.
export default function Pagina() {
  return <Redirigir a="/estrategias/laboratorio/" que="El laboratorio" />;
}
