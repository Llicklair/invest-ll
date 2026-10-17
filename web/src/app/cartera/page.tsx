import type { Metadata } from "next";

import { Cartera } from "@/vistas/cartera/Cartera";

export const metadata: Metadata = { title: "Mi cartera" };

export default function Pagina() {
  return <Cartera />;
}
