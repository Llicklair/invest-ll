"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { useGuardado } from "@/lib/almacen";
import { motivoFraccionInvalida } from "@/lib/decimal";

/** Los mismos valores por defecto que la barra lateral del panel de Streamlit. */
export const COMISION_POR_DEFECTO = "0.001";
export const SLIPPAGE_POR_DEFECTO = "0.0005";

interface ValorCostes {
  /** Fraccion, tal cual se teclea ("0.001"): viaja como cadena, igual que el dinero. */
  comision: string;
  slippage: string;
  /** Por que no se puede simular con estos costes; `null` si son validos. */
  motivo: string | null;
  fijarComision: (valor: string) => void;
  fijarSlippage: (valor: string) => void;
  restablecer: () => void;
}

const Contexto = createContext<ValorCostes | null>(null);

/**
 * Los costes son obligatorios en toda simulacion (Principio IV): la API no tiene valores por
 * defecto, asi que este control alimenta TODAS las peticiones de Simular. Se guardan en este
 * navegador.
 */
export function ProveedorCostes({ children }: { children: ReactNode }) {
  const [comision, fijarComisionGuardada] = useGuardado(
    "local",
    "invest-ll.costes.comision",
    COMISION_POR_DEFECTO,
  );
  const [slippage, fijarSlippageGuardado] = useGuardado(
    "local",
    "invest-ll.costes.slippage",
    SLIPPAGE_POR_DEFECTO,
  );

  const valor = useMemo<ValorCostes>(
    () => ({
      comision: comision.trim(),
      slippage: slippage.trim(),
      motivo:
        motivoFraccionInvalida(comision, "el coste de comisión") ??
        motivoFraccionInvalida(slippage, "el slippage"),
      fijarComision: (v) => fijarComisionGuardada(v),
      fijarSlippage: (v) => fijarSlippageGuardado(v),
      restablecer: () => {
        fijarComisionGuardada(null);
        fijarSlippageGuardado(null);
      },
    }),
    [comision, slippage, fijarComisionGuardada, fijarSlippageGuardado],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useCostes(): ValorCostes {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useCostes fuera de ProveedorCostes");
  return valor;
}
