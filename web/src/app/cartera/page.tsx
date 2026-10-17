import type { Metadata } from "next";

import { Cartera } from "@/vistas/cartera/Cartera";

export const metadata: Metadata = { title: "Cartera" };

export default function Pagina() {
  return <Cartera />;
}
