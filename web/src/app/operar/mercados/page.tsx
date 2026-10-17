import type { Metadata } from "next";

import { Mercado } from "@/vistas/mercado/Mercado";

export const metadata: Metadata = { title: "Mercados" };

export default function Pagina() {
  return <Mercado />;
}
