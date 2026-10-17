"use client";

import { useEffect, type ReactNode } from "react";

/**
 * La accion principal de un paso largo, fija abajo (encima de la barra inferior en el movil).
 * Mientras esta en pantalla, el boton de Pregunta sube para no taparla (globals.css).
 */
export function BarraAccion({ children }: { children: ReactNode }) {
  useEffect(() => {
    document.body.dataset.barraAccion = "1";
    return () => {
      delete document.body.dataset.barraAccion;
    };
  }, []);
  return (
    <div className="fixed inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] z-10 border-t border-linea bg-superficie/95 backdrop-blur-md lg:bottom-0 lg:left-64">
      <div className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-12">
        {children}
      </div>
    </div>
  );
}
