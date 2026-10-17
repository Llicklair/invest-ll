"use client";

import { api, conPlazo, pedir } from "@/api/cliente";
import type { Catalogo, PorcentajeEstrategia, ResultadoSimulado } from "@/api/tipos";
import { useEstado } from "@/contexto/estado";
import { useConsulta, type Consulta } from "@/lib/consulta";

export function useCatalogo(): Consulta<Catalogo> {
  const { versionDatos } = useEstado();
  return useConsulta(`catalogo:${versionDatos}`, () => pedir(api.GET("/api/estrategias", conPlazo())));
}

/** La clave con que llega `combinado` (contrato v2.1): tu reparto entero. */
export const CLAVE_REPARTO = "reparto";

/**
 * "Tus numeros" para varias estrategias a la vez. La API acepta hasta cuatro por peticion: se
 * trocea y se juntan. Devuelve un mapa clave -> resultado.
 *
 * Con `reparto` (la propuesta: porcentajes que suman 100), el primer trozo lleva sus estrategias
 * y pide tambien `combinado`, que entra en el mapa con la clave "reparto".
 */
export function useSimulaciones(
  claves: readonly string[],
  inicial: string,
  mensual: string,
  desdeAnio: number,
  reparto: readonly PorcentajeEstrategia[] = [],
): Consulta<Map<string, ResultadoSimulado>> {
  const { versionDatos } = useEstado();
  const conReparto = reparto.length > 1 ? reparto : [];
  const delReparto = conReparto.map((r) => r.estrategia);
  // Las del reparto, primero y juntas (la API calcula `combinado` con las de esa peticion).
  const lista = [...delReparto, ...[...claves].filter((c) => !delReparto.includes(c)).sort()];
  const firmaReparto = conReparto.map((r) => `${r.estrategia}=${r.porcentaje}`).join("+");
  const clave = lista.length ? `simular:${lista.join(",")}:${firmaReparto}:${inicial}:${mensual}:${desdeAnio}:${versionDatos}` : null;
  return useConsulta(clave, async () => {
    const trozos: string[][] = [];
    for (let i = 0; i < lista.length; i += 4) trozos.push(lista.slice(i, i + 4));
    const respuestas = await Promise.all(
      trozos.map((t, i) =>
        pedir(
          api.POST("/api/estrategias/simular", {
            body: {
              estrategias: t,
              inicial,
              mensual,
              desde_anio: desdeAnio,
              ...(i === 0 && conReparto.length ? { reparto: [...conReparto] } : {}),
            },
            ...conPlazo(),
          }),
        ),
      ),
    );
    const mapa = new Map<string, ResultadoSimulado>();
    for (const r of respuestas) {
      for (const x of r.resultados) mapa.set(x.clave, x);
      if (r.combinado) mapa.set(CLAVE_REPARTO, r.combinado);
    }
    return mapa;
  });
}

/** Huecos de color fijados a cada estrategia mientras dura la vista: quitar una no repinta a las demas. */
export function asignarHuecos(claves: readonly string[], previos: Readonly<Record<string, number>>): Record<string, number> {
  const resultado: Record<string, number> = {};
  const usados = new Set<number>();
  for (const c of claves) {
    const h = previos[c];
    if (h !== undefined && !usados.has(h)) {
      resultado[c] = h;
      usados.add(h);
    }
  }
  for (const c of claves) {
    if (resultado[c] !== undefined) continue;
    let h = 0;
    while (usados.has(h)) h++;
    resultado[c] = h;
    usados.add(h);
  }
  return resultado;
}
