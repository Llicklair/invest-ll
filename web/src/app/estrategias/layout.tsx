import type { ReactNode } from "react";

import { NavSeccion, PESTANAS_ESTRATEGIAS } from "@/componentes/NavSeccion";

// Estrategias (docs/panel-v5.md, seccion 2): las reglas que siguen los bots.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <NavSeccion etiqueta="Estrategias" pestanas={PESTANAS_ESTRATEGIAS} />
      {children}
    </>
  );
}
