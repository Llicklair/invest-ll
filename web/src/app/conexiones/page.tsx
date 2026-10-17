import type { Metadata } from "next";

import { PaginaConexiones } from "@/vistas/conexiones/PaginaConexiones";

export const metadata: Metadata = { title: "Conexiones" };

export default function Pagina() {
  return <PaginaConexiones />;
}
