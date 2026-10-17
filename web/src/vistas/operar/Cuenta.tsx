"use client";

import { RotateCcw, X } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { api, pedir } from "@/api/cliente";
import type { CuentaPractica, MonedaVivo } from "@/api/tipos";
import { useAlmacenVivo, useVivo } from "@/api/vivo";
import { Variacion } from "@/componentes/CifraGrande";
import { Hoja } from "@/componentes/Hoja";
import { Pestanas } from "@/componentes/Pestanas";
import { Td, Th } from "@/componentes/tabla";
import { Boton, ErrorApiVista, Nota, clases } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";
import { formatoCantidad, formatoImporte, signoDecimal } from "@/lib/decimal";
import { fraccionCoherente, momento } from "@/lib/formato";
import { decimalesPrecio, horaSegundos } from "@/lib/vivo";

import { leerNumero } from "./Boleto";

function decPrecio(monedas: ReadonlyMap<string, MonedaVivo>, coin: string): number {
  const m = monedas.get(coin);
  return m ? decimalesPrecio(m.precio, m.decimales_cantidad) : 2;
}

const usdc = (v: string | null | undefined, conSigno = false) => (v === null || v === undefined ? "—" : `${formatoImporte(v, { conSigno }).replace(/^-/, "−")} USDC`);

/**
 * Saldo, valor y ganancia de la cuenta de practica, en vivo (`cuenta` del stream, ~1 s).
 */
export function ResumenCuenta({ className }: { className?: string }) {
  const cuenta = useVivo("cuenta");
  const [reiniciar, setReiniciar] = useState(false);
  return (
    <section aria-labelledby="titulo-cuenta" className={clases("rounded-tarjeta border border-linea bg-superficie p-4 shadow-suave", className)}>
      <h2 id="titulo-cuenta" className="text-[0.9375rem] font-semibold text-tinta">
        Tu cuenta de práctica
      </h2>
      {cuenta ? (
        <>
          <p className="mt-1 text-sm text-tinta-suave">Lo que vale ahora</p>
          <p className="titular text-[2rem] leading-tight font-medium tracking-tight text-tinta">
            {formatoImporte(cuenta.valor_total).replace(/^-/, "−")} <span className="text-[0.55em] text-tinta-suave">USDC</span>
          </p>
          <Variacion importe={cuenta.ganancia} pct={cuenta.ganancia_pct} moneda="USDC" coletilla={`desde ${formatoImporte(cuenta.inicial, { decimales: 0 })} USDC`} className="mt-2 text-sm" />
          <dl className="cifras mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
            <dt className="text-tinta-suave">Libres</dt>
            <dd className="text-right font-medium text-tinta">{usdc(cuenta.saldo)}</dd>
            <dt className="text-tinta-suave">Apartados en órdenes</dt>
            <dd className="text-right font-medium text-tinta">{usdc(cuenta.reservado)}</dd>
            <dt className="text-tinta-suave">En monedas</dt>
            <dd className="text-right font-medium text-tinta">{cuenta.posiciones.length ? `${cuenta.posiciones.length} ${cuenta.posiciones.length === 1 ? "moneda" : "monedas"}` : "ninguna"}</dd>
          </dl>
          <p className="mt-2 text-xs text-tinta-suave">A precios de las {horaSegundos(cuenta.at)}. Dinero ficticio.</p>
        </>
      ) : (
        <p className="mt-3 text-sm text-tinta-suave">Cargando tu cuenta…</p>
      )}
      <button
        type="button"
        onClick={() => setReiniciar(true)}
        className="-ml-2 mt-1 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-sm font-medium text-marca hover:bg-marca-suave"
      >
        <RotateCcw aria-hidden="true" className="h-4 w-4" />
        Empezar de cero
      </button>
      <HojaReiniciar abierta={reiniciar} onCerrar={() => setReiniciar(false)} cuenta={cuenta} />
    </section>
  );
}

