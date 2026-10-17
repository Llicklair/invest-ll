"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Preferencias de este navegador (costes, tema, sesion del chat) en localStorage/sessionStorage.
 * Todo acceso va envuelto: en una ventana privada o con el almacenamiento bloqueado el panel
 * sigue funcionando con los valores por defecto, solo que sin recordarlos.
 */

type Tipo = "local" | "sesion";

const EVENTO = "invest-ll-almacen";

function almacen(tipo: Tipo): Storage | null {
  try {
    return tipo === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

export function leer(tipo: Tipo, clave: string): string | null {
  try {
    return almacen(tipo)?.getItem(clave) ?? null;
  } catch {
    return null;
  }
}

export function escribir(tipo: Tipo, clave: string, valor: string | null): void {
  try {
    const a = almacen(tipo);
    if (a) {
      if (valor === null) a.removeItem(clave);
      else a.setItem(clave, valor);
    }
  } catch {
    // Sin almacenamiento: se usa el valor solo mientras dure la pagina.
  }
  window.dispatchEvent(new CustomEvent(EVENTO, { detail: clave }));
}

function suscribir(aviso: () => void): () => void {
  window.addEventListener("storage", aviso);
  window.addEventListener(EVENTO, aviso);
  return () => {
    window.removeEventListener("storage", aviso);
    window.removeEventListener(EVENTO, aviso);
  };
}

/**
 * Una cadena guardada, como estado de React. En el HTML exportado vale `porDefecto` (no hay
 * navegador al compilar) y al hidratar toma lo guardado.
 */
export function useGuardado(
  tipo: Tipo,
  clave: string,
  porDefecto: string,
): [string, (valor: string | null) => void] {
  const valor = useSyncExternalStore(
    suscribir,
    () => leer(tipo, clave) ?? porDefecto,
    () => porDefecto,
  );
  const fijar = useCallback((nuevo: string | null) => escribir(tipo, clave, nuevo), [tipo, clave]);
  return [valor, fijar];
}
