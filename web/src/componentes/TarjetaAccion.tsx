"use client";

import { ArrowRight, ArrowUpRight, ChevronRight, Coins, Landmark, PlugZap } from "lucide-react";
import Link from "next/link";

import type { Accion, ModoPanel } from "@/api/tipos";
import { formatoCantidad } from "@/lib/decimal";
import { enMoneda, fechaCorta } from "@/lib/formato";
import { base } from "@/lib/nombres";

import { BotonEnlace, Boton, Chip, Tarjeta, clases } from "./ui";

/** "0,00123 BTC ≈ 100 USDT" (Binance) o "unas 0,14 participaciones" (broker). */
export function cuantoAccion(a: Accion): string {
  const importe = enMoneda(a.importe, a.moneda, { decimales: a.moneda.toUpperCase() === "EUR" ? 0 : 2 });
  if (a.donde === "binance") {
    const cantidad = a.cantidad ? `${formatoCantidad(a.cantidad)} ${base(a.par ?? a.simbolo)}` : null;
    return cantidad ? `${cantidad} ≈ ${importe}` : `≈ ${importe}`;
  }
  // En el broker la cantidad de la API es del fondo de EE.UU. con el que se calcula (SPY), no del
  // europeo que se compra desde Espana: no se ensena para no confundir. Lo que cuenta es el importe.
  return `Unos ${importe}`;
}

function IconoDonde({ donde, lado }: { donde: Accion["donde"]; lado: Accion["lado"] }) {
  // En el broker, una venta se distingue de un vistazo de la lista de la compra.
  const Icono = donde === "binance" ? Coins : lado === "sell" ? ArrowUpRight : Landmark;
  return (
    <span
      className={clases(
        "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
        donde === "binance" ? "bg-destaque-suave text-destaque-tinta" : "bg-marca-suave text-marca",
      )}
      aria-hidden="true"
    >
      <Icono className="h-5 w-5" strokeWidth={1.75} />
    </span>
  );
}

/**
 * Algo que toca hacer hoy. En Binance se revisa y se confirma aqui (en simulacion, el boton lleva
 * a conectar Binance); en tu broker es una venta (`lado="sell"`, va primero: lo que libera esta ya
 * en la lista de la compra) o una linea de la lista de la compra, y la anotas al hacerla.
 */
export function TarjetaAccion({
  accion: a,
  modo,
  onConfirmar,
  onHecho,
}: {
  accion: Accion;
  modo: ModoPanel | null;
  onConfirmar: (a: Accion) => void;
  onHecho: (a: Accion) => void;
}) {
  const binance = a.donde === "binance";
  const venta = a.lado === "sell";
  return (
    <Tarjeta como="article" className="flex flex-col gap-4 p-5 sm:p-6" id={`accion-${a.id}`}>
      <div className="flex items-start gap-4">
        <IconoDonde donde={a.donde} lado={a.lado} />
        <div className="min-w-0 flex-1 self-center">
          <h3 className="text-lg leading-snug font-semibold text-tinta">{a.titulo}</h3>
          {binance ? <p className="cifras mt-0.5 text-[0.9375rem] font-medium text-tinta">{cuantoAccion(a)}</p> : null}
        </div>
      </div>
      {/* En el movil el cuerpo usa todo el ancho; desde sm, alineado con el titulo. */}
      <div className="-mt-1 sm:pl-[60px]">
        <div>
          <p className="text-[0.9375rem] leading-relaxed text-tinta-suave">{a.explicacion}</p>
          {!binance && a.equivalente ? (
            <p className="mt-3 rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] leading-relaxed text-tinta">
              {venta ? (
                <>
                  <span className="font-semibold">Qué vender: </span>
                  el fondo que compraste para esto, {a.equivalente}.
                </>
              ) : (
                <>
                  <span className="font-semibold">Qué comprar desde España: </span>
                  {a.equivalente}
                </>
              )}
            </p>
          ) : null}
          {a.precio_ref ? (
            <p className="cifras mt-2 text-sm text-tinta-suave">
              {binance ? (
                <>
                  Precio de referencia: {enMoneda(a.precio_ref, a.precio_ref_moneda ?? a.moneda)}
                  {a.precio_fecha ? ` (cierre del ${fechaCorta(a.precio_fecha)})` : ""}. El de la orden será el del momento.
                </>
              ) : (
                <>
                  Para calcularlo se usa el fondo de EE.UU. al que imita ({a.referencia ?? a.simbolo}), que cerró a{" "}
                  {enMoneda(a.precio_ref, a.precio_ref_moneda ?? "USD")}
                  {a.precio_fecha ? ` el ${fechaCorta(a.precio_fecha)}` : ""}. El tuyo, el europeo, tiene otro precio y va en euros.
                </>
              )}
            </p>
          ) : null}
        </div>
      </div>
      <div className="flex flex-col items-stretch gap-3 border-t border-linea pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <Chip tono={binance ? "destaque" : "marca"} className="self-start sm:self-auto">
          {binance ? "En Binance · lo hace el panel" : venta ? "En tu bróker · lo vendes tú" : "En tu bróker · lo haces tú"}
        </Chip>
        {binance ? (
          modo === "simulacion" ? (
            <BotonEnlace href="/conexiones/" variante="secundario">
              <PlugZap aria-hidden="true" className="h-4 w-4" />
              Conectar Binance para hacerlo de verdad
            </BotonEnlace>
          ) : (
            <Boton
              variante={modo === "real" ? "real" : "primario"}
              onClick={() => onConfirmar(a)}
              disabled={modo === null}
              title={modo === null ? "No se sabe el modo: no se ofrece enviar nada" : undefined}
            >
              Revisar y confirmar
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </Boton>
          )
        ) : (
          <Boton variante="secundario" onClick={() => onHecho(a)}>
            {venta ? "Ya lo he vendido" : "Ya lo he comprado"}
          </Boton>
        )}
      </div>
    </Tarjeta>
  );
}

/** La version del Resumen: una fila que lleva a Invertir, donde se hace. */
export function FilaAccion({ accion: a }: { accion: Accion }) {
  return (
    <li>
      <Link
        href={`/plan/invertir/#accion-${a.id}`}
        className="flex min-h-16 items-center gap-4 rounded-xl px-3 py-3 hover:bg-superficie-2"
      >
        <IconoDonde donde={a.donde} lado={a.lado} />
        <span className="min-w-0 flex-1">
          <span className="block font-semibold text-tinta">{a.titulo}</span>
          <span className="cifras block text-sm text-tinta-suave">
            {a.donde === "binance"
              ? `${cuantoAccion(a)} · en Binance`
              : a.lado === "sell"
                ? "En tu bróker · lo vendes tú"
                : "En tu bróker · lo compras tú"}
          </span>
        </span>
        <ChevronRight aria-hidden="true" className="h-5 w-5 shrink-0 text-tinta-suave" />
      </Link>
    </li>
  );
}
