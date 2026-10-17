"use client";

import { ArrowDownLeft, ArrowUpRight, Banknote, NotebookPen, Plus, Sprout } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, pedir } from "@/api/cliente";
import type { Movimiento, NuevoMovimiento, PosicionAbierta, PosicionRetirada } from "@/api/tipos";
import { EstadoVacio } from "@/componentes/EstadoVacio";
import { Hoja } from "@/componentes/Hoja";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  Boton,
  BotonEnlace,
  CampoTexto,
  Chip,
  Codigo,
  Desplegable,
  Encabezado,
  ErrorApiVista,
  Esqueleto,
  Nota,
  Selector,
  Tarjeta,
  TextoApi,
  clases,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useModo } from "@/contexto/modo";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoCantidad, signoDecimal } from "@/lib/decimal";
import { euros, fecha, fechaCorta, hoyLocal, mesYAnioCorto, momento } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";
import { base, nombreLlano, unidad } from "@/lib/nombres";

import { Proteccion } from "./Proteccion";

type TipoMovimiento = NuevoMovimiento["tipo"];

function cuanto(p: PosicionAbierta): string {
  const u = unidad(p.activo);
  return `${formatoCantidad(p.cantidad)} ${u === "participaciones" ? (p.cantidad === "1" ? "participación" : "participaciones") : u}`;
}

function FilaTienes({ p }: { p: PosicionAbierta }) {
  const s = p.pnl_no_realizado === null ? null : signoDecimal(p.pnl_no_realizado);
  return (
    <li className="grid gap-1 py-4 sm:grid-cols-[1fr_auto] sm:items-baseline sm:gap-6">
      <div className="min-w-0">
        <p className="font-semibold text-tinta">{nombreLlano(p.activo)}</p>
        <p className="cifras text-[0.9375rem] text-tinta-suave">
          Tienes {cuanto(p)} · pusiste {euros(p.invertido)}
        </p>
      </div>
      <div className="sm:text-right">
        <p className="cifras text-lg font-semibold text-tinta">{p.valor === null ? "Sin precio" : `Valen ${euros(p.valor)}`}</p>
        {p.pnl_no_realizado !== null ? (
          <p className={clases("cifras text-[0.9375rem]", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "text-tinta-suave")}>
            {s === 1 ? "Ganas " : s === -1 ? "Pierdes " : ""}
            {euros(p.pnl_no_realizado, { conSigno: true })} si vendieras hoy
          </p>
        ) : null}
        <p className="text-sm text-tinta-suave">
          {p.precio_fecha ? `Precio del cierre del ${fechaCorta(p.precio_fecha)}` : "Sin precio descargado: no se puede saber cuánto vale"}
        </p>
      </div>
    </li>
  );
}

function FilaVendido({ r }: { r: PosicionRetirada }) {
  const s = signoDecimal(r.pnl_realizado);
  const palabra = s === 1 ? "Ganaste" : s === -1 ? "Perdiste" : "Ni ganaste ni perdiste";
  const importe = s === -1 ? r.pnl_realizado.replace(/^-/, "") : r.pnl_realizado;
  return (
    <li className="flex items-baseline justify-between gap-4 py-3">
      <p className="text-[0.9375rem] text-tinta">
        <span className={clases("font-semibold", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "")}>
          {palabra}
          {s !== 0 ? <span className="cifras"> {euros(importe)}</span> : null}
        </span>{" "}
        con {nombreLlano(r.activo)}
      </p>
      <p className="shrink-0 text-sm text-tinta-suave">
        {mesYAnioCorto(r.abierta)} – {mesYAnioCorto(r.retirada)}
      </p>
    </li>
  );
}

const ICONO_MOVIMIENTO = { compra: ArrowDownLeft, venta: ArrowUpRight, ingreso: Banknote, retirada: Banknote } as const;
const TEXTO_MOVIMIENTO = { compra: "Compra", venta: "Venta", ingreso: "Ingreso", retirada: "Retirada" } as const;

