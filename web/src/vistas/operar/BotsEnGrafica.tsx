"use client";

import { Bot, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { PendienteBot, ResumenBot } from "@/api/tipos";
import { useAlmacenVivo, useVivo } from "@/api/vivo";
import { clases } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";

import type { LineaGrafico, MarcaGrafico } from "./GraficoVelas";

const CADA_MS = 15_000;
/** Por bot, las órdenes preparadas más cerca del precio que se pintan (la rejilla tiene muchas). */
const LINEAS_POR_BOT = 3;
/** Las operaciones que se pintan, las más recientes: más taparían las velas. */
const MAX_MARCAS = 40;

/** "Rejilla SOL" cabe; "Compra periódica BTC y ETH" se queda en "Compra". */
function corto(nombre: string): string {
  return nombre.length <= 14 ? nombre : (nombre.split(" ")[0] ?? nombre);
}

/**
 * Los bots que operan con esta moneda, sobre la gráfica (docs/panel-v5.md): sus compras y ventas
 * (del feed "Ahora mismo", más las últimas 200 al entrar) y las órdenes que tienen preparadas (de
 * su ficha, cada 15 s), las más cercanas al precio. Hay que estar dentro de un `ProveedorVivo` con
 * los canales `bots` y `actividad`.
 */
export function useBotsEnGrafica(coin: string, visibles: boolean) {
  const lista = useVivo("bots");
  const actividad = useVivo("actividad");
  const almacen = useAlmacenVivo();
  const [vuelta, setVuelta] = useState(0);

  // Al entrar, las últimas 200 de todos los bots (el stream solo trae las últimas 40).
  useEffect(() => {
    let vivo = true;
    void pedir(api.GET("/api/actividad", { params: { query: { limite: 200 } } }))
      .then((v) => {
        if (vivo) almacen.recibir("actividad", { ...v, inicial: true });
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [almacen]);

  useEffect(() => {
    const t = window.setInterval(() => {
      if (!document.hidden) setVuelta((v) => v + 1);
    }, CADA_MS);
    return () => window.clearInterval(t);
  }, []);

  const bots = useMemo(() => (lista?.bots ?? []).filter((b) => b.monedas.includes(coin)), [lista, coin]);
  const ids = bots.map((b) => b.id).join(",");
  const fichas = useConsulta(visibles && ids ? `bots-grafica:${ids}:${vuelta}` : null, () =>
    Promise.all(ids.split(",").map((id) => pedir(api.GET("/api/bots/{bot_id}", { params: { path: { bot_id: id } } })))),
  );

  const marcas = useMemo<MarcaGrafico[]>(() => {
    if (!visibles) return [];
    // Con un solo bot en la moneda, flechas sin nombre: ya lo dice la franja de arriba y, con muchas
    // operaciones, los nombres taparían las velas.
    const nombres = new Map(bots.map((b) => [b.id, bots.length > 1 ? corto(b.nombre) : ""] as const));
    return (actividad ?? [])
      .filter((m) => m.coin === coin && (m.tipo === "compra" || m.tipo === "venta") && nombres.has(m.bot_id))
      .slice(0, MAX_MARCAS)
      .map((m) => ({ at: m.at, lado: m.tipo === "compra" ? "compra" : "venta", texto: nombres.get(m.bot_id) ?? "" }));
  }, [visibles, actividad, bots, coin]);

  const lineas = useMemo<LineaGrafico[]>(() => {
    if (!visibles || !fichas.datos) return [];
    const salida: LineaGrafico[] = [];
    for (const f of fichas.datos) {
      const conPrecio = f.pendientes.filter((p): p is PendienteBot & { precio: string } => p.coin === coin && p.precio !== null && p.precio !== undefined);
      const cercanas = [...conPrecio].sort((a, b) => Math.abs(a.distancia ?? 1) - Math.abs(b.distancia ?? 1)).slice(0, LINEAS_POR_BOT);
      for (const p of cercanas) {
        salida.push({
          precio: Number(p.precio),
          lado: p.tipo === "compra" ? "compra" : p.tipo === "venta" ? "venta" : "mirar",
          texto: `${corto(f.nombre)}: ${p.tipo === "compra" ? "compra" : p.tipo === "venta" ? "vende" : "mira"}`,
        });
      }
    }
    return salida;
  }, [visibles, fichas.datos, coin]);

  return { bots, marcas, lineas };
}

/** La franja de encima de la gráfica: qué bots se ven y el botón para ocultarlos. */
export function FranjaBots({
  bots,
  visibles,
  onVisibles,
  marcas,
}: {
  bots: readonly ResumenBot[];
  visibles: boolean;
  onVisibles: (v: boolean) => void;
  marcas: number;
}) {
  if (!bots.length) {
    return (
      <p className="flex items-center gap-2 border-b border-linea px-3 py-1.5 text-xs text-tinta-suave sm:px-4">
        <Bot aria-hidden="true" className="h-3.5 w-3.5" />
        Ninguno de tus bots opera con esta moneda.{" "}
        <Link href="/bots/nuevo/" className="font-semibold text-marca underline underline-offset-2">
          Desplegar uno
        </Link>
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-linea px-3 py-1.5 text-xs sm:px-4">
      <span className="flex items-center gap-1.5 font-semibold text-tinta">
        <Bot aria-hidden="true" className="h-3.5 w-3.5 text-marca" />
        En la gráfica:
      </span>
      {bots.map((b) => (
        <Link key={b.id} href={`/bots/ficha/?id=${encodeURIComponent(b.id)}`} className={clases("text-tinta hover:underline", !visibles && "text-tinta-suave line-through")}>
          {b.nombre}
        </Link>
      ))}
      {visibles ? <span className="text-tinta-suave">· {marcas === 1 ? "su última operación" : `sus ${marcas} últimas operaciones`}</span> : null}
      <button
        type="button"
        onClick={() => onVisibles(!visibles)}
        aria-pressed={visibles}
        className="ml-auto inline-flex min-h-8 items-center gap-1 rounded-lg px-2 font-semibold text-marca hover:bg-superficie-2"
      >
        {visibles ? <EyeOff aria-hidden="true" className="h-3.5 w-3.5" /> : <Eye aria-hidden="true" className="h-3.5 w-3.5" />}
        {visibles ? "Ocultar bots" : "Ver bots"}
      </button>
    </div>
  );
}
