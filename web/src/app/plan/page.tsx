import type { Metadata } from "next";

import { Estrategias } from "@/vistas/estrategias/Estrategias";

export const metadata: Metadata = { title: "Mi plan" };

export default function Pagina() {
  return <Estrategias />;
}
