import type { Metadata } from "next";

import { Vigilar } from "@/vistas/vigilar/Vigilar";

export const metadata: Metadata = { title: "Vigilar" };

export default function Pagina() {
  return <Vigilar />;
}