function FilaMovimiento({ m }: { m: Movimiento }) {
  const Icono = ICONO_MOVIMIENTO[m.tipo];
  const conActivo = m.tipo === "compra" || m.tipo === "venta";
  return (
    <li className="flex items-center gap-4 py-3">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-superficie-2 text-tinta-suave" aria-hidden="true">
        <Icono className="h-4 w-4" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[0.9375rem] text-tinta">
          <span className="font-semibold">{TEXTO_MOVIMIENTO[m.tipo]}</span>
          {conActivo && m.activo ? ` de ${m.activo}` : ""}
        </p>
        <p className="cifras truncate text-sm text-tinta-suave">
          {fecha(m.fecha)}
          {conActivo ? ` · ${formatoCantidad(m.cantidad)} ${m.simbolo?.includes("/") ? base(m.simbolo) : "part."} a ${euros(m.precio)}` : ""}
          {m.origen === "panel" ? " · desde el panel" : m.origen === "plan" ? " · de tu plan" : ""}
        </p>
      </div>
      <p className="cifras shrink-0 text-right font-semibold text-tinta">{euros(m.importe)}</p>
    </li>
  );
}

/** Anotar un movimiento: escribe en tu registro lo que ya hiciste. NO envia ninguna orden. */
function HojaAnotar({ abierta, onCerrar, alAnotar }: { abierta: boolean; onCerrar: () => void; alAnotar: () => void }) {
  return (
    <Hoja abierta={abierta} onCerrar={onCerrar} titulo="Anotar un movimiento" bajada="Para lo que hiciste fuera del panel. Esto NO envía nada: solo lo apunta.">
      {abierta ? <FormularioAnotar alAnotar={alAnotar} onCerrar={onCerrar} /> : null}
    </Hoja>
  );
}

