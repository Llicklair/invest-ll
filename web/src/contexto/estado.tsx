"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { api, pedir, type ErrorApi } from "@/api/cliente";
import type { Estado } from "@/api/tipos";
import { useConsulta } from "@/lib/consulta";

interface ValorEstado {
  estado: Estado | null;
  error: ErrorApi | null;
  cargando: boolean;
  recargar: () => void;
  /**
   * Sube cada vez que cambian los datos descargados (descarga, actualizacion, pausa...). Las
   * pantallas la meten en la clave de sus consultas para releer lo que dependa de ellos.
   */
  versionDatos: number;
  refrescarDatos: () => void;
}

const Contexto = createContext<ValorEstado | null>(null);

export function ProveedorEstado({ children }: { children: ReactNode }) {
  const [versionDatos, setVersionDatos] = useState(0);
  const consulta = useConsulta(`estado:${versionDatos}`, () => pedir(api.GET("/api/estado")));
  const refrescarDatos = useCallback(() => setVersionDatos((v) => v + 1), []);

  const valor = useMemo<ValorEstado>(
    () => ({
      estado: consulta.datos,
      error: consulta.error,
      cargando: consulta.cargando,
      recargar: consulta.recargar,
      versionDatos,
      refrescarDatos,
    }),
    [consulta.datos, consulta.error, consulta.cargando, consulta.recargar, versionDatos, refrescarDatos],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useEstado(): ValorEstado {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useEstado fuera de ProveedorEstado");
  return valor;
}
