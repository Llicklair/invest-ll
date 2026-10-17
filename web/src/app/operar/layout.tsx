import type { ReactNode } from "react";

import { NavSeccion, PESTANAS_OPERAR } from "@/componentes/NavSeccion";

// Operar (docs/panel-v5.md, seccion 2): la pantalla de exchange y los mercados.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <NavSeccion etiqueta="Operar" pestanas={PESTANAS_OPERAR} compacta />
      {children}
    </>
  );
}
