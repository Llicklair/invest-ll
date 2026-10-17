import type { Metadata } from "next";

import { Operar } from "@/vistas/operar/Operar";

export const metadata: Metadata = { title: "Operar en Hyperliquid" };

// Operar → Hyperliquid (docs/panel-v5.md): para operar de verdad con tu cuenta.
export default function Pagina() {
  return <Operar modo="real" />;
}
