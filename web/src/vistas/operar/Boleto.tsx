"use client";

import { useId, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { LadoPractica, MonedaVivo, NuevaOrdenPractica, ResultadoPractica, TipoOrden } from "@/api/tipos";
import { useAlmacenVivo, useConexionVivo, useVivo } from "@/api/vivo";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { Aviso, ErrorApiVista, Segmentado, clases } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { leerImporte } from "@/lib/importe";
import {
  COMISION_CREADOR,
  COMISION_TOMADOR,
  cantidadMoneda,
  decimalesPrecio,
  extremos,
  previaLimite,
  previaMercado,
  precioFijo,
  truncar,
  type Previa,
} from "@/lib/vivo";

/**
 * Lo tecleado, como numero, con las reglas de lib/importe.ts ("1.000" es mil, "12,50" doce con
 * cincuenta, "0.015" cero coma cero quince). `null` si no es un numero.
 */
export function leerNumero(texto: string): number | null {
  const limpio = leerImporte(texto.trim());
  if (limpio === null || limpio === "") return null;
  const n = Number(limpio);
  return Number.isFinite(n) ? n : null;
}

/** Un numero para un campo de texto, con coma decimal y sin separador de miles. */
function paraCampo(n: number, decimales: number): string {
  return truncar(n, decimales).toFixed(decimales).replace(/\.?0+$/, "").replace(".", ",");
}

const dosDec = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" });

export interface PresetBoleto {
  lado: LadoPractica;
  /** Vender todo lo que se tiene, por ejemplo. */
  porcentaje?: number;
}

/**
 * El boleto de compra y venta de la cuenta de practica (docs/panel-v3-vivo.md, seccion 2).
 * Antes de enviar dice que va a pasar, calculado con el libro que se ve ahora (aproximado: el
 * precio y la comision de verdad los pone la API al ejecutar). Es dinero ficticio: no se teclea
 * ninguna confirmacion.
 */
export function Boleto({ moneda, inicial, className }: { moneda: MonedaVivo; inicial?: PresetBoleto; className?: string }) {
  const coin = moneda.coin;
  const dec = moneda.decimales_cantidad;
  const decP = decimalesPrecio(moneda.precio, dec);
  const almacen = useAlmacenVivo();
  const libro = useVivo("libro");
  const cuenta = useVivo("cuenta");
  const libroVigente = libro && libro.coin === coin ? libro : null;
  // Sin precios de Hyperliquid no se opera: el libro que se ve esta viejo (la API diria que no).
  const sinPrecios = useConexionVivo().fuente?.conectado === false;
  const { compra: mejorCompra, venta: mejorVenta } = extremos(libroVigente);

  const [lado, setLado] = useState<LadoPractica>(inicial?.lado ?? "compra");
  const [tipo, setTipo] = useState<TipoOrden>("mercado");
  const [unidad, setUnidad] = useState<"usdc" | "moneda">(inicial?.lado === "venta" ? "moneda" : "usdc");
  const [cantidadTexto, setCantidadTexto] = useState(() => {
    // "Vender" desde una posicion: el boleto llega con todo lo que se tiene de esa moneda.
    if (inicial?.lado !== "venta" || !inicial.porcentaje) return "";
    const c = almacen.leer("cuenta");
    const tiene = Number(c?.posiciones.find((p) => p.coin === coin)?.cantidad ?? 0);
    const reservada = c?.ordenes.filter((o) => o.coin === coin && o.lado === "venta").reduce((s, o) => s + Number(o.cantidad), 0) ?? 0;
    const q = truncar(Math.max(0, tiene - reservada) * inicial.porcentaje, dec);
    return q > 0 ? paraCampo(q, dec) : "";
  });
  const [precioTexto, setPrecioTexto] = useState("");
  const idCantidad = useId();
  const idPrecio = useId();
  const idPrevia = useId();

  const enviar = useAccion(async (cuerpo: NuevaOrdenPractica): Promise<ResultadoPractica> => {
    const r = await pedir(api.POST("/api/practica/ordenes", { body: cuerpo }));
    almacen.fijarYa("cuenta", r.cuenta);
    return r;
  });

  // Lo disponible (aproximado: la API es la que dice si llega).
  const saldo = cuenta ? Number(cuenta.saldo) : 0;
  const posicion = cuenta?.posiciones.find((p) => p.coin === coin);
  const enOrdenesVenta = cuenta?.ordenes.filter((o) => o.coin === coin && o.lado === "venta").reduce((s, o) => s + Number(o.cantidad), 0) ?? 0;
  const tieneMoneda = Math.max(0, (posicion ? Number(posicion.cantidad) : 0) - enOrdenesVenta);

  const precioLimite = tipo === "limite" ? leerNumero(precioTexto) : null;
  const cantidadNum = leerNumero(cantidadTexto);
  const comisionTipo = tipo === "mercado" ? COMISION_TOMADOR : COMISION_CREADOR;

  // El precio de referencia para pasar de USDC a moneda (y al reves).
  const referencia = tipo === "limite" ? precioLimite : lado === "compra" ? mejorVenta : mejorCompra;

  let previa: Previa | null = null;
  if (cantidadNum !== null && cantidadNum > 0) {
    if (tipo === "mercado" && libroVigente) {
      previa = previaMercado(libroVigente, lado, unidad === "usdc" ? { importe: cantidadNum } : { cantidad: truncar(cantidadNum, dec) });
    } else if (tipo === "limite" && precioLimite) {
      const q = unidad === "moneda" ? truncar(cantidadNum, dec) : truncar(cantidadNum / precioLimite, dec);
      previa = previaLimite(q, precioLimite);
    }
  }

  const aporcentaje = (p: number) => {
    enviar.limpiar();
    if (lado === "compra") {
      const importe = (saldo * p) / (1 + comisionTipo);
      if (unidad === "usdc") setCantidadTexto(paraCampo(importe, 2));
      else if (tipo === "mercado" && libroVigente) {
        const pr = previaMercado(libroVigente, "compra", { importe });
        setCantidadTexto(pr ? paraCampo(pr.cantidad, dec) : "");
      } else if (referencia) setCantidadTexto(paraCampo(importe / referencia, dec));
    } else {
      const q = truncar(tieneMoneda * p, dec);
      if (unidad === "moneda") setCantidadTexto(paraCampo(q, dec));
      else if (referencia) setCantidadTexto(paraCampo(q * referencia, 2));
    }
  };

  // Lo que impide enviar, en llano.
  let impide: string | null = null;
  if (sinPrecios) impide = "Ahora no llegan precios de Hyperliquid: no se puede comprar ni vender hasta que vuelvan.";
  else if (cantidadTexto.trim() && (cantidadNum === null || cantidadNum <= 0)) impide = "Escribe una cantidad mayor que cero (por ejemplo 250 o 0,015).";
  else if (tipo === "limite" && precioTexto.trim() && (precioLimite === null || precioLimite <= 0)) impide = "Escribe un precio límite mayor que cero.";
  else if (previa && previa.cantidad <= 0) impide = `Es demasiado poco: ${coin} se compra en pasos de ${cantidadMoneda(10 ** -dec, dec)}.`;
  else if (previa && lado === "compra" && previa.importe + previa.comision > saldo + 1e-9)
    impide = `No te llega: costaría unos ${dosDec(previa.importe + previa.comision)} USDC y tienes ${dosDec(saldo)} USDC libres.`;
  else if (previa && lado === "venta" && previa.cantidad > tieneMoneda + 10 ** -(dec + 2))
    impide = tieneMoneda > 0 ? `Solo tienes ${cantidadMoneda(tieneMoneda, dec)} ${coin} para vender.` : `No tienes ${moneda.nombre} que vender.`;
  else if (previa?.insuficiente) impide = "El libro que se ve no tiene tanto: la orden no se podría hacer entera. Prueba con menos.";

  const puedeEnviar = previa !== null && impide === null && !enviar.enCurso && (tipo === "mercado" || precioLimite !== null);

  const alEnviar = () => {
    if (!previa || !puedeEnviar) return;
    const cuerpo: NuevaOrdenPractica =
      tipo === "mercado"
        ? unidad === "usdc" && cantidadNum !== null
          ? { coin, lado, tipo, importe: cantidadNum.toFixed(2) }
          : { coin, lado, tipo, cantidad: truncar(cantidadNum ?? 0, dec).toFixed(dec) }
        : { coin, lado, tipo, cantidad: previa.cantidad.toFixed(dec), precio_limite: (precioLimite ?? 0).toFixed(decP) };
    void enviar.ejecutar(cuerpo).then((r) => {
      if (r) setCantidadTexto("");
    });
  };

  const cambiarTipo = (t: TipoOrden) => {
    setTipo(t);
    enviar.limpiar();
    if (t === "limite" && !precioTexto) {
      const p = lado === "compra" ? mejorCompra : mejorVenta;
      if (p !== null) setPrecioTexto(p.toFixed(decP).replace(".", ","));
    }
  };

  const cruza = tipo === "limite" && precioLimite !== null && (lado === "compra" ? mejorVenta !== null && precioLimite >= mejorVenta : mejorCompra !== null && precioLimite <= mejorCompra);
  const etiquetaUnidad = unidad === "usdc" ? "USDC" : coin;

  return (
    <section aria-labelledby="titulo-boleto" className={clases("rounded-tarjeta border border-linea bg-superficie p-4 shadow-suave", className)}>
      <h2 id="titulo-boleto" className="sr-only">
        Comprar o vender {moneda.nombre}
      </h2>
      <fieldset>
        <legend className="sr-only">¿Comprar o vender?</legend>
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-superficie-2 p-1">
          {(["compra", "venta"] as const).map((l) => {
            const activo = lado === l;
            return (
              <label
                key={l}
                className={clases(
                  "flex min-h-11 cursor-pointer items-center justify-center rounded-lg text-[0.9375rem] font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco",
                  activo ? (l === "compra" ? "bg-sube text-marca-tinta shadow-sm" : "bg-baja text-marca-tinta shadow-sm") : "text-tinta-suave hover:text-tinta",
                )}
              >
                <input
                  type="radio"
                  name={`${idCantidad}-lado`}
                  className="sr-only"
                  checked={activo}
                  onChange={() => {
                    setLado(l);
                    setCantidadTexto("");
                    enviar.limpiar();
                    if (tipo === "limite") {
                      const p = l === "compra" ? mejorCompra : mejorVenta;
                      if (p !== null) setPrecioTexto(p.toFixed(decP).replace(".", ","));
                    }
                  }}
                />
                {l === "compra" ? "Comprar" : "Vender"}
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-2">
        <Segmentado
          etiqueta="Tipo de orden"
          ocultarEtiqueta
          opciones={[
            { valor: "mercado", texto: "A mercado" },
            { valor: "limite", texto: "Con límite" },
          ]}
          valor={tipo}
          onCambio={cambiarTipo}
          className="[&_label]:text-sm"
        />
        <QueEsEsto clave="tipo-orden" etiqueta="¿Cuál elijo?" className="[&>button]:text-xs" />
      </div>

      {tipo === "limite" ? (
        <div className="mt-3 flex flex-col gap-1.5">
          <label htmlFor={idPrecio} className="text-sm font-medium text-tinta">
            {lado === "compra" ? "Comprar si el precio baja a" : "Vender si el precio sube a"}
          </label>
          <div className="relative">
            <input
              id={idPrecio}
              inputMode="decimal"
              autoComplete="off"
              value={precioTexto}
              onChange={(e) => {
                setPrecioTexto(e.target.value);
                enviar.limpiar();
              }}
              className="cifras min-h-11 w-full rounded-xl border border-linea-control/70 bg-superficie px-3 pr-16 text-base text-tinta hover:border-linea-control"
            />
            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-tinta-suave" aria-hidden="true">
              USDC
            </span>
          </div>
          <p className="text-xs text-tinta-suave">
            Ahora: compran a <span className="cifras">{precioFijo(mejorCompra, decP)}</span> · venden a <span className="cifras">{precioFijo(mejorVenta, decP)}</span>
          </p>
        </div>
      ) : null}

      <div className="mt-3 flex flex-col gap-1.5">
        <div className="flex items-end justify-between gap-2">
          <label htmlFor={idCantidad} className="text-sm font-medium text-tinta">
            {lado === "compra" ? "Cuánto comprar" : "Cuánto vender"}
          </label>
          <Segmentado
            etiqueta="Cantidad en"
            ocultarEtiqueta
            opciones={[
              { valor: "usdc", texto: "USDC" },
              { valor: "moneda", texto: coin },
            ]}
            valor={unidad}
            onCambio={(u) => {
              setUnidad(u);
              setCantidadTexto("");
              enviar.limpiar();
            }}
            className="[&_label]:px-2.5 [&_label]:text-xs [&>div]:p-0.5"
          />
        </div>
        <div className="relative">
          <input
            id={idCantidad}
            inputMode="decimal"
            autoComplete="off"
            placeholder={unidad === "usdc" ? "250" : `0,${"0".repeat(Math.max(0, dec - 1))}1`}
            value={cantidadTexto}
            onChange={(e) => {
              setCantidadTexto(e.target.value);
              enviar.limpiar();
            }}
            aria-describedby={idPrevia}
            aria-invalid={impide && cantidadTexto ? true : undefined}
            className="cifras min-h-12 w-full rounded-xl border border-linea-control/70 bg-superficie px-3 pr-16 text-lg text-tinta placeholder:text-tinta-suave/60 hover:border-linea-control aria-[invalid=true]:border-real"
          />
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-tinta-suave" aria-hidden="true">
            {etiquetaUnidad}
          </span>
        </div>
        <div className="grid grid-cols-4 gap-1" role="group" aria-label={lado === "compra" ? "Parte de tu saldo" : `Parte de tus ${coin}`}>
          {[0.25, 0.5, 0.75, 1].map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => aporcentaje(p)}
              disabled={lado === "compra" ? saldo <= 0 : tieneMoneda <= 0}
              className="cifras min-h-11 rounded-lg border border-linea bg-superficie text-sm font-medium text-tinta hover:bg-superficie-2 disabled:opacity-45"
            >
              {p * 100} %
            </button>
          ))}
        </div>
        <p className="text-xs text-tinta-suave">
          {lado === "compra" ? (
            <>
              Tienes <span className="cifras font-medium text-tinta">{cuenta ? formatoImporte(cuenta.saldo) : "—"} USDC</span> libres
            </>
          ) : (
            <>
              Tienes <span className="cifras font-medium text-tinta">{cantidadMoneda(tieneMoneda, dec)} {coin}</span> para vender
            </>
          )}
        </p>
      </div>

      <div id={idPrevia} className="mt-3 min-h-[4.5rem] rounded-xl bg-superficie-2 px-3 py-2.5 text-sm leading-relaxed text-tinta" aria-live="polite">
        {impide ? (
          <p className="font-medium text-real-tinta">{impide}</p>
        ) : previa ? (
          <TextoPrevia previa={previa} lado={lado} tipo={tipo} coin={coin} dec={dec} decP={decP} cruza={cruza} />
        ) : (
          <p className="text-tinta-suave">
            Escribe cuánto {lado === "compra" ? "comprar" : "vender"} o elige un porcentaje: aquí verás qué va a pasar antes de enviarlo.
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={alEnviar}
        disabled={!puedeEnviar}
        className={clases(
          "mt-3 inline-flex min-h-12 w-full items-center justify-center rounded-xl text-[0.9375rem] font-semibold shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45",
          lado === "compra" ? "bg-sube text-marca-tinta hover:bg-sube/90" : "bg-baja text-marca-tinta hover:bg-baja/90",
        )}
      >
        {enviar.enCurso ? "Enviando…" : `${lado === "compra" ? "Comprar" : "Vender"} ${coin}${tipo === "limite" ? " con límite" : ""}`}
      </button>

      {enviar.resultado ? (
        <Aviso tipo="hecho" vivo className="mt-3 text-sm">
          {enviar.resultado.resumen}
        </Aviso>
      ) : null}
      {enviar.error ? <ErrorApiVista error={enviar.error} className="mt-3 text-sm" /> : null}
    </section>
  );
}

function TextoPrevia({
  previa,
  lado,
  tipo,
  coin,
  dec,
  decP,
  cruza,
}: {
  previa: Previa;
  lado: LadoPractica;
  tipo: TipoOrden;
  coin: string;
  dec: number;
  decP: number;
  cruza: boolean;
}) {
  const q = cantidadMoneda(previa.cantidad, dec);
  const fuerte = (t: string) => <strong className="cifras font-semibold">{t}</strong>;
  if (tipo === "mercado") {
    return (
      <>
        <p>
          {lado === "compra" ? (
            <>
              Comprarás unos {fuerte(`${q} ${coin}`)} por {fuerte(`${dosDec(previa.importe)} USDC`)}
            </>
          ) : (
            <>
              Venderás {fuerte(`${q} ${coin}`)} y cobrarás unos {fuerte(`${dosDec(previa.importe - previa.comision)} USDC`)}
            </>
          )}
          , a ~<span className="cifras">{precioFijo(previa.precioMedio, decP)}</span> de media.
        </p>
        <p className="text-tinta-suave">
          Comisión ~<span className="cifras">{dosDec(previa.comision)}</span> USDC{lado === "compra" ? ", que se suma" : ", ya descontada"}.
          {previa.niveles > 1 ? ` Se comerá ${previa.niveles} niveles del libro: cuanto más pides, peor precio.` : ""}
        </p>
      </>
    );
  }
  return (
    <>
      <p>
        {lado === "compra" ? (
          <>
            Si alguien vende a {fuerte(precioFijo(previa.precioMedio, decP))} o menos, comprarás {fuerte(`${q} ${coin}`)} por {fuerte(`${dosDec(previa.importe)} USDC`)}.
          </>
        ) : (
          <>
            Si alguien compra a {fuerte(precioFijo(previa.precioMedio, decP))} o más, venderás {fuerte(`${q} ${coin}`)} por {fuerte(`${dosDec(previa.importe)} USDC`)}.
          </>
        )}
      </p>
      <p className="text-tinta-suave">
        Comisión ~<span className="cifras">{dosDec(previa.comision)}</span> USDC.
        {lado === "compra" ? ` Hasta entonces se apartan ~${dosDec(previa.importe + previa.comision)} USDC de tu saldo.` : " Puede que no llegue nunca: puedes cancelarla."}
        {cruza ? " Tu precio ya alcanza al otro lado del libro: se ejecutará casi al momento." : ""}
      </p>
    </>
  );
}