function HojaReiniciar({ abierta, onCerrar, cuenta }: { abierta: boolean; onCerrar: () => void; cuenta: CuentaPractica | null }) {
  const almacen = useAlmacenVivo();
  const [texto, setTexto] = useState("10000");
  const id = useId();
  const accion = useAccion(async (inicial: string) => {
    const c = await pedir(api.POST("/api/practica/reiniciar", { body: { inicial } }));
    almacen.fijarYa("cuenta", c);
    return c;
  });
  const n = leerNumero(texto);
  const valido = n !== null && n > 0;
  return (
    <Hoja
      abierta={abierta}
      onCerrar={() => {
        accion.limpiar();
        onCerrar();
      }}
      titulo="Empezar de cero"
      bajada="La cuenta vuelve a tener solo USDC ficticios, sin monedas ni órdenes."
      cerrable={!accion.enCurso}
      pie={
        <div className="flex flex-wrap gap-3">
          <Boton
            variante="primario"
            disabled={!valido || accion.enCurso}
            onClick={() => {
              if (!valido) return;
              void accion.ejecutar(n.toFixed(2)).then((r) => {
                if (r) onCerrar();
              });
            }}
          >
            {accion.enCurso ? "Empezando…" : "Sí, empezar de cero"}
          </Boton>
          <Boton onClick={onCerrar} disabled={accion.enCurso}>
            Cancelar
          </Boton>
        </div>
      }
    >
      <div className="space-y-4">
        {cuenta ? (
          <p className="text-[0.9375rem] leading-relaxed text-tinta">
            Ahora tu cuenta vale <strong className="cifras font-semibold">{usdc(cuenta.valor_total)}</strong>
            {cuenta.posiciones.length ? `, con ${cuenta.posiciones.length} ${cuenta.posiciones.length === 1 ? "moneda" : "monedas"}` : ""}
            {cuenta.ordenes.length ? ` y ${cuenta.ordenes.length} ${cuenta.ordenes.length === 1 ? "orden pendiente" : "órdenes pendientes"}` : ""}. Al empezar de cero, todo eso se cierra y el historial se guarda aparte.
          </p>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <label htmlFor={id} className="text-[0.9375rem] font-medium text-tinta">
            Empezar con
          </label>
          <div className="relative max-w-xs">
            <input
              id={id}
              inputMode="decimal"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              aria-invalid={!valido || undefined}
              className="cifras min-h-12 w-full rounded-xl border border-linea-control/70 bg-superficie px-3.5 pr-16 text-base text-tinta aria-[invalid=true]:border-real"
            />
            <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-tinta-suave" aria-hidden="true">
              USDC
            </span>
          </div>
          <Nota>USDC ficticios. Puedes poner lo que vayas a invertir de verdad, para practicar con cifras parecidas.</Nota>
        </div>
        {accion.error ? <ErrorApiVista error={accion.error} /> : null}
      </div>
    </Hoja>
  );
}

type Lista = "posiciones" | "ordenes" | "historial";

/**
 * Posiciones, ordenes con limite (cancelables) e historial de la cuenta de practica.
 */
export function ListasCuenta({
  monedas,
  onVender,
  compacta = false,
  className,
}: {
  monedas: ReadonlyMap<string, MonedaVivo>;
  onVender: (coin: string) => void;
  /** En el movil, una ficha por fila en vez de una tabla ancha. */
  compacta?: boolean;
  className?: string;
}) {
  const cuenta = useVivo("cuenta");
  const almacen = useAlmacenVivo();
  const [lista, setLista] = useState<Lista>("posiciones");
  const idPanel = useId();
  const cancelar = useAccion(async (id: string) => {
    const c = await pedir(api.DELETE("/api/practica/ordenes/{orden_id}", { params: { path: { orden_id: id } } }));
    almacen.fijarYa("cuenta", c);
    return c;
  });

  const n = (x: unknown[] | undefined) => (x && x.length ? ` (${x.length})` : "");
  return (
    <section aria-label="Tus posiciones, órdenes e historial" className={clases("min-w-0 rounded-tarjeta border border-linea bg-superficie shadow-suave", className)}>
      <div className="px-2 pt-1 sm:px-3">
        <Pestanas
          etiqueta="Tu cuenta"
          idPanel={idPanel}
          actual={lista}
          onCambio={setLista}
          pestanas={[
            { clave: "posiciones", texto: `Lo que tienes${n(cuenta?.posiciones)}` },
            { clave: "ordenes", texto: `Órdenes con límite${n(cuenta?.ordenes)}` },
            { clave: "historial", texto: `Historial${n(cuenta?.historial)}` },
          ]}
        />
      </div>
      <div id={idPanel} role="tabpanel" aria-labelledby={`pestana-${lista}`} className={clases("relative", compacta ? undefined : "max-h-[22rem] overflow-auto")}>
        {!cuenta ? (
          <p className="px-4 py-6 text-sm text-tinta-suave">Cargando…</p>
        ) : compacta ? (
          <FichasCuenta cuenta={cuenta} lista={lista} monedas={monedas} onVender={onVender} cancelar={(id) => void cancelar.ejecutar(id)} cancelando={cancelar.enCurso} />
        ) : lista === "posiciones" ? (
          cuenta.posiciones.length ? (
            <table className="cifras w-full border-collapse text-sm">
              <caption className="sr-only">Lo que tienes en la cuenta de práctica, a precios de ahora</caption>
              <thead className="tabla-densa">
                <tr>
                  <Th className="pl-4">Moneda</Th>
                  <Th numerica>Tienes</Th>
                  <Th numerica>Te costó (precio medio)</Th>
                  <Th numerica>Precio ahora</Th>
                  <Th numerica>Vale</Th>
                  <Th numerica>Si vendieras ahora</Th>
                  <Th className="pr-4">
                    <span className="sr-only">Acciones</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {cuenta.posiciones.map((p) => {
                  const s = p.ganancia === null ? null : signoDecimal(p.ganancia);
                  const d = decPrecio(monedas, p.coin);
                  return (
                    <tr key={p.coin}>
                      <Td className="pl-4">
                        <span className="font-medium text-tinta">{p.nombre}</span> <span className="text-tinta-suave">{p.coin}</span>
                      </Td>
                      <Td numerica>{formatoCantidad(p.cantidad)}</Td>
                      <Td numerica>{formatoImporte(p.precio_medio, { decimales: d })}</Td>
                      <Td numerica>{formatoImporte(p.precio, { decimales: d })}</Td>
                      <Td numerica>{usdc(p.valor)}</Td>
                      <Td numerica className={clases("font-medium", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "text-tinta-suave")}>
                        {s === null ? "—" : `${s > 0 ? "Ganas" : s < 0 ? "Pierdes" : "Igual"} ${usdc(p.ganancia, true)}`}
                        {s ? <span className="block text-xs font-normal">{fraccionCoherente(p.ganancia_pct, s)}</span> : null}
                      </Td>
                      <Td className="pr-4 text-right">
                        <Boton tamano="compacto" onClick={() => onVender(p.coin)} aria-label={`Vender ${p.nombre}`}>
                          Vender
                        </Boton>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <Vacio>Aún no tienes ninguna moneda. Compra la que quieras con el boleto: es dinero ficticio.</Vacio>
          )
        ) : lista === "ordenes" ? (
          <>
            {cancelar.error ? <ErrorApiVista error={cancelar.error} className="m-3 text-sm" /> : null}
            {cuenta.ordenes.length ? (
              <table className="cifras w-full border-collapse text-sm">
                <caption className="sr-only">Órdenes con límite que esperan a que el precio llegue</caption>
                <thead className="tabla-densa">
                  <tr>
                    <Th className="pl-4">Moneda</Th>
                    <Th>Qué</Th>
                    <Th numerica>Cantidad</Th>
                    <Th numerica>Precio límite</Th>
                    <Th>Desde</Th>
                    <Th className="pr-4">
                      <span className="sr-only">Acciones</span>
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {cuenta.ordenes.map((o) => (
                    <tr key={o.id}>
                      <Td className="pl-4">
                        <span className="font-medium text-tinta">{o.nombre}</span> <span className="text-tinta-suave">{o.coin}</span>
                      </Td>
                      <Td className={o.lado === "compra" ? "text-sube-texto" : "text-baja-texto"}>{o.lado === "compra" ? "Comprar si baja a" : "Vender si sube a"}</Td>
                      <Td numerica>{formatoCantidad(o.cantidad)}</Td>
                      <Td numerica>{formatoImporte(o.precio_limite, { decimales: decPrecio(monedas, o.coin) })}</Td>
                      <Td>{momento(o.creada)}</Td>
                      <Td className="pr-4 text-right">
                        <Boton
                          tamano="compacto"
                          variante="peligro"
                          disabled={cancelar.enCurso}
                          onClick={() => void cancelar.ejecutar(o.id)}
                          aria-label={`Cancelar la orden de ${o.lado === "compra" ? "compra" : "venta"} de ${formatoCantidad(o.cantidad)} ${o.coin} a ${formatoImporte(o.precio_limite, { decimales: decPrecio(monedas, o.coin) })}`}
                        >
                          <X aria-hidden="true" className="h-4 w-4" />
                          Cancelar
                        </Boton>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Vacio>No tienes órdenes con límite esperando.</Vacio>
            )}
          </>
        ) : cuenta.historial.length ? (
          <table className="cifras w-full border-collapse text-sm">
            <caption className="sr-only">Lo que has comprado y vendido, lo más reciente primero</caption>
            <thead className="tabla-densa">
              <tr>
                <Th className="pl-4">Cuándo</Th>
                <Th>Qué</Th>
                <Th numerica>Cantidad</Th>
                <Th numerica>Precio</Th>
                <Th numerica>Importe</Th>
                <Th numerica className="pr-4">
                  Comisión
                </Th>
              </tr>
            </thead>
            <tbody>
              {cuenta.historial.map((e) => (
                <tr key={e.id}>
                  <Td className="pl-4">{momento(e.at)}</Td>
                  <Td>
                    <span className={clases("font-medium", e.lado === "compra" ? "text-sube-texto" : "text-baja-texto")}>{e.lado === "compra" ? "Compra" : "Venta"}</span>{" "}
                    <span className="text-tinta">{e.nombre}</span> <span className="text-tinta-suave">{e.tipo === "mercado" ? "a mercado" : "con límite"}</span>
                  </Td>
                  <Td numerica>
                    {formatoCantidad(e.cantidad)} {e.coin}
                  </Td>
                  <Td numerica>{formatoImporte(e.precio, { decimales: decPrecio(monedas, e.coin) })}</Td>
                  <Td numerica>{usdc(e.importe)}</Td>
                  <Td numerica className="pr-4">
                    {formatoImporte(e.comision, { decimales: 2 })}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Vacio>Aún no has comprado ni vendido nada.</Vacio>
        )}
      </div>
    </section>
  );
}

/** Las mismas listas en el movil: una ficha por fila, lo importante primero. */
function FichasCuenta({
  cuenta,
  lista,
  monedas,
  onVender,
  cancelar,
  cancelando,
}: {
  cuenta: CuentaPractica;
  lista: Lista;
  monedas: ReadonlyMap<string, MonedaVivo>;
  onVender: (coin: string) => void;
  cancelar: (id: string) => void;
  cancelando: boolean;
}) {
  if (lista === "posiciones") {
    if (!cuenta.posiciones.length) return <Vacio>Aún no tienes ninguna moneda. Compra la que quieras con el boleto: es dinero ficticio.</Vacio>;
    return (
      <ul className="divide-y divide-linea">
        {cuenta.posiciones.map((p) => {
          const s = p.ganancia === null ? null : signoDecimal(p.ganancia);
          const d = decPrecio(monedas, p.coin);
          return (
            <li key={p.coin} className="flex items-start gap-3 px-4 py-3">
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-semibold text-tinta">
                  {p.nombre} <span className="font-normal text-tinta-suave">{p.coin}</span>
                </p>
                <p className="cifras text-tinta">
                  Tienes {formatoCantidad(p.cantidad)} · valen {usdc(p.valor)}
                </p>
                <p className={clases("cifras font-medium", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "text-tinta-suave")}>
                  {s === null ? "—" : `${s > 0 ? "Ganas" : s < 0 ? "Pierdes" : "Igual"} ${usdc(p.ganancia, true)}${s ? ` (${fraccionCoherente(p.ganancia_pct, s)})` : ""}`}{" "}
                  <span className="font-normal text-tinta-suave">si vendieras ahora</span>
                </p>
                <p className="cifras text-xs text-tinta-suave">
                  Te costó a {formatoImporte(p.precio_medio, { decimales: d })} · ahora {formatoImporte(p.precio, { decimales: d })}
                </p>
              </div>
              <Boton tamano="compacto" onClick={() => onVender(p.coin)} aria-label={`Vender ${p.nombre}`}>
                Vender
              </Boton>
            </li>
          );
        })}
      </ul>
    );
  }
  if (lista === "ordenes") {
    if (!cuenta.ordenes.length) return <Vacio>No tienes órdenes con límite esperando.</Vacio>;
    return (
      <ul className="divide-y divide-linea">
        {cuenta.ordenes.map((o) => {
          const precio = formatoImporte(o.precio_limite, { decimales: decPrecio(monedas, o.coin) });
          return (
            <li key={o.id} className="flex items-start gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-tinta">
                  <span className={o.lado === "compra" ? "text-sube-texto" : "text-baja-texto"}>{o.lado === "compra" ? "Comprar" : "Vender"}</span>{" "}
                  <span className="cifras">{formatoCantidad(o.cantidad)}</span> {o.nombre}
                </p>
                <p className="cifras text-tinta">
                  si {o.lado === "compra" ? "baja" : "sube"} a {precio} USDC
                </p>
                <p className="text-xs text-tinta-suave">Desde el {momento(o.creada)}</p>
              </div>
              <Boton
                tamano="compacto"
                variante="peligro"
                disabled={cancelando}
                onClick={() => cancelar(o.id)}
                aria-label={`Cancelar la orden de ${o.lado === "compra" ? "compra" : "venta"} de ${formatoCantidad(o.cantidad)} ${o.coin} a ${precio}`}
              >
                Cancelar
              </Boton>
            </li>
          );
        })}
      </ul>
    );
  }
  if (!cuenta.historial.length) return <Vacio>Aún no has comprado ni vendido nada.</Vacio>;
  return (
    <ul className="divide-y divide-linea">
      {cuenta.historial.map((e) => (
        <li key={e.id} className="px-4 py-3 text-sm">
          <p className="text-tinta">
            <span className={clases("font-semibold", e.lado === "compra" ? "text-sube-texto" : "text-baja-texto")}>{e.lado === "compra" ? "Compraste" : "Vendiste"}</span>{" "}
            <span className="cifras">{formatoCantidad(e.cantidad)}</span> {e.nombre} a <span className="cifras">{formatoImporte(e.precio, { decimales: decPrecio(monedas, e.coin) })}</span>
          </p>
          <p className="cifras text-xs text-tinta-suave">
            {momento(e.at)} · {e.tipo === "mercado" ? "a mercado" : "con límite"} · {usdc(e.importe)} · comisión {formatoImporte(e.comision, { decimales: 2 })}
          </p>
        </li>
      ))}
    </ul>
  );
}

function Vacio({ children }: { children: ReactNode }) {
  return <p className="px-4 py-6 text-[0.9375rem] text-tinta-suave">{children}</p>;
}
