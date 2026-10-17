import type { Metadata } from "next";

import { Ajustes } from "@/vistas/ajustes/Ajustes";

export const metadata: Metadata = { title: "Ajustes" };

export default function Pagina() {
  return <Ajustes />;
}
