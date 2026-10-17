import type { Metadata } from "next";

import { Plantillas } from "@/vistas/estrategias/Plantillas";

export const metadata: Metadata = { title: "Estrategias" };

export default function Pagina() {
  return <Plantillas />;
}
