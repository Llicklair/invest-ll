"use client";

import { api, pedir } from "@/api/cliente";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import { Aviso, Boton, Cargando, ErrorApiVista, Nota, Seccion, TextoApi } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";

import { AvisoCostes, useFriccion } from "./comun";

/**
 * Reproduce el experimento real del LLM sin gastar cuota: decisiones grabadas. Generar decisiones
 * nuevas gasta cuota y sigue en invest-ll-generate.
 */
export function Llm() {
  const friccion = useFriccion();
  const comparar = useAccion(() => {
    if (!friccion) throw new Error("costes no válidos");
    return pedir(api.POST("/api/simular/llm", { body: friccion }));
  });
  const r = comparar.resultado;

  return (
    <Seccion titulo="El LLM decide (decisiones grabadas)" id="llm">
      <Nota>
        84 decisiones reales de claude-opus-4-6 sobre 21 años (GLD/TLT/XLE/XLF), grabadas en decisions/llm-trimestral.
        Compararlas no consulta a nadie ni gasta nada.
      </Nota>
      <AvisoCostes />
      <Boton variante="primario" onClick={() => void comparar.ejecutar()} disabled={comparar.enCurso || !friccion}>
        Comparar LLM vs momentum vs no hacer nada
      </Boton>
      {comparar.enCurso ? <Cargando texto="Reproduciendo 21 años de decisiones…" /> : null}
      {comparar.error ? <ErrorApiVista error={comparar.error} prefijo="No se pudo reproducir:" /> : null}
      {r && !r.disponible ? (
        <Aviso tipo="info">
          <TextoApi texto={r.motivo ?? "El experimento no se puede reproducir con lo que hay."} />
        </Aviso>
      ) : null}
      {r && r.disponible ? (
        <div className="space-y-3">
          <MarcoTabla etiqueta="LLM frente a momentum y a no hacer nada">
            <thead>
              <tr>
                <Th>estrategia</Th>
                <Th numerica>resultado</Th>
                <Th numerica>drawdown</Th>
                <Th numerica>operaciones</Th>
                <Th numerica>costes</Th>
              </tr>
            </thead>
            <tbody>
              {r.filas.map((f) => (
                <tr key={f.estrategia}>
                  <Td className="font-medium">{f.estrategia}</Td>
                  <Td numerica>{formatoImporte(f.resultado, { decimales: 0, conSigno: true })}</Td>
                  <Td numerica>{formatoImporte(f.drawdown, { decimales: 0 })}</Td>
                  <Td numerica>{f.operaciones.toLocaleString("es-ES")}</Td>
                  <Td numerica>{formatoImporte(f.costes, { decimales: 0 })}</Td>
                </tr>
              ))}
            </tbody>
          </MarcoTabla>
          {r.ninguna_bate ? (
            <Aviso tipo="critico">
              <strong>Ninguna bate a comprar y mantener.</strong> Todo el riesgo asumido y las comisiones pagadas quedaron
              por debajo de no hacer nada.
            </Aviso>
          ) : null}
        </div>
      ) : null}
      {r ? (
        <Aviso tipo="aviso">
          <span className="block font-mono text-[0.8rem] whitespace-pre-wrap">{r.advertencia.trimEnd()}</span>
        </Aviso>
      ) : null}
    </Seccion>
  );
}
