"use client";

import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";

import { clases } from "./ui";

type Lectura = { tono: "vivo" | "aviso" | "neutro"; palabra: string; detalle: string };

const CADA_MS = 15_000;

/**
 * Abajo del menu, en todas las pantallas: si llegan precios en directo de Hyperliquid
 * (docs/panel-v5.md, seccion 2). Pregunta a `/api/vivo/estado` cada 15 s: no abre el stream, que
 * es de las pantallas que lo necesitan (Bots, Operar, Resumen).
 */
export function IndicadorDirecto({ compacta, movil = false }: { compacta: boolean; movil?: boolean }) {
  const [lectura, setLectura] = useState<Lectura>({ tono: "neutro", palabra: "Conectando…", detalle: "Preguntando a la API local." });

  useEffect(() => {
    let vivo = true;
    const preguntar = async () => {
      try {
        const e = await pedir(api.GET("/api/vivo/estado"));
        if (!vivo) return;
        setLectura(
          e.conectado
            ? { tono: "vivo", palabra: "En directo", detalle: `Precios en directo de ${e.fuente}.` }
            : { tono: "aviso", palabra: "Sin directo", detalle: e.aviso ?? `No llegan precios de ${e.fuente}.` },
        );
      } catch {
        if (vivo) setLectura({ tono: "aviso", palabra: "Sin API", detalle: "La API local no responde: ¿está el panel en marcha?" });
      }
    };
    void preguntar();
    const t = window.setInterval(() => void preguntar(), CADA_MS);
    return () => {
      vivo = false;
      window.clearInterval(t);
    };
  }, []);

  const punto = (
    <span
      aria-hidden="true"
      className={clases(
        "h-2 w-2 shrink-0 rounded-full",
        lectura.tono === "vivo" ? "bg-sube animate-pulse motion-reduce:animate-none" : lectura.tono === "aviso" ? "bg-pruebas" : "bg-tinta-suave/50",
      )}
    />
  );

  if (compacta) {
    return (
      <p className="flex justify-center py-2" title={`${lectura.palabra}. ${lectura.detalle}`}>
        {punto}
        <span className="sr-only">
          {lectura.palabra}. {lectura.detalle}
        </span>
      </p>
    );
  }
  return (
    <p
      role="status"
      title={lectura.detalle}
      className={clases(
        "flex items-center gap-2 text-sm",
        movil ? "rounded-full bg-superficie-2 px-3 py-1.5" : "mx-3 rounded-xl border border-linea px-3 py-2.5",
        lectura.tono === "vivo" ? "text-tinta" : "text-tinta-suave",
      )}
    >
      {punto}
      <span className="font-medium">{lectura.palabra}</span>
      {movil ? null : <span className="sr-only">. {lectura.detalle}</span>}
    </p>
  );
}
