"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { memo, useMemo, useState } from "react";

import type { NivelLibro, OperacionMercado } from "@/api/tipos";
import { useVivo } from "@/api/vivo";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { clases } from "@/componentes/ui";
import { cantidadMoneda, horaSegundos, precioFijo } from "@/lib/vivo";

interface Fila {
  precio: number;
  cantidad: number;
  acumulado: number;
  ordenes: number;
}

function acumular(niveles: readonly NivelLibro[], n: number): Fila[] {
  let suma = 0;
  return niveles.slice(0, n).map((l) => {
    suma += l.cantidad;
    return { precio: l.precio, cantidad: l.cantidad, acumulado: suma, ordenes: l.ordenes };
  });
}

/**
 * Una fila del libro. Memoizada: con el libro llegando 5 veces por segundo, solo se repintan las
 * filas que cambian. La barra de profundidad es un fondo lavado (no un bloque) que crece desde la
 * derecha con lo acumulado.
 */
const FilaLibro = memo(function FilaLibro({
  precio,
  cantidad,
  acumulado,
  fraccion,
  lado,
  decimales,
  decimalesCantidad,
}: {
  precio: number;
  cantidad: number;
  acumulado: number;
  fraccion: number;
  lado: "compra" | "venta";
  decimales: number;
  decimalesCantidad: number;
}) {
  const color = lado === "compra" ? "var(--sube-suave)" : "var(--baja-suave)";
  const pct = Math.max(0, Math.min(100, fraccion * 100)).toFixed(1);
  return (
    <tr style={{ background: `linear-gradient(to left, ${color} ${pct}%, transparent ${pct}%)` }}>
      <th scope="row" className={clases("py-[3px] pr-2 pl-3 text-left font-medium", lado === "compra" ? "text-sube-texto" : "text-baja-texto")}>
        {precioFijo(precio, decimales)}
      </th>
      <td className="px-2 py-[3px] text-right text-tinta">{cantidadMoneda(cantidad, decimalesCantidad)}</td>
      <td className="py-[3px] pr-3 pl-2 text-right text-tinta-suave">{cantidadMoneda(acumulado, decimalesCantidad)}</td>
    </tr>
  );
});

/**
 * El libro de ordenes en vivo (docs/panel-v3-vivo.md, seccion 2): ventas arriba (la mas barata
 * pegada al centro), compras abajo (la mas cara pegada al centro) y en medio el precio y la
 * diferencia entre las dos. Es una tabla de verdad: el lector de pantalla la recorre fila a fila
 * (con su encabezado por lado). No es una region viva: cambia demasiado para anunciarla.
 */
