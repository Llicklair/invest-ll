import type { Metadata } from "next";

import { Investigacion } from "@/vistas/investigacion/Investigacion";

export const metadata: Metadata = { title: "Investigación" };

export default function Pagina() {
  return <Investigacion />;
}
