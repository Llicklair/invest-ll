"use client";

import { useState } from "react";

import { Separador } from "@/componentes/ui";

import { Cotizaciones } from "./Cotizaciones";
import { DatosDescargados } from "./Datos";
import { Panorama } from "./Panorama";

/**
 * ¿Como esta el mundo? Cotizaciones al pulsar, rendimiento con su grafica, comparacion y estado
 * de los datos: una pestana por pregunta.
 */
export function Mercado() {
  const [elegido, setElegido] = useState<string | null>(null);

  const verGrafica = (simbolo: string) => {
    setElegido(simbolo);
    window.requestAnimationFrame(() =>
      document.getElementById("grafica-activo")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-semibold text-tinta">Mercado</h1>
      <Cotizaciones onVerGrafica={verGrafica} />
      <Separador />
      <Panorama elegido={elegido} onElegir={setElegido} />
      <Separador />
      <DatosDescargados />
    </div>
  );
}