export function Libro({
  coin,
  decimales,
  decimalesCantidad,
  filas = 11,
  className,
}: {
  coin: string;
  decimales: number;
  decimalesCantidad: number;
  filas?: number;
  className?: string;
}) {
  const libro = useVivo("libro");
  const vigente = libro && libro.coin === coin ? libro : null;
  const ventas = useMemo(() => (vigente ? acumular(vigente.ventas, filas) : []), [vigente, filas]);
  const compras = useMemo(() => (vigente ? acumular(vigente.compras, filas) : []), [vigente, filas]);
  const maximo = Math.max(ventas[ventas.length - 1]?.acumulado ?? 0, compras[compras.length - 1]?.acumulado ?? 0) || 1;
  const mejorVenta = ventas[0]?.precio ?? null;
  const mejorCompra = compras[0]?.precio ?? null;
  const medio = mejorVenta !== null && mejorCompra !== null ? (mejorVenta + mejorCompra) / 2 : null;
  const diferencial = vigente?.diferencial ?? (mejorVenta !== null && mejorCompra !== null ? mejorVenta - mejorCompra : null);
  const pctDif = diferencial !== null && medio ? (diferencial / medio) * 100 : null;

  // La flecha del precio medio: hacia donde se movio desde la foto anterior (palabra para el
  // lector). Estado ajustado al cambiar el dato, el patron de React para "lo anterior".
  const [anterior, setAnterior] = useState<{ medio: number | null; sentido: -1 | 0 | 1 }>({ medio: null, sentido: 0 });
  if (medio !== anterior.medio) {
    setAnterior({ medio, sentido: medio !== null && anterior.medio !== null ? (medio > anterior.medio ? 1 : -1) : 0 });
  }
  const sentido = anterior.sentido;

  return (
    <div className={clases("flex min-w-0 flex-col", className)}>
      <table className="cifras w-full table-fixed border-collapse text-[0.8125rem] leading-5">
        <caption className="sr-only">
          Libro de órdenes de {coin}
          {vigente ? `, foto de las ${horaSegundos(vigente.at)}` : ""}. Precios en USDC, cantidades en {coin}.
        </caption>
        <colgroup>
          <col className="w-[38%]" />
          <col className="w-[31%]" />
          <col className="w-[31%]" />
        </colgroup>
        <thead>
          <tr className="text-xs text-tinta-suave">
            <th scope="col" className="py-1.5 pr-2 pl-3 text-left font-medium">
              Precio <span className="sr-only">en USDC</span>
            </th>
            <th scope="col" className="px-2 py-1.5 text-right font-medium">
              Cantidad <span className="text-tinta-suave/80">({coin})</span>
            </th>
            <th scope="col" className="py-1.5 pr-3 pl-2 text-right font-medium">
              Acumulado
            </th>
          </tr>
        </thead>
        <tbody aria-label="Quieren vender">
          <tr>
            <th scope="rowgroup" colSpan={3} className="px-3 pt-1 pb-0.5 text-left text-[0.6875rem] font-semibold tracking-wide text-baja-texto uppercase">
              Quieren vender
            </th>
          </tr>
          {Array.from({ length: filas }, (_, i) => {
            // De la mas cara (arriba) a la mas barata (pegada al centro).
            const f = ventas[filas - 1 - i];
            if (!f) return <FilaVacia key={`v-${i}`} />;
            return <FilaLibro key={`v-${i}`} lado="venta" {...f} fraccion={f.acumulado / maximo} decimales={decimales} decimalesCantidad={decimalesCantidad} />;
          })}
        </tbody>
        <tbody aria-label="Precio y diferencia">
          <tr className="border-y border-linea bg-superficie-2/60">
            <th scope="row" className="py-1.5 pr-2 pl-3 text-left">
              <span className={clases("inline-flex items-center gap-1 text-base font-semibold", sentido > 0 ? "text-sube-texto" : sentido < 0 ? "text-baja-texto" : "text-tinta")}>
                {sentido > 0 ? <ArrowUp aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2.5} /> : sentido < 0 ? <ArrowDown aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2.5} /> : null}
                {precioFijo(medio, decimales)}
              </span>
              <span className="sr-only"> USDC, precio medio{sentido > 0 ? " (acaba de subir)" : sentido < 0 ? " (acaba de bajar)" : ""}</span>
            </th>
            <td colSpan={2} className="py-1.5 pr-3 pl-2 text-right text-xs text-tinta-suave">
              Diferencia <span className="font-medium text-tinta">{precioFijo(diferencial, decimales)}</span>
              {pctDif !== null ? ` · ${pctDif.toLocaleString("es-ES", { maximumFractionDigits: 3, minimumFractionDigits: 3 })} %` : ""}
            </td>
          </tr>
        </tbody>
        <tbody aria-label="Quieren comprar">
          {Array.from({ length: filas }, (_, i) => {
            const f = compras[i];
            if (!f) return <FilaVacia key={`c-${i}`} />;
            return <FilaLibro key={`c-${i}`} lado="compra" {...f} fraccion={f.acumulado / maximo} decimales={decimales} decimalesCantidad={decimalesCantidad} />;
          })}
          <tr>
            <th scope="rowgroup" colSpan={3} className="px-3 pt-0.5 pb-1 text-left text-[0.6875rem] font-semibold tracking-wide text-sube-texto uppercase">
              Quieren comprar
            </th>
          </tr>
        </tbody>
      </table>
      <div className="mt-auto border-t border-linea px-3 py-1">
        <QueEsEsto clave="libro" className="[&>button]:text-xs" />
      </div>
    </div>
  );
}

