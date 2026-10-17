"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { comoErrorApi, type ErrorApi } from "@/api/cliente";

interface Resultado<T> {
  clave: string;
  datos: T | null;
  error: ErrorApi | null;
}

export interface Consulta<T> {
  /** Lo ultimo que llego bien. Mientras se recarga, se conserva (atenuado) en vez de parpadear. */
  datos: T | null;
  /** El error de la peticion vigente, con el `detail` de la API. */
  error: ErrorApi | null;
  /** Hay una peticion en curso para la clave actual. */
  cargando: boolean;
  /** Los `datos` son de una clave anterior (p. ej., otro activo) y se esta pidiendo la nueva. */
  desfasados: boolean;
  recargar: () => void;
}

/**
 * Pide algo a la API cuando cambia `clave` (que debe codificar todo lo que usa `pedirFn`).
 * `clave === null` = todavia no se pide nada.
 */
export function useConsulta<T>(clave: string | null, pedirFn: () => Promise<T>): Consulta<T> {
  const [version, setVersion] = useState(0);
  const [resultado, setResultado] = useState<Resultado<T> | null>(null);
  const fnRef = useRef(pedirFn);

  useEffect(() => {
    fnRef.current = pedirFn;
  });

  const claveVigente = clave === null ? null : `${clave}#${version}`;

  useEffect(() => {
    if (claveVigente === null) return;
    let vigente = true;
    fnRef.current().then(
      (datos) => {
        if (vigente) setResultado({ clave: claveVigente, datos, error: null });
      },
      (error: unknown) => {
        if (vigente) setResultado({ clave: claveVigente, datos: null, error: comoErrorApi(error) });
      },
    );
    return () => {
      vigente = false;
    };
  }, [claveVigente]);

  const recargar = useCallback(() => setVersion((v) => v + 1), []);
  const alDia = resultado !== null && resultado.clave === claveVigente;
  const mismaClave =
    resultado !== null && clave !== null && resultado.clave.startsWith(`${clave}#`);

  return {
    datos: resultado?.datos ?? null,
    error: alDia ? resultado.error : null,
    cargando: claveVigente !== null && !alDia,
    desfasados: resultado !== null && !alDia && !mismaClave,
    recargar,
  };
}

export interface Accion<A extends unknown[], T> {
  ejecutar: (...args: A) => Promise<T | null>;
  resultado: T | null;
  error: ErrorApi | null;
  enCurso: boolean;
  limpiar: () => void;
}

/** Una accion que el operador dispara (un boton): guarda su resultado o su error. */
export function useAccion<A extends unknown[], T>(fn: (...args: A) => Promise<T>): Accion<A, T> {
  const [resultado, setResultado] = useState<T | null>(null);
  const [error, setError] = useState<ErrorApi | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const fnRef = useRef(fn);

  useEffect(() => {
    fnRef.current = fn;
  });

  const ejecutar = useCallback(async (...args: A): Promise<T | null> => {
    setEnCurso(true);
    setError(null);
    try {
      const r = await fnRef.current(...args);
      setResultado(r);
      return r;
    } catch (e) {
      setResultado(null);
      setError(comoErrorApi(e));
      return null;
    } finally {
      setEnCurso(false);
    }
  }, []);

  const limpiar = useCallback(() => {
    setResultado(null);
    setError(null);
  }, []);

  return { ejecutar, resultado, error, enCurso, limpiar };
}

/** Un valor que solo cambia cuando el operador deja de teclear `ms` milisegundos. */
export function useRetardado<T>(valor: T, ms = 350): T {
  const [retardado, setRetardado] = useState(valor);
  useEffect(() => {
    const t = window.setTimeout(() => setRetardado(valor), ms);
    return () => window.clearTimeout(t);
  }, [valor, ms]);
  return retardado;
}
