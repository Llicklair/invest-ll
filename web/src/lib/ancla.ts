"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * El ancla de la URL (#investigacion) como estado: las subsecciones de una pagina se pueden
 * enlazar y el boton de atras del navegador vuelve a la anterior. En el HTML exportado vale "".
 */
function suscribir(aviso: () => void): () => void {
  window.addEventListener("hashchange", aviso);
  return () => window.removeEventListener("hashchange", aviso);
}

export function useAncla(): [string, (nueva: string) => void] {
  const ancla = useSyncExternalStore(
    suscribir,
    () => decodeURIComponent(window.location.hash.slice(1)),
    () => "",
  );
  const fijar = useCallback((nueva: string) => {
    if (decodeURIComponent(window.location.hash.slice(1)) === nueva) return;
    window.location.hash = nueva;
  }, []);
  return [ancla, fijar];
}
