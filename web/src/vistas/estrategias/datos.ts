"use client";

import { api, conPlazo, pedir } from "@/api/cliente";
import type { Catalogo, ResultadoSimulado } from "@/api/tipos";
import { useEstado } from "@/contexto/estado";
import { useConsulta, type Consulta } from "@/lib/consulta";

export function useCatalogo(): Consulta<Catalogo> {
  const { versionDatos } = useEstado();
  return useConsulta(`catalogo:${versionDatos}`, () => pedir(api.GET("/api/estrategias", conPlazo())));
}

/**
 * "Tus numeros" para varias estrategias a la vez. La API acepta hasta cuatro por peticion: se
 * trocea y se juntan. Devuelve un mapa clave -> resultado.
 */
export function useSimulaciones(
  claves: readonly string[],
  inicial: string,
  mensual: string,
  desdeAnio: number,
): Consulta<Map<string, ResultadoSimulado>> {
  const { versionDatos } = useEstado();
  const lista = [...claves].sort();
  const clave = lista.length ? `simular:${lista.join(",")}:${inicial}:${mensual}:${desdeAnio}:${versionDatos}` : null;
  return useConsulta(clave, async () => {
    const trozos: string[][] = [];
    for (let i = 0; i < lista.length; i += 4) trozos.push(lista.slice(i, i + 4));
    const respuestas = await Promise.all(
      trozos.map((t) =>
        pedir(
          api.POST("/api/estrategias/simular", { body: { estrategias: t, inicial, mensual, desde_anio: desdeAnio }, ...conPlazo() }),
        ),
      ),
    );
    const mapa = new Map<string, ResultadoSimulado>();
    for (const r of respuestas) for (const x of r.resultados) mapa.set(x.clave, x);
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
