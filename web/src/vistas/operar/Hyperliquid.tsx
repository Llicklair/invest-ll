"use client";

import { Plug, ShieldCheck, Wallet } from "lucide-react";

import { api, pedir } from "@/api/cliente";
import type { EstadoExchange } from "@/api/tipos";
import { BotonEnlace, ErrorApiVista, Esqueleto, Tarjeta } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";

/** El estado de Hyperliquid en Conexiones: sin conectar, en su red de pruebas o con dinero real. */
export function useHyperliquid() {
  const conexiones = useConsulta("conexiones:hyperliquid", () => pedir(api.GET("/api/conexiones")));
  const estado: EstadoExchange | null = conexiones.datos?.exchanges.find((e) => e.id === "hyperliquid") ?? null;
  return { conexiones, estado };
}

/**
 * Lo que va en el sitio del boleto en la pestaña Hyperliquid mientras no está conectado: qué hace
 * falta para operar de verdad y adónde ir. Nada se envía sin conexión.
 */
export function SinConectarHyperliquid() {
  return (
    <Tarjeta className="space-y-4 p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-marca-suave text-marca" aria-hidden="true">
          <Plug className="h-5 w-5" strokeWidth={1.75} />
        </span>
        <div>
          <h2 className="titular text-lg font-semibold text-tinta">Opera de verdad en Hyperliquid</h2>
          <p className="mt-1 text-[0.9375rem] leading-relaxed text-tinta-suave">
            Para enviar órdenes reales, conecta tu cuenta de Hyperliquid. Primero en su red de pruebas (dinero de pruebas, órdenes de verdad) y, cuando quieras,
            con dinero real.
          </p>
        </div>
      </div>
      <ul className="space-y-2 text-[0.9375rem] text-tinta">
        <li className="flex items-start gap-2">
          <Wallet aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-marca" />
          Con tu wallet (MetaMask, Rabby…): firmas una vez y el panel opera con una wallet agente que no puede retirar tus fondos.
        </li>
        <li className="flex items-start gap-2">
          <ShieldCheck aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-marca" />
          Cada orden real te dice qué va a pasar y la confirmas tecleando la cantidad.
        </li>
      </ul>
      <BotonEnlace href="/conexiones/" variante="primario" className="w-full">
        Conectar Hyperliquid
      </BotonEnlace>
      <p className="text-sm text-tinta-suave">Mientras, la gráfica, el libro y tus bots se ven igual: los precios son los de Hyperliquid de verdad.</p>
    </Tarjeta>
  );
}

/** El sitio del boleto en la pestaña Hyperliquid. */
export function PanelHyperliquid() {
  const { conexiones, estado } = useHyperliquid();
  if (conexiones.error) return <ErrorApiVista error={conexiones.error} reintentar={conexiones.recargar} />;
  if (!conexiones.datos) return <Esqueleto className="h-[26rem]" />;
  if (!estado || estado.activo === "sin_conectar") return <SinConectarHyperliquid />;
  return <SinConectarHyperliquid />;
}
