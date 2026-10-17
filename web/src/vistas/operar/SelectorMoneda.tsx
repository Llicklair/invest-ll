"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import type { MonedaVivo } from "@/api/tipos";
import { CambioPct } from "@/componentes/CifraGrande";
import { clases } from "@/componentes/ui";
import { compacto, decimalesPrecio, normalizar, precioFijo } from "@/lib/vivo";

/**
 * Elegir moneda (docs/panel-v3-vivo.md, seccion 2): un buscador por nombre llano o por su nombre
 * en Hyperliquid, y la lista con precio, variacion de 24 h y volumen, las mas negociadas primero
 * (el orden de la API). Es un <dialog> nativo: atrapa el foco, Escape cierra y devuelve el foco
 * al boton. Las flechas recorren la lista.
 */
export function SelectorMoneda({
  monedas,
  coin,
  onElegir,
}: {
  monedas: readonly MonedaVivo[];
  coin: string;
  onElegir: (coin: string) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const dialogo = useRef<HTMLDialogElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const lista = useRef<HTMLUListElement>(null);
  const idTitulo = useId();
  const actual = monedas.find((m) => m.coin === coin);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (abierto && !d.open) {
      // En escritorio, debajo del boton; en el movil, como hoja desde abajo (lo pone el CSS).
      const r = boton.current?.getBoundingClientRect();
      if (r && window.innerWidth >= 1024) {
        d.style.top = `${Math.round(r.bottom + 8)}px`;
        d.style.left = `${Math.round(r.left)}px`;
      } else {
        d.style.top = "";
        d.style.left = "";
      }
      d.showModal();
    }
    if (!abierto && d.open) d.close();
  }, [abierto]);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    const alCerrar = () => setAbierto(false);
    d.addEventListener("close", alCerrar);
    return () => d.removeEventListener("close", alCerrar);
  }, []);

  const q = normalizar(busqueda);
  const filtradas = q ? monedas.filter((m) => normalizar(m.nombre).includes(q) || normalizar(m.coin).includes(q)) : monedas;

  const elegir = (c: string) => {
    onElegir(c);
    setBusqueda("");
    setAbierto(false);
  };

  const mover = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const botones = Array.from(lista.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    if (!botones.length) return;
    e.preventDefault();
    const i = botones.findIndex((b) => b === document.activeElement);
    const siguiente = e.key === "ArrowDown" ? (i < 0 ? 0 : Math.min(botones.length - 1, i + 1)) : i <= 0 ? -1 : i - 1;
    if (siguiente < 0) dialogo.current?.querySelector<HTMLInputElement>("input")?.focus();
    else botones[siguiente]?.focus();
  };

  return (
    <>
      <button
        ref={boton}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={abierto}
        onClick={() => setAbierto(true)}
        className="group inline-flex min-h-12 items-center gap-2 rounded-xl border border-linea-control/50 bg-superficie px-3 text-left shadow-sm hover:bg-superficie-2"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-marca-suave text-xs font-bold text-marca" aria-hidden="true">
          {coin.replace(/^k/, "").slice(0, 3)}
        </span>
        <span className="min-w-0">
          <span className="block text-[0.9375rem] leading-tight font-semibold text-tinta">{actual?.nombre ?? coin}</span>
          <span className="block text-xs leading-tight text-tinta-suave">{coin} / USDC</span>
        </span>
        <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0 text-tinta-suave" />
        <span className="sr-only">: cambiar de moneda</span>
      </button>
      <dialog
        ref={dialogo}
        aria-labelledby={idTitulo}
        className="selector-moneda"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) setAbierto(false);
        }}
      >
        {abierto ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex items-center justify-between gap-2 px-4 pt-3">
              <h2 id={idTitulo} className="text-[0.9375rem] font-semibold text-tinta">
                Elige una moneda
              </h2>
              <button
                type="button"
                onClick={() => setAbierto(false)}
                aria-label="Cerrar"
                className="-mr-2 inline-flex h-11 w-11 items-center justify-center rounded-full text-tinta-suave hover:bg-superficie-2 hover:text-tinta"
              >
                <X aria-hidden="true" className="h-5 w-5" />
              </button>
            </div>
            <div className="px-4 pb-2">
              <label className="relative block">
                <span className="sr-only">Buscar por nombre</span>
                <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-tinta-suave" />
                <input
                  type="search"
                  value={busqueda}
                  // El foco empieza en el buscador: se abre para buscar.
                  autoFocus
                  onChange={(e) => setBusqueda(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && filtradas[0]) elegir(filtradas[0].coin);
                    mover(e);
                  }}
                  placeholder="Bitcoin, ETH, Solana…"
                  className="min-h-11 w-full rounded-xl border border-linea-control/70 bg-superficie py-2 pr-3 pl-9 text-base text-tinta placeholder:text-tinta-suave/70"
                />
              </label>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_6.5rem_4.5rem_4.5rem] gap-2 border-y border-linea bg-superficie-2 px-4 py-1.5 text-xs font-medium text-tinta-suave max-sm:grid-cols-[minmax(0,1fr)_6.5rem_4.5rem]" aria-hidden="true">
              <span>Moneda</span>
              <span className="text-right">Precio</span>
              <span className="text-right">24 h</span>
              <span className="text-right max-sm:hidden">Volumen</span>
            </div>
            <ul ref={lista} className="min-h-0 flex-1 overflow-y-auto overscroll-contain py-1" onKeyDown={mover} aria-label="Monedas, las más negociadas primero">
              {filtradas.map((m) => {
                const es = m.coin === coin;
                return (
                  <li key={m.coin}>
                    <button
                      type="button"
                      onClick={() => elegir(m.coin)}
                      aria-current={es ? "true" : undefined}
                      className={clases(
                        "grid min-h-12 w-full grid-cols-[minmax(0,1fr)_6.5rem_4.5rem_4.5rem] items-center gap-2 px-4 py-1.5 text-left text-sm hover:bg-superficie-2 focus-visible:bg-superficie-2 max-sm:grid-cols-[minmax(0,1fr)_6.5rem_4.5rem]",
                        es && "bg-marca-suave/60",
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-tinta">{m.nombre}</span>
                        <span className="block text-xs text-tinta-suave">{m.coin}</span>
                      </span>
                      <span className="cifras text-right text-tinta">{precioFijo(m.precio, decimalesPrecio(m.precio, m.decimales_cantidad))}</span>
                      <span className="text-right">
                        <CambioPct pct={m.var_24h} className="text-xs" />
                      </span>
                      <span className="cifras text-right text-xs text-tinta-suave max-sm:hidden">
                        <span className="sr-only">volumen </span>
                        {compacto(m.volumen_24h)}
                      </span>
                    </button>
                  </li>
                );
              })}
              {!filtradas.length ? <li className="px-4 py-6 text-sm text-tinta-suave">Ninguna moneda se llama «{busqueda}».</li> : null}
            </ul>
            <p className="border-t border-linea px-4 py-2 text-xs text-tinta-suave">Precios de Hyperliquid. Volumen de 24 h en USDC.</p>
          </div>
        ) : null}
      </dialog>
    </>
  );
}
