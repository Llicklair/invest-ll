import type { Metadata } from "next";

import { Laboratorio } from "@/vistas/laboratorio/Laboratorio";

export const metadata: Metadata = { title: "Laboratorio" };

export default function Pagina() {
  return <Laboratorio />;
}
