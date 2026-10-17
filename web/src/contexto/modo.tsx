"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { api, pedir, type ErrorApi } from "@/api/cliente";
import type { Conexion, Modo, ModoPanel } from "@/api/tipos";
import { useConsulta } from "@/lib/consulta";

import { useEstado } from "./estado";

interface ValorModo {
  /** El modo EFECTIVO (entorno si lo fija; si no, el del panel). `null` = no se sabe. */
  modo: ModoPanel | null;
  /** Lo que dice `GET /api/conexion`: claves, cerrojos, que falta. */
  conexion: Conexion | null;
  error: ErrorApi | null;
  cargando: boolean;
  recargar: () => void;
}

const Contexto = createContext<ValorModo | null>(null);

/** El `Modo` de `GET /api/estado` (v1) en el vocabulario del panel v2. */
function desdeEstado(modo: Modo | undefined): ModoPanel | null {
  if (!modo) return null;
  if (modo.es_real) return "real";
  if (modo.envia_ordenes) return "pruebas";
  return "simulacion";
}

/**
 * El modo va en todas las pantallas (la pildora y la franja roja), asi que se lee una vez aqui.
 * La fuente es `GET /api/conexion`; si no responde, `GET /api/estado`, que dice lo mismo con
 * menos detalle. Si ninguna responde, el modo es desconocido y nada que mueva dinero se ofrece.
 */
export function ProveedorModo({ children }: { children: ReactNode }) {
  const { estado, error: errorEstado, versionDatos } = useEstado();
  const consulta = useConsulta(`conexion:${versionDatos}`, () => pedir(api.GET("/api/conexion")));

  const valor = useMemo<ValorModo>(() => {
    const modo = consulta.datos?.modo ?? desdeEstado(estado?.modo);
    return {
      modo,
      conexion: consulta.datos,
      error: modo === null ? (consulta.error ?? errorEstado) : null,
      cargando: consulta.cargando,
      recargar: consulta.recargar,
    };
  }, [consulta.datos, consulta.error, consulta.cargando, consulta.recargar, estado, errorEstado]);

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useModo(): ValorModo {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useModo fuera de ProveedorModo");
  return valor;
}

export const NOMBRE_MODO: Record<ModoPanel, string> = {
  simulacion: "Simulación",
  pruebas: "Pruebas",
  real: "Dinero real",
};
