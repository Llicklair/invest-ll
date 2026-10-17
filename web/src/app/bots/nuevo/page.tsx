import type { Metadata } from "next";

import { Desplegar } from "@/vistas/bots/Desplegar";

export const metadata: Metadata = { title: "Desplegar un bot" };

export default function Pagina() {
  return <Desplegar />;
}
