"use client";

import { useState } from "react";

import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import { Codigo, Nota, Segmentado, Separador } from "@/componentes/ui";

import { CostesSimulacion } from "../Costes";

import { Aportaciones } from "./Aportaciones";
import { Llm } from "./Llm";
import { Propuesta } from "./Propuesta";
import { UnActivo } from "./UnActivo";

const VIAS = [
  { valor: "propuesta", texto: "Propuesta simple" },
  { valor: "aportaciones", texto: "Aportaciones periódicas a una cartera" },
  { valor: "activo", texto: "Una estrategia sobre un activo" },
  { valor: "llm", texto: "El LLM decide (grabado)" },
] as const;
type Via = (typeof VIAS)[number]["valor"];

/** ¿Que pasaria si...? Todo lo que es ensayo vive junto, y nada de esto mueve dinero. */
export function Probar() {
  const [via, setVia] = useState<Via>("propuesta");
  return (
    <div className="space-y-5">
      <CostesSimulacion />
      <Nota>
        Propuestas y backtests sobre datos históricos, con los costes de arriba. Nada de esto envía órdenes: la única
        puerta al dinero real es invest-ll-execute (o Invertir → Avanzado), con su confirmación.
      </Nota>
      <Segmentado etiqueta="Qué quieres ensayar" opciones={VIAS} valor={via} onCambio={setVia} />
      <Separador />
      {via === "propuesta" ? <Propuesta /> : null}
      {via === "aportaciones" ? <Aportaciones /> : null}
      {via === "activo" ? <UnActivo /> : null}
      {via === "llm" ? <Llm /> : null}

      <Separador />
      <section className="space-y-3" aria-labelledby="cuatro-vias">
        <h2 id="cuatro-vias" className="text-lg font-semibold">
          Las cuatro vías de invertir
        </h2>
        <MarcoTabla etiqueta="Las cuatro vías de invertir">
          <thead>
            <tr>
              <Th>Vía</Th>
              <Th>Dónde, en este panel</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td className="font-semibold">Botón simple</Td>
              <Td className="whitespace-normal">
                Propuesta simple: simula y <strong>registra en Cartera con un botón</strong>
              </Td>
            </tr>
            <tr>
              <Td className="font-semibold">Bot determinista</Td>
              <Td className="whitespace-normal">Rotación momentum: Aportaciones / Un activo, aquí arriba</Td>
            </tr>
            <tr>
              <Td className="font-semibold">LLM</Td>
              <Td className="whitespace-normal">
                «El LLM decide (grabado)»: reproduce el experimento real sin gastar cuota, y el botón Pregunta para
                preguntarle
              </Td>
            </tr>
            <tr>
              <Td className="font-semibold">LLM desde fuera</Td>
              <Td className="whitespace-normal">
                Un agente externo maneja los diez comandos con <Codigo>--json</Codigo>; las advertencias viajan dentro del
                JSON
              </Td>
            </tr>
          </tbody>
        </MarcoTabla>
        <Nota>
          Lo único que no vive en el Laboratorio es el dinero real: eso es invest-ll-execute, con su confirmación. Lo medido
          hasta hoy (21 años, 4 activos): cuanto menos se opera, mejor — 423 operaciones dieron 2.890; una sola dio
          37.773. Ver docs/experimento-llm-2026-07.md.
        </Nota>
      </section>
    </div>
  );
}
