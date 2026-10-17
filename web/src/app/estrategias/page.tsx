import type { Metadata } from "next";

import { Estrategias } from "@/vistas/estrategias/Estrategias";

export const metadata: Metadata = { title: "Estrategias" };

export default function Pagina() {
  return <Estrategias />;
}