function FormularioAnotar({ alAnotar, onCerrar }: { alAnotar: () => void; onCerrar: () => void }) {
  const [tipo, setTipo] = useState<TipoMovimiento>("compra");
  const [simbolo, setSimbolo] = useState("");
  const [dia, setDia] = useState(hoyLocal);
  const [cantidad, setCantidad] = useState("");
  const [precio, setPrecio] = useState("");
  const [comision, setComision] = useState("0");
  const conActivo = tipo === "compra" || tipo === "venta";

  const registrar = useAccion(async (movimiento: NuevoMovimiento) => {
    const r = await pedir(api.POST("/api/cartera/movimientos", { body: movimiento }));
    alAnotar();
    return r;
  });

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    void registrar.ejecutar({
      tipo,
      fecha: dia,
      cantidad: leerImporte(cantidad) ?? cantidad.trim(),
      comision: leerImporte(comision === "" ? "0" : comision) ?? comision.trim(),
      ...(conActivo ? { simbolo: simbolo.trim().toUpperCase(), precio: leerImporte(precio) ?? precio.trim() } : {}),
    });
  };

  if (registrar.resultado) {
    return (
      <div className="space-y-6">
        <Aviso tipo="hecho" vivo titulo="Anotado">
          Queda en tu registro (movimiento <Codigo>{registrar.resultado.activity_id}</Codigo>). No se ha enviado ninguna orden.
        </Aviso>
        <Boton variante="primario" className="w-full" onClick={onCerrar}>
          Hecho
        </Boton>
      </div>
    );
  }

  return (
    <form onSubmit={enviar} className="space-y-5">
      <Selector etiqueta="Qué hiciste" value={tipo} onChange={(e) => setTipo(e.target.value as TipoMovimiento)}>
        <option value="compra">Compré algo</option>
        <option value="venta">Vendí algo</option>
        <option value="deposito">Ingresé dinero</option>
        <option value="retirada">Retiré dinero</option>
      </Selector>
      {conActivo ? (
        <CampoTexto
          etiqueta="Qué (símbolo)"
          ayuda="Como aparece en tu bróker o en Binance: SPY, GLD, BTC/USDT…"
          placeholder="GLD"
          value={simbolo}
          onChange={(e) => setSimbolo(e.target.value)}
          required
        />
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto
          etiqueta={conActivo ? "Cantidad" : "Importe"}
          sufijo={conActivo ? undefined : "€"}
          value={cantidad}
          onChange={(e) => setCantidad(e.target.value)}
          inputMode="decimal"
          required
        />
        {conActivo ? (
          <CampoTexto etiqueta="Precio por unidad" sufijo="€" value={precio} onChange={(e) => setPrecio(e.target.value)} inputMode="decimal" required />
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto etiqueta="Comisión" sufijo="€" value={comision} onChange={(e) => setComision(e.target.value)} inputMode="decimal" />
        <CampoTexto etiqueta="Fecha" type="date" value={dia} onChange={(e) => setDia(e.target.value)} required />
      </div>
      {registrar.error ? <ErrorApiVista error={registrar.error} prefijo="No se anotó:" /> : null}
      <Boton type="submit" variante="primario" className="w-full" disabled={registrar.enCurso}>
        {registrar.enCurso ? "Anotando…" : "Anotar en mi registro"}
      </Boton>
    </form>
  );
}

function OrdenesEnviadas({ version }: { version: number }) {
  const consulta = useConsulta(`ordenes:${version}`, () => pedir(api.GET("/api/ordenes")));
  const o = consulta.datos;
  return (
    <div className="space-y-3">
      <Nota>Lo que de verdad salió a Binance, con el modo de cada orden a la vista. La cartera dice qué tienes; esto, qué mandaste.</Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!o && consulta.cargando ? <Esqueleto className="h-24" /> : null}
      {o && o.total === 0 ? <p className="text-[0.9375rem] text-tinta-suave">Ninguna orden enviada todavía.</p> : null}
      {o && o.total > 0 ? (
        <>
          <MarcoTabla etiqueta="Órdenes enviadas, la más reciente primero" altoMaximo={420}>
            <thead>
              <tr>
                <Th>cuándo</Th>
                <Th>modo</Th>
                <Th>qué</Th>
                <Th numerica>pedida</Th>
                <Th numerica>hecha</Th>
                <Th numerica>precio</Th>
                <Th>estado</Th>
              </tr>
            </thead>
            <tbody>
              {o.filas.map((f, i) => (
                <tr key={`${f.cuando}-${i}`}>
                  <Td>{momento(f.cuando)}</Td>
                  <Td className={f.modo.toUpperCase() === "REAL" ? "font-bold text-real-tinta" : undefined}>
                    {f.modo.toUpperCase() === "REAL" ? "dinero real" : f.modo}
                  </Td>
                  <Td className="font-medium">
                    {f.lado === "buy" ? "Compra" : "Venta"} de {nombreLlano(f.activo)}
                  </Td>
                  <Td numerica>{formatoCantidad(f.pedida)}</Td>
                  <Td numerica>{formatoCantidad(f.ejecutada)}</Td>
                  <Td numerica>{f.precio === null ? "—" : formatoCantidad(f.precio)}</Td>
                  <Td>
                    {{ filled: "hecha", partial: "en parte", rejected: "rechazada", unknown: "desconocido" }[f.estado] ?? f.estado}
                  </Td>
                </tr>
              ))}
            </tbody>
          </MarcoTabla>
          <Nota>
            {o.total} orden(es) · <strong className="text-tinta">{o.reales} con dinero real</strong> · registro en <Codigo>{o.registro}</Codigo>
          </Nota>
          {o.atencion.map((a) => (
            <Aviso key={a} tipo={a.includes("DESCONOCIDO") ? "critico" : "aviso"}>
              <TextoApi texto={a} />
            </Aviso>
          ))}
        </>
      ) : null}
    </div>
  );
}

/** Cartera: ¿que tengo? (docs/panel-v2.md, 4.4). La del modo activo, con sus fechas. */
export function Cartera() {
  const [version, setVersion] = useState(0);
  const { versionDatos, refrescarDatos } = useEstado();
  const { modo } = useModo();
  const [anotar, setAnotar] = useState(false);
  const clave = `${version}:${versionDatos}:${modo ?? "?"}`;
  const cartera = useConsulta(`cartera:${clave}`, () => pedir(api.GET("/api/cartera")));
  const movs = useConsulta(`movimientos:${clave}`, () => pedir(api.GET("/api/cartera/movimientos")));
  const c = cartera.datos;
  const ficticio = movs.datos?.cartera === "pruebas" || modo === "pruebas";
  const recargar = () => {
    setVersion((v) => v + 1);
    refrescarDatos();
  };

  return (
    <div>
      <Encabezado
        titulo="Cartera"
        bajada="Lo que tienes, lo que vendiste y todos tus movimientos."
        accion={
          <Boton variante="secundario" onClick={() => setAnotar(true)}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            Anotar un movimiento
          </Boton>
        }
      />
      {ficticio ? (
        <Aviso tipo="aviso" className="mb-6" titulo="Dinero ficticio">
          Estás en modo pruebas: esta es tu cartera de la red de pruebas de Binance, no la de verdad.
        </Aviso>
      ) : null}

      <div className="space-y-12">
        <section aria-labelledby="tienes-titulo" className="space-y-4">
          <h2 id="tienes-titulo" className="titular text-2xl font-semibold text-tinta">
            Lo que tienes
          </h2>
          {cartera.error ? <ErrorApiVista error={cartera.error} reintentar={cartera.recargar} /> : null}
          {!c && cartera.cargando ? <Esqueleto className="h-48" /> : null}
          {c?.error ? (
            <Aviso tipo="critico" titulo="Tu registro cuenta una historia imposible">
              <TextoApi texto={c.error} />
            </Aviso>
          ) : null}
          {c?.avisos.map((a) => (
            <Aviso key={a} tipo="aviso">
              <TextoApi texto={a} />
            </Aviso>
          ))}
          {c && !c.error && c.vacia ? (
            <EstadoVacio
              icono={Sprout}
              tono="neutro"
              titulo="Aún no tienes nada"
              accion={
                <BotonEnlace href="/invertir/" variante="primario">
                  Ver qué toca hacer
                </BotonEnlace>
              }
            >
              Cuando compres algo desde Invertir o anotes una compra, aparecerá aquí con lo que vale.
            </EstadoVacio>
          ) : null}
          {c && !c.error && c.abiertas.length ? (
            <Tarjeta className={clases("px-5 sm:px-6", cartera.cargando && "opacity-70")}>
              <ul className="divide-y divide-linea">
                {c.abiertas.map((p) => (
                  <FilaTienes key={p.activo} p={p} />
                ))}
              </ul>
              <div className="flex flex-wrap items-baseline justify-between gap-3 border-t border-linea py-4">
                <p className="text-[0.9375rem] text-tinta-suave">En total</p>
                <p className="cifras text-right text-[0.9375rem] text-tinta">
                  {c.valor_total === null ? (
                    "No se puede sumar: falta algún precio"
                  ) : (
                    <>
                      Valen <strong className="font-semibold">{euros(c.valor_total)}</strong> · pusiste {euros(c.invertido_abiertas)}
                    </>
                  )}
                </p>
              </div>
            </Tarjeta>
          ) : null}
        </section>

        {c && c.retiradas.length ? (
          <section aria-labelledby="vendiste-titulo" className="space-y-4">
            <h2 id="vendiste-titulo" className="titular text-2xl font-semibold text-tinta">
              Lo que ya vendiste
            </h2>
            <Tarjeta className="px-5 sm:px-6">
              <ul className="divide-y divide-linea">
                {c.retiradas.map((r) => (
                  <FilaVendido key={`${r.activo}-${r.abierta}-${r.retirada}`} r={r} />
                ))}
              </ul>
            </Tarjeta>
            <Nota>Esto ya es un hecho: no cambia con los precios.</Nota>
          </section>
        ) : null}

        <section aria-labelledby="movimientos-titulo" className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="movimientos-titulo" className="titular text-2xl font-semibold text-tinta">
              Movimientos
            </h2>
            {ficticio ? <Chip tono="pruebas">dinero ficticio</Chip> : null}
          </div>
          {movs.error ? <ErrorApiVista error={movs.error} reintentar={movs.recargar} /> : null}
          {!movs.datos && movs.cargando ? <Esqueleto className="h-40" /> : null}
          {movs.datos && movs.datos.movimientos.length === 0 ? (
            <EstadoVacio icono={NotebookPen} tono="neutro" titulo="Tu registro está vacío">
              Cada compra, venta, ingreso o retirada que hagas o anotes quedará aquí, con su fecha.
            </EstadoVacio>
          ) : null}
          {movs.datos && movs.datos.movimientos.length ? (
            <Tarjeta className="px-5 sm:px-6">
              <ul className="divide-y divide-linea">
                {movs.datos.movimientos.map((m) => (
                  <FilaMovimiento key={m.id} m={m} />
                ))}
              </ul>
            </Tarjeta>
          ) : null}
        </section>

        <Proteccion simbolos={c?.abiertas.map((p) => p.activo) ?? []} />

        <Desplegable resumen="Órdenes enviadas a Binance">
          <OrdenesEnviadas version={version} />
        </Desplegable>
      </div>

      <HojaAnotar abierta={anotar} onCerrar={() => setAnotar(false)} alAnotar={recargar} />
    </div>
  );
}

