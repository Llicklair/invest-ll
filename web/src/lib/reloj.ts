"use client";

import { useEffect, useState } from "react";

/** La hora de ahora, repintada cada `cadaMs`: para lo que dice "hace 12 s". */
export function useAhora(cadaMs = 1000): number {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setAhora(Date.now()), cadaMs);
    return () => window.clearInterval(t);
  }, [cadaMs]);
  return ahora;
}
