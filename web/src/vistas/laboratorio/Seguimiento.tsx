"use client";

import { api, pedir } from "@/api/cliente";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import { Aviso, Cargando, ErrorApiVista, FilaMetricas, Metrica, Nota } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { fecha } from "@/lib/formato";

/**
 * Lo estimado frente a lo que paso. Es la unica evidencia sobre el LLM que no esta contaminada:
 * un backtest sobre el pasado no vale porque el modelo sabe lo que ocurrio despues.
 */
export function Seguimiento() {
  const consulta = useConsulta("seguimiento", () => pedir(api.GET("/api/seguimiento")));
  const s = consulta.datos;
  return (
    <div className="space-y-5">
      <h2 className="titular text-2xl font-semibold text-tinta">Lo estimado frente a lo que pasó</h2>
      <Nota>
        Un backtest del LLM sobre el pasado no demuestra nada: el modelo fue entrenado con datos posteriores al periodo
        simulado. Esto sí.
      </Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!s && consulta.cargando ? <Cargando /> : null}
      {s && s.evaluadas === 0 && s.pendientes === 0 ? (
        <Aviso tipo="info">
          Todavía no hay ninguna estimación registrada. Es lo normal al principio: hay que emitir una y esperar a que
          venza su horizonte.
        </Aviso>
      ) : null}
      {s && (s.evaluadas > 0 || s.pendientes > 0) ? (
        <div className="space-y-4">
          <FilaMetricas columnas={3}>
            <Metrica etiqueta="Evaluadas" valor={s.evaluadas} />
            <Metrica etiqueta="Pendientes" valor={s.pendientes} detalle="Aún no ha vencido su horizonte" />
            <Metrica etiqueta="Sobreestimaciones" valor={`${s.sobreestimaciones}/${s.evaluadas}`} />
          </FilaMetricas>
          {s.evaluadas > 0 ? (
            <>
              <Aviso tipo="aviso">
                <strong>Veredicto:</strong> el sistema {s.tendencia ?? "— (la API no da la tendencia)"}.
              </Aviso>
              <MarcoTabla etiqueta="Estimaciones evaluadas">
                <thead>
                  <tr>
                    <Th>emitida</Th>
                    <Th numerica>estimado</Th>
                    <Th numerica>real</Th>
                    <Th numerica>error</Th>
                  </tr>
                </thead>
                <tbody>
                  {s.filas.map((f, i) => (
                    <tr key={`${f.emitida}-${i}`}>
                      <Td>{fecha(f.emitida)}</Td>
                      <Td numerica>{formatoImporte(f.estimado)}</Td>
                      <Td numerica>{formatoImporte(f.real)}</Td>
                      <Td numerica>{formatoImporte(f.error, { conSigno: true })}</Td>
                    </tr>
                  ))}
                </tbody>
              </MarcoTabla>
              <Nota>
                Los fallos siguen en la tabla a propósito. Un historial que solo guarda los aciertos no mide nada.
              </Nota>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
