import type { Metadata } from "next";

import { Invertir } from "@/vistas/invertir/Invertir";

export const metadata: Metadata = { title: "Invertir" };

export default function Pagina() {
  return <Invertir />;
}
