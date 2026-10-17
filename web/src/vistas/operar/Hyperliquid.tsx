"use client";

import { CircleAlert, Plug, ShieldCheck, Wallet, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { EstadoExchange, EstadoOperarReal, MonedaVivo, ResultadoOrdenReal } from "@/api/tipos";
import { useVivo } from "@/api/vivo";
import { ConfirmacionTecleada, type EstadoTecleo } from "@/componentes/ConfirmacionTecleada";
import { Hoja } from "@/componentes/Hoja";
import { Aviso, Boton, BotonEnlace, Chip, ErrorApiVista, Esqueleto, Segmentado, Tarjeta, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoCantidad } from "@/lib/decimal";
import { momento } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";
import { extremos, precioFijo } from "@/lib/vivo";

const EXCHANGE = "hyperliquid";
const CADA_MS = 10_000;

/** El estado de Hyperliquid en Conexiones: sin conectar, en su red de pruebas o con dinero real. */
export function useHyperliquid() {
  const conexiones = useConsulta("conexiones:hyperliquid", () => pedir(api.GET("/api/conexiones")));
  const estado: EstadoExchange | null = conexiones.datos?.exchanges.find((e) => e.id === EXCHANGE) ?? null;
  return { conexiones, estado };
}

/**
 * Lo que va en el sitio del boleto en la pestaña Hyperliquid mientras no está conectado: qué hace
 * falta para operar de verdad y adónde ir. Nada se envía sin conexión.
 */
export function SinConectarHyperliquid({ queFalta = [] }: { queFalta?: readonly string[] }) {
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
      {queFalta.length ? (
        <ul className="list-disc space-y-1 pl-5 text-sm text-tinta-suave">
          {queFalta.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      ) : null}
      <BotonEnlace href="/conexiones/" variante="primario" className="w-full">
        Conectar Hyperliquid
      </BotonEnlace>
      <p className="text-sm text-tinta-suave">Mientras, la gráfica, el libro y tus bots se ven igual: los precios son los de Hyperliquid de verdad.</p>
    </Tarjeta>
  );
}

// -- Cuentas con decimales sin pasar por float para lo que se envía --------------------------------

/** Los decimales de un paso ("0.01" → 2). */
function decimalesDe(paso: string | null | undefined): number {
  if (!paso) return 8;
  const [, d = ""] = paso.split(".");
  return d.replace(/0+$/, "").length || (Number(paso) >= 1 ? 0 : d.length);
}

/** La cantidad al paso del mercado, hacia abajo (nunca de más), como texto decimal. */
function alPaso(cantidad: number, paso: string | null | undefined): string {
  const d = decimalesDe(paso);
  const p = paso ? Number(paso) : 10 ** -d;
  const n = Math.floor(cantidad / p + 1e-9) * p;
  return n > 0 ? n.toFixed(d) : "";
}

/** "0.50" → "0,5": como se enseña y se teclea. */
function aCastellano(texto: string): string {
  if (!texto) return "";
  const limpio = texto.includes(".") ? texto.replace(/0+$/, "").replace(/\.$/, "") : texto;
  return limpio.replace(".", ",");
}

function saldoDe(e: EstadoOperarReal, moneda: string | undefined): number {
  if (!moneda) return 0;
  return Number(e.saldo.find((s) => s.moneda.toUpperCase() === moneda.toUpperCase())?.cantidad ?? 0);
}

// -- El boleto real ---------------------------------------------------------------------------------

function BoletoReal({ e, moneda, onHecho }: { e: EstadoOperarReal; moneda: MonedaVivo; onHecho: () => void }) {
  const libro = useVivo("libro");
  const { medio } = extremos(libro && libro.coin === moneda.coin ? libro : null);
  const precioRef = medio ?? moneda.precio;
  const m = e.mercado;
  const [lado, setLado] = useState<"compra" | "venta">("compra");
  const [tipo, setTipo] = useState<"mercado" | "limite">("mercado");
  const [cantidadTexto, setCantidadTexto] = useState("");
  const [precioTexto, setPrecioTexto] = useState("");
  const [revisar, setRevisar] = useState(false);
  if (!m) return null;

  const real = e.red === "real";
  const precioLimite = tipo === "limite" ? Number(leerImporte(precioTexto) ?? NaN) : NaN;
  const precio = tipo === "limite" ? precioLimite : precioRef;
  const tecleada = Number(leerImporte(cantidadTexto) ?? NaN);
  const cantidad = Number.isFinite(tecleada) ? alPaso(tecleada, m.paso_cantidad) : "";
  const importe = cantidad && Number.isFinite(precio) ? Number(cantidad) * precio : null;
  const comision = importe !== null ? importe * Number(m.comision_tomador ?? 0) : null;
  const libreCotizada = saldoDe(e, m.cotizada);
  const libreBase = saldoDe(e, m.base);

  const problema = (() => {
    if (!cantidad) return null;
    if (tipo === "limite" && !Number.isFinite(precioLimite)) return "Pon el precio de la orden límite.";
    if (m.minimo_importe && importe !== null && importe < Number(m.minimo_importe))
      return `El mínimo por orden es de ${formatoCantidad(m.minimo_importe)} ${m.cotizada}.`;
    if (lado === "compra" && importe !== null && importe + (comision ?? 0) > libreCotizada) return `No tienes tantos ${m.cotizada} libres.`;
    if (lado === "venta" && Number(cantidad) > libreBase) return `No tienes tanto ${m.base} libre.`;
    return null;
  })();

  const porcentaje = (p: number) => {
    const q = lado === "compra" ? (libreCotizada * p) / (precio * (1 + Number(m.comision_tomador ?? 0))) : libreBase * p;
    setCantidadTexto(aCastellano(alPaso(q, m.paso_cantidad)));
  };

  return (
    <Tarjeta className={clases("space-y-4 p-4", real && "border-real/50")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[0.9375rem] font-semibold text-tinta">Orden en {m.par}</h2>
        {real ? <Chip tono="real">Dinero real</Chip> : <Chip tono="pruebas">Red de pruebas</Chip>}
      </div>
      <Segmentado
        etiqueta="Comprar o vender"
        ocultarEtiqueta
        repartido
        opciones={[
          { valor: "compra", texto: "Comprar" },
          { valor: "venta", texto: "Vender" },
        ]}
        valor={lado}
        onCambio={setLado}
      />
      <Segmentado
        etiqueta="Tipo de orden"
        ocultarEtiqueta
        opciones={[
          { valor: "mercado", texto: "A mercado" },
          { valor: "limite", texto: "Con límite" },
        ]}
        valor={tipo}
        onCambio={setTipo}
      />
      {tipo === "limite" ? (
        <label className="block">
          <span className="text-sm font-medium text-tinta">Precio ({m.cotizada})</span>
          <input
            inputMode="decimal"
            value={precioTexto}
            onChange={(ev) => setPrecioTexto(ev.target.value)}
            placeholder={precioFijo(precioRef, 2)}
            className="mt-1 min-h-11 w-full rounded-xl border border-linea-control/60 bg-superficie px-3 text-right text-base text-tinta"
          />
        </label>
      ) : null}
      <label className="block">
        <span className="text-sm font-medium text-tinta">Cantidad ({m.base})</span>
        <input
          inputMode="decimal"
          value={cantidadTexto}
          onChange={(ev) => setCantidadTexto(ev.target.value)}
          placeholder="0"
          className="mt-1 min-h-11 w-full rounded-xl border border-linea-control/60 bg-superficie px-3 text-right text-base text-tinta"
        />
      </label>
      <div className="grid grid-cols-4 gap-2">
        {[0.25, 0.5, 0.75, 1].map((p) => (
          <button key={p} type="button" onClick={() => porcentaje(p)} className="min-h-10 rounded-xl border border-linea text-sm font-medium text-tinta hover:bg-superficie-2">
            {p * 100} %
          </button>
        ))}
      </div>
      <p className="text-sm text-tinta-suave">
        Tienes {formatoCantidad(String(libreCotizada))} {m.cotizada} y {formatoCantidad(String(libreBase))} {m.base} libres.
      </p>
      {cantidad ? (
        <p className="rounded-xl bg-superficie-2 px-3 py-2 text-sm text-tinta">
          {lado === "compra" ? "Comprarías" : "Venderías"} <strong className="cifras">{aCastellano(cantidad)} {m.base}</strong>
          {importe !== null ? (
            <>
              {" "}
              por unos <strong className="cifras">{precioFijo(importe, 2)} {m.cotizada}</strong>
              {comision !== null ? ` (comisión ~${precioFijo(comision, 2)})` : ""}
            </>
          ) : null}
          {tipo === "mercado" ? ". A mercado, el precio final puede moverse un poco." : "."}
        </p>
      ) : null}
      {problema ? <p className="text-sm font-medium text-baja-texto">{problema}</p> : null}
      <Boton variante={real ? "real" : "primario"} className="w-full" disabled={!cantidad || problema !== null} onClick={() => setRevisar(true)}>
        Revisar la orden
      </Boton>
      {revisar && cantidad ? (
        <HojaOrdenReal
          e={e}
          lado={lado}
          tipo={tipo}
          cantidad={cantidad}
          precio={tipo === "limite" ? (leerImporte(precioTexto) ?? undefined) : undefined}
          importe={importe}
          onCerrar={(enviada) => {
            setRevisar(false);
            // Lo enviado ya no se repite por descuido: el boleto vuelve a quedar en blanco.
            if (enviada) setCantidadTexto("");
          }}
          onHecho={onHecho}
        />
      ) : null}
    </Tarjeta>
  );
}

function HojaOrdenReal({
  e,
  lado,
  tipo,
  cantidad,
  precio,
  importe,
  onCerrar,
  onHecho,
}: {
  e: EstadoOperarReal;
  lado: "compra" | "venta";
  tipo: "mercado" | "limite";
  cantidad: string;
  precio: string | undefined;
  importe: number | null;
  /** `enviada`: si la orden salió (para dejar el boleto en blanco). */
  onCerrar: (enviada: boolean) => void;
  onHecho: () => void;
}) {
  const m = e.mercado;
  const real = e.red === "real";
  const [escrito, setEscrito] = useState("");
  const enviar = useAccion(async () => {
    const r = await pedir(
      api.POST("/api/operar/{exchange}/ordenes", {
        params: { path: { exchange: EXCHANGE } },
        body: { coin: e.coin, lado, tipo, cantidad, precio: precio ?? null, red: e.red ?? "pruebas", escrito },
      }),
    );
    onHecho();
    return r;
  });
  if (!m) return null;
  const esperado = aCastellano(cantidad);
  const tecleado = leerImporte(escrito);
  const estado: EstadoTecleo =
    escrito.trim() === ""
      ? { tipo: "vacio" }
      : tecleado !== null && Number(tecleado) === Number(cantidad)
        ? { tipo: "puede" }
        : { tipo: "no", motivo: `Escribe ${esperado}, la cantidad de la orden.` };
  const hecho: ResultadoOrdenReal | null = enviar.resultado;

  return (
    <Hoja
      abierta
      onCerrar={() => onCerrar(hecho !== null)}
      cerrable={!enviar.enCurso}
      titulo={hecho ? "Orden enviada" : `${lado === "compra" ? "Comprar" : "Vender"} ${esperado} ${m.base} ${real ? "con dinero real" : "en la red de pruebas"}`}
      bajada={real ? "Esto mueve tu dinero en Hyperliquid. Revisa la cantidad antes de teclearla." : "Red de pruebas de Hyperliquid: dinero de pruebas, órdenes de verdad."}
      pie={
        hecho ? (
          <Boton onClick={() => onCerrar(true)}>Cerrar</Boton>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Boton variante={real ? "real" : "primario"} disabled={estado.tipo !== "puede" || enviar.enCurso} onClick={() => void enviar.ejecutar()}>
              {enviar.enCurso ? "Enviando…" : real ? "Enviar con dinero real" : "Enviar a la red de pruebas"}
            </Boton>
            <Boton onClick={() => onCerrar(false)} disabled={enviar.enCurso}>
              Cancelar
            </Boton>
          </div>
        )
      }
    >
      <div className="space-y-4 text-[0.9375rem] leading-relaxed text-tinta">
        {hecho ? (
          <Aviso tipo={hecho.estado === "desconocido" || hecho.estado === "rechazada" ? "critico" : "hecho"} vivo>
            {hecho.texto}
          </Aviso>
        ) : (
          <>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl bg-superficie-2 p-4">
              <dt className="text-tinta-suave">Dónde</dt>
              <dd className="font-medium">
                Hyperliquid · {m.par} · {real ? "dinero real" : "red de pruebas"}
              </dd>
              <dt className="text-tinta-suave">Qué</dt>
              <dd className="font-medium">
                {lado === "compra" ? "Comprar" : "Vender"} {esperado} {m.base} {tipo === "mercado" ? "a mercado" : `a ${precio?.replace(".", ",")} ${m.cotizada} (límite)`}
              </dd>
              {importe !== null ? (
                <>
                  <dt className="text-tinta-suave">Aproximado</dt>
                  <dd className="cifras font-medium">
                    {precioFijo(importe, 2)} {m.cotizada}
                  </dd>
                </>
              ) : null}
            </dl>
            <ConfirmacionTecleada
              esperado={esperado}
              valor={escrito}
              onCambio={setEscrito}
              estado={estado}
              tono={real ? "real" : "normal"}
              ayuda="Se escribe la cantidad, no un «sí»: obliga a mirar lo que se va a mover. Pegar está desactivado."
            />
          </>
        )}
        {enviar.error ? <ErrorApiVista error={enviar.error} /> : null}
      </div>
    </Hoja>
  );
}

// -- Tu cuenta en Hyperliquid ------------------------------------------------------------------------

function CuentaReal({ e, onCambio }: { e: EstadoOperarReal; onCambio: () => void }) {
  const cancelar = useAccion(async (id: string) => {
    const r = await pedir(api.DELETE("/api/operar/{exchange}/ordenes/{id_cliente}", { params: { path: { exchange: EXCHANGE, id_cliente: id }, query: { coin: e.coin } } }));
    onCambio();
    return r;
  });
  return (
    <Tarjeta className="space-y-3 p-4">
      <h2 className="text-[0.9375rem] font-semibold text-tinta">Tu cuenta en Hyperliquid{e.red === "pruebas" ? " (red de pruebas)" : ""}</h2>
      {e.saldo.length ? (
        <ul className="divide-y divide-linea text-sm">
          {e.saldo.map((s) => (
            <li key={s.moneda} className="flex items-baseline justify-between py-1.5">
              <span className="text-tinta">{s.moneda}</span>
              <span className="cifras font-medium text-tinta">{formatoCantidad(s.cantidad)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-tinta-suave">Sin saldo{e.red === "pruebas" ? ": pide USDC de pruebas en la web de Hyperliquid (red de pruebas)." : "."}</p>
      )}
      <h3 className="pt-1 text-sm font-semibold text-tinta">Órdenes abiertas</h3>
      {e.ordenes_abiertas.length ? (
        <ul className="space-y-2 text-sm">
          {e.ordenes_abiertas.map((o) => (
            <li key={o.id_cliente} className="flex items-start justify-between gap-2 rounded-xl border border-linea px-3 py-2">
              <span className="text-tinta">
                {o.lado === "compra" ? "Comprar" : "Vender"} {formatoCantidad(o.cantidad)} {o.par.split("/")[0]}
                {o.precio ? ` a ${formatoCantidad(o.precio)}` : ""}
                <span className="block text-xs text-tinta-suave">{momento(o.at)}</span>
              </span>
              <Boton tamano="compacto" variante="fantasma" disabled={cancelar.enCurso} onClick={() => void cancelar.ejecutar(o.id_cliente)}>
                <X aria-hidden="true" className="h-4 w-4" />
                Cancelar
              </Boton>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-tinta-suave">Ninguna.</p>
      )}
      {cancelar.resultado ? <Aviso tipo="hecho">{cancelar.resultado.texto}</Aviso> : null}
      {cancelar.error ? <ErrorApiVista error={cancelar.error} /> : null}
    </Tarjeta>
  );
}

/**
 * El sitio del boleto en la pestaña Hyperliquid (docs/panel-v5.md): sin conectar, qué falta; con
 * Hyperliquid conectado, el boleto de verdad (red de pruebas o dinero real, la activa en
 * Conexiones) y tu cuenta. Se vuelve a preguntar cada 10 s y después de cada orden.
 */
export function PanelHyperliquid({ moneda }: { moneda: MonedaVivo | undefined }) {
  const coin = moneda?.coin ?? "BTC";
  const [vuelta, setVuelta] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => {
      if (!document.hidden) setVuelta((v) => v + 1);
    }, CADA_MS);
    return () => window.clearInterval(t);
  }, []);
  const estado = useConsulta(`operar-real:${coin}:${vuelta}`, () => pedir(api.GET("/api/operar/{exchange}", { params: { path: { exchange: EXCHANGE }, query: { coin } } })));
  const e = estado.datos;
  const recargar = () => setVuelta((v) => v + 1);

  if (estado.error && !e) return <ErrorApiVista error={estado.error} reintentar={estado.recargar} />;
  if (!e || !moneda) return <Esqueleto className="h-[26rem]" />;
  if (!e.conectado) return <SinConectarHyperliquid queFalta={e.que_falta} />;
  return (
    <div className="space-y-3">
      {e.aviso ? (
        <Aviso tipo="aviso">
          <CircleAlert aria-hidden="true" className="mr-1 inline h-4 w-4 align-[-3px]" />
          {e.aviso}
        </Aviso>
      ) : null}
      {e.mercado ? <BoletoReal key={coin} e={e} moneda={moneda} onHecho={recargar} /> : null}
      <CuentaReal e={e} onCambio={recargar} />
    </div>
  );
}