function FilaVacia() {
  return (
    <tr aria-hidden="true">
      <td colSpan={3} className="py-[3px]">
        &nbsp;
      </td>
    </tr>
  );
}

const FilaOperacion = memo(function FilaOperacion({ op, decimales, decimalesCantidad }: { op: OperacionMercado; decimales: number; decimalesCantidad: number }) {
  const compra = op.lado === "compra";
  return (
    <tr>
      <td className={clases("py-[3px] pr-2 pl-3 font-medium", compra ? "text-sube-texto" : "text-baja-texto")}>
        <span className="inline-flex items-center gap-1">
          {compra ? <ArrowUp aria-hidden="true" className="h-3 w-3" strokeWidth={2.5} /> : <ArrowDown aria-hidden="true" className="h-3 w-3" strokeWidth={2.5} />}
          {precioFijo(op.precio, decimales)}
        </span>
        <span className="sr-only">{compra ? ", compró quien tenía prisa" : ", vendió quien tenía prisa"}</span>
      </td>
      <td className="px-2 py-[3px] text-right text-tinta">{cantidadMoneda(op.cantidad, decimalesCantidad)}</td>
      <td className="py-[3px] pr-3 pl-2 text-right text-tinta-suave">{horaSegundos(op.at)}</td>
    </tr>
  );
});

/**
 * Las ultimas operaciones de la moneda, la mas reciente arriba. La flecha y el color dicen quien
 * tuvo prisa: hacia arriba, alguien compro al precio de venta; hacia abajo, alguien vendio.
 */
export function UltimasOperaciones({
  coin,
  decimales,
  decimalesCantidad,
  filas = 24,
  className,
}: {
  coin: string;
  decimales: number;
  decimalesCantidad: number;
  filas?: number;
  className?: string;
}) {
  const ops = useVivo("operaciones");
  const lista = ops.filter((o) => o.coin === coin).slice(0, filas);
  return (
    <div className={clases("min-w-0", className)}>
      <table className="cifras w-full table-fixed border-collapse text-[0.8125rem] leading-5">
        <caption className="sr-only">Últimas operaciones de {coin}, la más reciente primero. Precios en USDC.</caption>
        <colgroup>
          <col className="w-[38%]" />
          <col className="w-[31%]" />
          <col className="w-[31%]" />
        </colgroup>
        <thead>
          <tr className="text-xs text-tinta-suave">
            <th scope="col" className="py-1.5 pr-2 pl-3 text-left font-medium">
              Precio
            </th>
            <th scope="col" className="px-2 py-1.5 text-right font-medium">
              Cantidad <span className="text-tinta-suave/80">({coin})</span>
            </th>
            <th scope="col" className="py-1.5 pr-3 pl-2 text-right font-medium">
              Hora
            </th>
          </tr>
        </thead>
        <tbody>
          {lista.length ? (
            lista.map((o) => <FilaOperacion key={`${o.at}|${o.precio}|${o.cantidad}|${o.lado}`} op={o} decimales={decimales} decimalesCantidad={decimalesCantidad} />)
          ) : (
            <tr>
              <td colSpan={3} className="px-3 py-6 text-center text-sm text-tinta-suave">
                Aún no han llegado operaciones.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="border-t border-linea px-3 py-2 text-xs leading-relaxed text-tinta-suave">
        <ArrowUp aria-hidden="true" className="inline h-3 w-3" strokeWidth={2.5} /> alguien compró con prisa (al precio de venta) ·{" "}
        <ArrowDown aria-hidden="true" className="inline h-3 w-3" strokeWidth={2.5} /> alguien vendió con prisa
      </p>
    </div>
  );
}
