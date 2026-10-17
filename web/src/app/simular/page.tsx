import type { Metadata } from "next";

import { Simular } from "@/vistas/simular/Simular";

export const metadata: Metadata = { title: "Simular" };

export default function Pagina() {
  return <Simular />;
}
