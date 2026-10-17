import type { ReactNode } from "react";

import { NavSeccion, PESTANAS_PLAN } from "@/componentes/NavSeccion";
import { PildoraModo } from "@/componentes/PildoraModo";
import { ClaudeCompacto } from "@/vistas/conexiones/ClaudeSuscripcion";

// Mi plan (docs/panel-v5.md, seccion 2): el largo plazo. La pildora del modo es la de su dinero; al
// lado, Claude (con tu suscripción), que es quien explica el plan en Pregunta.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <NavSeccion etiqueta="Mi plan" pestanas={PESTANAS_PLAN} extra={
          <div className="flex flex-wrap items-center gap-2">
            <ClaudeCompacto />
            <PildoraModo />
          </div>
        } />
      {children}
    </>
  );
}
