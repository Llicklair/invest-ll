import type { ReactNode } from "react";

import { NavSeccion, PESTANAS_PLAN } from "@/componentes/NavSeccion";
import { PildoraModo } from "@/componentes/PildoraModo";

// Mi plan (docs/panel-v5.md, seccion 2): el largo plazo. La pildora del modo es la de su dinero.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <NavSeccion etiqueta="Mi plan" pestanas={PESTANAS_PLAN} extra={<PildoraModo />} />
      {children}
    </>
  );
}
