import type { Metadata } from "next";

import { Chat } from "@/vistas/chat/Chat";

export const metadata: Metadata = { title: "Chat" };

export default function Pagina() {
  return <Chat />;
}
