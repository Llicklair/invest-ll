import type { Metadata } from "next";

import { Operar } from "@/vistas/operar/Operar";

export const metadata: Metadata = { title: "Operar" };

export default function Pagina() {
  return <Operar />;
}
