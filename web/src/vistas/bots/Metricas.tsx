"use client";

import { ArrowDownRight, ArrowUpRight, Eye, Moon } from "lucide-react";
import type { ReactNode } from "react";

import type { MetricasBot, PendienteBot } from "@/api/tipos";
import { Aviso, clases } from "@/componentes/ui";
import { formatoImporte } from "@/lib/decimal";
import { fraccion, precio as formatoPrecio, signoImporteVisible, signoVisible } from "@/lib/formato";
import { useAhora } from "@/lib/reloj";

import { usdc } from "./comun";

function Celda({ etiqueta, valor, explica, tono }: { etiqueta: string; valor: ReactNode; explica: string; tono?: -1 | 0 | 1 | null }) {
  return (
    <div className="rounded-xl border border-linea bg-superficie p-4">
      <dt className="text-sm text-tinta-suave">{etiqueta}</dt>
      <dd className={clases("cifras mt-1 text-xl font-semibold", tono === 1 ? "text-sube-texto" : tono === -1 ? "text-baja-texto" : "text-tinta")}>{valor}</dd>
      <dd className="mt-1 text-sm leading-relaxed text-tinta-suave">{explica}</dd>
    </div>
  );
}

function pct(v: number | null): string {
  return v === null ? "—" : fraccion(v, 0).replace(/^\+/, "");
}

function dinero(v: string | null, conSigno = true): string {
  return v === null ? "—" : usdc(v, { conSigno });
}

/**
 * Las métricas de un bot (docs/panel-v5.md §4), cada una con lo que quiere decir. Con pocas
 * operaciones cerradas lo dice arriba: un 100 % de aciertos con una venta no es nada.
 */
export function PanelMetricas({ m, compacto = false }: { m: MetricasBot; compacto?: boolean }) {
  const frente = m.frente_a_mantener;
  const frenteTexto = frente === null ? "—" : `${fraccion(frente, 1).replace(/\s*%$/, "")} puntos`;
  const celdas = [
    {
      etiqueta: "Aciertos",
      valor: m.aciertos === null ? "—" : `${pct(m.aciertos)} de ${m.cerradas}`,
      explica: "De las ventas que ha cerrado, cuántas cobraron más de lo que le costó de media lo vendido.",
      tono: null,
    },
    {
      etiqueta: "Frente a solo mantener",
      valor: frenteTexto,
      explica: "Su ganancia menos la de haber comprado sus monedas al arrancar y no hacer nada más.",
      tono: frente === null ? null : signoVisible(frente, frenteTexto),
    },
    {
      etiqueta: "Resultado de sus ventas",
      valor: dinero(m.realizada),
      explica: "Lo cobrado al vender, frente a lo que le costó de media lo vendido (comisiones incluidas).",
      tono: signoImporteVisible(m.realizada),
    },
    {
      etiqueta: "Si vendiera ahora",
      valor: dinero(m.sin_realizar),
      explica: "Lo que ganaría o perdería con lo que tiene comprado, a precios de ahora.",
      tono: signoImporteVisible(m.sin_realizar),
    },
    {
      etiqueta: "Factor de beneficio",
      valor: m.factor_beneficio === null ? "—" : m.factor_beneficio.toLocaleString("es-ES", { maximumFractionDigits: 2 }),
      explica: m.factor_beneficio === null ? "Aún no ha perdido en ninguna venta: no hay con qué comparar." : "Lo ganado en las ventas buenas entre lo perdido en las malas. Por encima de 1, gana más de lo que pierde.",
      tono: null,
    },
    {
      etiqueta: "Venta buena / mala, de media",
      valor: `${m.ganancia_media === null ? "—" : usdc(m.ganancia_media, { conSigno: true })} / ${m.perdida_media === null ? "—" : usdc(m.perdida_media, { conSigno: true })}`,
      explica: "Lo que gana de media cuando acierta y lo que pierde cuando falla.",
      tono: null,
    },
    {
      etiqueta: "Comisiones pagadas",
      valor: `${formatoImporte(m.comisiones, { decimales: 2 })} USDC`,
      explica: `En ${m.operaciones} ${m.operaciones === 1 ? "operación" : "operaciones"} (${m.compras} compras y ${m.ventas} ventas). Ya están descontadas de todo lo demás.`,
      tono: null,
    },
    {
      etiqueta: "Tiempo dentro",
      valor: pct(m.tiempo_dentro),
      explica: "La parte del tiempo, desde que arrancó, en que ha tenido alguna moneda comprada.",
      tono: null,
    },
    {
      etiqueta: "Operaciones al día",
      valor: m.operaciones_dia === null ? "—" : m.operaciones_dia.toLocaleString("es-ES", { maximumFractionDigits: 1 }),
      explica: m.operaciones_dia === null ? "Se calcula cuando lleve un día en marcha." : "De media desde que arrancó. Más operaciones, más comisiones.",
      tono: null,
    },
  ];
  const vistas = compacto ? celdas.slice(0, 4) : celdas;
  return (
    <div className="space-y-3">
      {m.aviso ? <Aviso tipo="info">{m.aviso}</Aviso> : null}
      <dl className={clases("grid gap-3", compacto ? "sm:grid-cols-2 xl:grid-cols-4" : "sm:grid-cols-2 lg:grid-cols-3")}>
        {vistas.map((c) => (
          <Celda key={c.etiqueta} etiqueta={c.etiqueta} valor={c.valor} explica={c.explica} tono={c.tono} />
        ))}
      </dl>
    </div>
  );
}

