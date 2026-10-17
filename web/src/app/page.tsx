import type { Metadata } from "next";

import { Resumen } from "@/vistas/resumen/Resumen";

export const metadata: Metadata = { title: "Resumen" };

export default function Pagina() {
  return <Resumen />;
}
