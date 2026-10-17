import type { Metadata } from "next";

import { Biblioteca } from "@/vistas/medida/Biblioteca";

export const metadata: Metadata = { title: "Estrategias a medida" };

export default function Pagina() {
  return <Biblioteca />;
}