const ICONO_PENDIENTE: Record<PendienteBot["tipo"], typeof Eye> = { compra: ArrowDownRight, venta: ArrowUpRight, mirar: Eye, nada: Moon };
const TONO_PENDIENTE: Record<PendienteBot["tipo"], string> = {
  compra: "bg-sube-suave text-sube-texto",
  venta: "bg-baja-suave text-baja-texto",
  mirar: "bg-marca-suave text-marca",
  nada: "bg-superficie-2 text-tinta-suave",
};

/** "en 4 min", "en 3 h", "en 2 días": cuánto falta. */
function dentroDe(cuando: string, ahora: number): string {
  const s = Math.round((Date.parse(cuando) - ahora) / 1000);
  if (Number.isNaN(s)) return "";
  if (s <= 0) return "ahora";
  if (s < 60) return `en ${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `en ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `en ${h} h`;
  const d = Math.round(h / 24);
  return `en ${d} ${d === 1 ? "día" : "días"}`;
}

/** "si sube un 1,2 %" o "en 14 min": lo que falta para que pase. */
function Distancia({ p, ahora }: { p: PendienteBot; ahora: number }) {
  if (p.distancia !== null && p.distancia !== undefined) {
    const sube = p.distancia >= 0;
    return (
      <span className="cifras text-sm whitespace-nowrap text-tinta-suave">
        si {sube ? "sube" : "baja"} un {fraccion(Math.abs(p.distancia), 1).replace(/^\+/, "")}
      </span>
    );
  }
  if (p.cuando) return <span className="text-sm whitespace-nowrap text-tinta-suave">{dentroDe(p.cuando, ahora)}</span>;
  return null;
}

/**
 * Qué hará después (docs/panel-v5.md §4), en llano: lo más cercano primero. En la rejilla, el
 * escalón más cerca del precio de ahora (arriba o abajo) se marca: es lo próximo que pasará.
 */
export function ListaPendientes({ pendientes, max }: { pendientes: readonly PendienteBot[]; max?: number }) {
  const ahora = useAhora(5000);
  if (!pendientes.length) return <p className="text-[0.9375rem] text-tinta-suave">No tiene nada preparado ahora mismo.</p>;
  const cercano = pendientes.reduce<PendienteBot | null>((a, p) => {
    if (p.distancia === null || p.distancia === undefined) return a;
    if (a === null || a.distancia === null || a.distancia === undefined) return p;
    return Math.abs(p.distancia) < Math.abs(a.distancia) ? p : a;
  }, null);
  // En el resumen (`max`), los más cercanos al precio de ahora, en su orden; en la lista entera, todos.
  const distancia = (p: PendienteBot) => (p.distancia === null || p.distancia === undefined ? Infinity : Math.abs(p.distancia));
  const vistos = max ? [...pendientes].sort((a, b) => distancia(a) - distancia(b)).slice(0, max).sort((a, b) => pendientes.indexOf(a) - pendientes.indexOf(b)) : pendientes;
  // El precio de ahora, sacado de cualquier pendiente con precio y distancia (precio / (1 + distancia)).
  const conPrecio = pendientes.find((p) => p.precio && p.distancia !== null && p.distancia !== undefined);
  const precioAhora = conPrecio?.precio && conPrecio.distancia !== null && conPrecio.distancia !== undefined ? Number(conPrecio.precio) / (1 + conPrecio.distancia) : null;
  return (
    <ol className="divide-y divide-linea overflow-hidden rounded-tarjeta border border-linea bg-superficie">
      {vistos.map((p, i) => {
        const Icono = ICONO_PENDIENTE[p.tipo];
        const esCercano = p === cercano && pendientes.length > 1;
        const anterior = vistos[i - 1];
        // La raya del precio de ahora: entre lo último que vende si sube y lo primero que compra si baja.
        const raya =
          precioAhora !== null && anterior && (anterior.distancia ?? 0) > 0 && (p.distancia ?? 0) <= 0 ? (
            <li key="precio-ahora" className="flex items-center gap-3 bg-superficie-2 px-4 py-2 text-sm font-semibold text-tinta sm:px-5">
              <span aria-hidden="true" className="h-px flex-1 bg-linea-control" />
              Precio ahora: {formatoPrecio(precioAhora)} USDC
              <span aria-hidden="true" className="h-px flex-1 bg-linea-control" />
            </li>
          ) : null;
        return [
          raya,
          <li key={`${p.tipo}-${p.precio ?? p.cuando ?? i}`} className={clases("flex flex-wrap items-start gap-x-3 gap-y-1 px-4 py-3 sm:flex-nowrap sm:px-5", esCercano && "bg-destaque-suave/50")}>
            <span className={clases("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", TONO_PENDIENTE[p.tipo])} aria-hidden="true">
              <Icono className="h-4 w-4" strokeWidth={2} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[0.9375rem] leading-relaxed text-tinta">
                {esCercano ? <span className="mr-1.5 rounded-full bg-destaque px-2 py-0.5 text-xs font-semibold text-destaque-tinta">Lo próximo</span> : null}
                {p.texto}
              </p>
            </div>
            <span className="w-full pl-11 sm:w-auto sm:pl-0">
              <Distancia p={p} ahora={ahora} />
            </span>
          </li>,
        ];
      })}
    </ol>
  );
}
