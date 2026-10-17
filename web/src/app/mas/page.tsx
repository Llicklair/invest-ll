import type { Metadata } from "next";

import { Mas } from "@/vistas/mas/Mas";

export const metadata: Metadata = { title: "Más" };

export default function Pagina() {
  return <Mas />;
}
