import type { Metadata } from "next";

import { Seguimiento } from "@/vistas/seguimiento/Seguimiento";

export const metadata: Metadata = { title: "Estimado vs real" };

export default function Pagina() {
  return <Seguimiento />;
}
