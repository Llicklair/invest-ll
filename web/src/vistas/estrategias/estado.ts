"use client";

import { useCallback, useMemo } from "react";

import type { AnteCaida, Horizonte, Perfil, QuiereCripto } from "@/api/tipos";
import { useGuardado } from "@/lib/almacen";
import { leerImporte } from "@/lib/importe";

/** Lo que se ha respondido, tal cual se teclea (los importes, como texto). */
export interface Respuestas {
  inicial: string;
  mensual: string;
  horizonte?: Horizonte;
  ante_caida?: AnteCaida;
  cripto?: QuiereCripto;
}

export interface Recorrido {
  /** 0 Cuentanos · 1 Te proponemos · 2 Tu plan */
  paso: 0 | 1 | 2;
  alcanzado: 0 | 1 | 2;
  /** "perfil": con recomendacion. "catalogo": sin responder, mirando todas. */
  via: "perfil" | "catalogo";
  respuestas: Respuestas;
  desdeAnio: number;
  /** Lo que se precarga en Tu plan (recomendacion o plan actual) y cuando se entro, para rehacerlo. */
  precarga: { estrategia: string; inicial: string; mensual: string }[] | null;
  entrada: number;
}

export const ANIOS = [2018, 2019, 2020, 2021, 2022, 2023] as const;

const INICIAL: Recorrido = {
  paso: 0,
  alcanzado: 0,
  via: "perfil",
  respuestas: { inicial: "", mensual: "" },
  desdeAnio: 2018,
  precarga: null,
  entrada: 0,
};

function leer(texto: string): Recorrido {
  try {
    const v = JSON.parse(texto) as Partial<Recorrido>;
    if (typeof v !== "object" || v === null) return INICIAL;
    const paso = v.paso === 1 || v.paso === 2 ? v.paso : 0;
    const alcanzado = v.alcanzado === 1 || v.alcanzado === 2 ? v.alcanzado : 0;
    return {
      paso,
      alcanzado: Math.max(paso, alcanzado) as Recorrido["alcanzado"],
      via: v.via === "catalogo" ? "catalogo" : "perfil",
      respuestas: { ...INICIAL.respuestas, ...(v.respuestas ?? {}) },
      desdeAnio: ANIOS.includes(v.desdeAnio as (typeof ANIOS)[number]) ? (v.desdeAnio as number) : 2018,
      precarga: Array.isArray(v.precarga) ? v.precarga : null,
      entrada: typeof v.entrada === "number" ? v.entrada : 0,
    };
  } catch {
    return INICIAL;
  }
}

/**
 * El recorrido de Estrategias, guardado en esta pestana del navegador: si Laura se va a mirar
 * otra cosa y vuelve, sigue donde lo dejo (y si cierra la pestana, empieza de cero).
 */
export function useRecorrido(): [Recorrido, (cambio: Partial<Recorrido> | ((r: Recorrido) => Partial<Recorrido>)) => void, () => void] {
  const [texto, guardar] = useGuardado("sesion", "invest-ll.estrategias", JSON.stringify(INICIAL));
  const recorrido = useMemo(() => leer(texto), [texto]);
  const cambiar = useCallback(
    (cambio: Partial<Recorrido> | ((r: Recorrido) => Partial<Recorrido>)) => {
      const actual = leer(texto);
      const parcial = typeof cambio === "function" ? cambio(actual) : cambio;
      const nuevo = { ...actual, ...parcial };
      nuevo.alcanzado = Math.max(nuevo.alcanzado, nuevo.paso) as Recorrido["alcanzado"];
      guardar(JSON.stringify(nuevo));
    },
    [texto, guardar],
  );
  const reiniciar = useCallback(() => guardar(null), [guardar]);
  return [recorrido, cambiar, reiniciar];
}

/** El perfil para la API, o null si falta algo. */
export function perfilDe(r: Respuestas): Perfil | null {
  const inicial = leerImporte(r.inicial === "" ? "0" : r.inicial);
  const mensual = leerImporte(r.mensual === "" ? "0" : r.mensual);
  if (inicial === null || mensual === null || !r.horizonte || !r.ante_caida || !r.cripto) return null;
  return { inicial, mensual, horizonte: r.horizonte, ante_caida: r.ante_caida, cripto: r.cripto };
}
