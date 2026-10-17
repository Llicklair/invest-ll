"use client";

import { Encabezado } from "@/componentes/ui";
import { Conexiones } from "@/vistas/ajustes/Conexiones";

import { ClaudeSuscripcion } from "./ClaudeSuscripcion";

/**
 * Conexiones (docs/panel-v5.md, seccion 2): Claude con tu suscripción, tus exchanges (cada uno con
 * su camino de la red de pruebas al dinero real) y el conector con Claude. Antes vivia dentro de Ajustes.
 */
export function PaginaConexiones() {
  return (
    <div>
      <Encabezado
        titulo="Conexiones"
        bajada="Claude con tu suscripción, tus exchanges y el conector con Claude. Cada exchange pasa por tres pasos, de la red de pruebas al dinero real, sin saltarse ninguno. Las claves nunca salen de este ordenador."
      />
      <div className="space-y-10">
        <ClaudeSuscripcion />
        <Conexiones />
      </div>
    </div>
  );
}
