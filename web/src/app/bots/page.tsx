import type { Metadata } from "next";

import { Bots } from "@/vistas/bots/Bots";

export const metadata: Metadata = { title: "Bots" };

export default function Pagina() {
  return <Bots />;
}
