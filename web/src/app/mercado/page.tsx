import type { Metadata } from "next";

import { Mercado } from "@/vistas/mercado/Mercado";

export const metadata: Metadata = { title: "Mercado" };

export default function Pagina() {
  return <Mercado />;
}
