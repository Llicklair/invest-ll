import type { Metadata } from "next";

import { Operar } from "@/vistas/operar/Operar";

export const metadata: Metadata = { title: "Práctica" };

// Operar → Práctica: la cuenta de dinero ficticio, con precios de Hyperliquid (docs/panel-v3-vivo.md).
export default function Pagina() {
  return <Operar modo="practica" />;
}
