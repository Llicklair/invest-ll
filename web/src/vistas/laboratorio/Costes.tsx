"use client";

import { useCostes } from "@/contexto/costes";
import { fraccionComoPorcentaje } from "@/lib/decimal";

import { ESTILO_ENTRADA, Tarjeta, clases } from "@/componentes/ui";

/**
 * Los costes de toda simulacion del Laboratorio (comision y deslizamiento). Antes vivian en la
 * cabecera de todas las pantallas; en la v2 son cosa de quien prueba estrategias, asi que viven
 * aqui (docs/panel-v2.md, 4.5). Son obligatorios: una simulacion sin friccion es una mentira
 * optimista.
 */
export function CostesSimulacion() {
  const { comision, slippage, motivo, fijarComision, fijarSlippage, restablecer } = useCostes();
  const pctComision = fraccionComoPorcentaje(comision);
  const pctSlippage = fraccionComoPorcentaje(slippage);
  return (
    <Tarjeta como="section" className="p-5" aria-labelledby="costes-titulo">
      <h3 id="costes-titulo" className="text-[0.9375rem] font-semibold text-tinta">
        Costes de toda simulación
      </h3>
      <p className="mt-1 text-sm text-tinta-suave">
        Obligatorios a propósito: una simulación sin comisiones es una mentira optimista. Se guardan en este navegador.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-3">
        <label className="flex flex-col gap-1.5 text-[0.9375rem] font-medium">
          Comisión por operación
          <span className="flex items-center gap-2">
            <input
              value={comision}
              onChange={(e) => fijarComision(e.target.value)}
              inputMode="decimal"
              aria-invalid={motivo !== null && motivo.toLowerCase().includes("comisión") ? true : undefined}
              className={clases(ESTILO_ENTRADA, "cifras w-32")}
            />
            <span className="cifras text-sm font-normal text-tinta-suave">{pctComision ?? "?"}</span>
          </span>
        </label>
        <label className="flex flex-col gap-1.5 text-[0.9375rem] font-medium">
          Deslizamiento (slippage)
          <span className="flex items-center gap-2">
            <input
              value={slippage}
              onChange={(e) => fijarSlippage(e.target.value)}
              inputMode="decimal"
              aria-invalid={motivo !== null && motivo.toLowerCase().includes("slippage") ? true : undefined}
              className={clases(ESTILO_ENTRADA, "cifras w-32")}
            />
            <span className="cifras text-sm font-normal text-tinta-suave">{pctSlippage ?? "?"}</span>
          </span>
        </label>
        <button
          type="button"
          onClick={restablecer}
          className="min-h-12 text-sm font-medium text-marca underline underline-offset-4"
        >
          Volver a 0.001 / 0.0005
        </button>
      </div>
      {motivo ? (
        <p className="mt-3 text-sm font-medium text-real-tinta" role="alert">
          {motivo} No se puede simular hasta corregirlo.
        </p>
      ) : null}
    </Tarjeta>
  );
}
