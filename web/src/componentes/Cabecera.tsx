"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { API_BASE, MODO_EJEMPLO } from "@/api/cliente";
import type { Modo } from "@/api/tipos";
import { useCostes } from "@/contexto/costes";
import { useEstado } from "@/contexto/estado";
import { useGuardado } from "@/lib/almacen";
import { fraccionComoPorcentaje } from "@/lib/decimal";

import { Aviso, Codigo, ErrorApiVista, TextoApi, clases } from "./ui";

/** Siete pestanas, una pregunta cada una, en el orden en que se usan. */
export const PESTANAS = [
  { ruta: "/mercado/", texto: "Mercado" },
  { ruta: "/cartera/", texto: "Mi cartera" },
  { ruta: "/simular/", texto: "Simular" },
  { ruta: "/vigilar/", texto: "Vigilar" },
  { ruta: "/estimado-vs-real/", texto: "Estimado vs real" },
  { ruta: "/investigacion/", texto: "Investigación" },
  { ruta: "/chat/", texto: "Chat" },
] as const;

const NOMBRES_MODO: Record<string, string> = {
  simulacion: "SIMULACIÓN",
  pruebas: "PRUEBAS",
  real: "REAL",
};

function nombreModo(modo: Modo): string {
  return NOMBRES_MODO[modo.nombre.toLowerCase()] ?? modo.nombre.toUpperCase();
}

function InsigniaModo() {
  const { estado, error } = useEstado();
  let texto = "MODO: leyendo…";
  let estilo = "border-borde bg-superficie-2 text-tinta-2";
  if (error && !estado) {
    texto = "MODO DESCONOCIDO";
    estilo = "border-critico-borde bg-critico-fondo text-critico-tinta";
  } else if (estado) {
    texto = `MODO ${nombreModo(estado.modo)}`;
    if (estado.modo.es_real) estilo = "border-transparent bg-peligro text-white";
    else if (estado.modo.envia_ordenes) estilo = "border-aviso-borde bg-aviso-fondo text-aviso-tinta";
    else estilo = "border-borde bg-superficie-2 text-tinta";
  }
  return (
    <span
      className={clases("rounded border px-2 py-0.5 text-xs font-bold tracking-wide whitespace-nowrap", estilo)}
      aria-live="polite"
    >
      {texto}
    </span>
  );
}

function Navegacion() {
  const ruta = usePathname();
  const normal = ruta.endsWith("/") ? ruta : `${ruta}/`;
  return (
    <nav aria-label="Pestañas del panel" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex min-w-max gap-1">
        {PESTANAS.map((p) => {
          const activa = normal === p.ruta || (normal === "/" && p.ruta === "/mercado/");
          return (
            <li key={p.ruta}>
              <Link
                href={p.ruta}
                aria-current={activa ? "page" : undefined}
                className={clases(
                  "block rounded-t-md border-b-2 px-3 py-2 text-sm whitespace-nowrap",
                  activa
                    ? "border-acento font-semibold text-tinta"
                    : "border-transparent text-tinta-2 hover:border-eje hover:text-tinta",
                )}
              >
                {p.texto}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function SelectorTema() {
  const [tema, fijarTema] = useGuardado("local", "invest-ll.tema", "auto");
  useEffect(() => {
    if (tema === "claro") document.documentElement.dataset.theme = "light";
    else if (tema === "oscuro") document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
  }, [tema]);
  return (
    <label className="flex items-center gap-1.5 text-xs text-tinta-2">
      Tema
      <select
        value={tema}
        onChange={(e) => fijarTema(e.target.value === "auto" ? null : e.target.value)}
        className="rounded border border-borde bg-superficie px-1.5 py-0.5 text-xs text-tinta"
      >
        <option value="auto">sistema</option>
        <option value="claro">claro</option>
        <option value="oscuro">oscuro</option>
      </select>
    </label>
  );
}

/** El modo va en la cabecera, no escondido: es lo primero que hay que saber al mirar una cifra. */
function AvisosDeModo() {
  const { estado, error, cargando } = useEstado();

  if (error && !estado) {
    return (
      <div className="space-y-2">
        <Aviso tipo="critico">
          <strong>No se ha podido leer el modo de operación</strong>, así que este panel no puede
          decirte si envía órdenes o no. No uses nada que mueva dinero hasta que la API responda.
        </Aviso>
        <ErrorApiVista error={error} prefijo="GET /api/estado:" />
      </div>
    );
  }
  if (!estado) {
    return cargando ? <p className="text-sm text-tinta-2">Leyendo el modo de operación de la API…</p> : null;
  }

  const { modo } = estado;
  return (
    <div className="space-y-2">
      {modo.es_real ? (
        <Aviso tipo="critico">
          <strong>MODO REAL: este panel PUEDE enviar órdenes con dinero de verdad.</strong> Cada una
          sigue pidiendo su confirmación.
        </Aviso>
      ) : modo.envia_ordenes ? (
        <Aviso tipo="aviso">
          <strong>MODO PRUEBAS: las órdenes salen de verdad al exchange, con dinero ficticio.</strong>
        </Aviso>
      ) : null}
      <p className="text-sm text-tinta-2">
        Simulación sobre datos históricos.{" "}
        {modo.envia_ordenes
          ? "Las órdenes se envían desde Mi cartera, con confirmación. "
          : "No ejecuta ninguna orden real. "}
        <strong className="font-semibold text-tinta">Recuerda: el win rate no es criterio de éxito.</strong>
      </p>
      {estado.reserva ? (
        <Aviso tipo="info">
          <TextoApi texto={estado.reserva} />
        </Aviso>
      ) : null}
      {estado.pausa ? (
        <Aviso tipo="aviso">
          <strong>Pausa de entradas activa:</strong> <TextoApi texto={estado.pausa} />. No se proponen entradas nuevas; las
          posiciones abiertas no se tocan.
        </Aviso>
      ) : null}
      {estado.activos.length === 0 ? (
        <Aviso tipo="critico">
          No hay ningún histórico descargado todavía. Descarga alguno con:{" "}
          <Codigo>
            uv run invest-ll-fetch AAPL --market equity --interval DAY_1 --start 2020-01-01 --end 2026-01-01
          </Codigo>
        </Aviso>
      ) : null}
    </div>
  );
}

function ControlCostes() {
  const { comision, slippage, motivo, fijarComision, fijarSlippage, restablecer } = useCostes();
  const pctComision = fraccionComoPorcentaje(comision);
  const pctSlippage = fraccionComoPorcentaje(slippage);
  return (
    <fieldset className="rounded-md border border-borde bg-superficie px-3 py-2">
      <legend className="px-1 text-xs font-semibold tracking-wide text-tinta-2 uppercase">
        Costes de toda simulación
      </legend>
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <label className="flex items-center gap-2 text-sm">
          <span>Comisión por operación</span>
          <input
            value={comision}
            onChange={(e) => fijarComision(e.target.value)}
            inputMode="decimal"
            aria-invalid={motivo !== null && motivo.toLowerCase().includes("comisión") ? true : undefined}
            className="cifras w-24 rounded border border-borde bg-superficie px-2 py-1 text-sm aria-[invalid=true]:border-critico-borde"
          />
          <span className="cifras text-xs text-tinta-2">{pctComision ?? "?"}</span>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span>Slippage</span>
          <input
            value={slippage}
            onChange={(e) => fijarSlippage(e.target.value)}
            inputMode="decimal"
            aria-invalid={motivo !== null && motivo.toLowerCase().includes("slippage") ? true : undefined}
            className="cifras w-24 rounded border border-borde bg-superficie px-2 py-1 text-sm aria-[invalid=true]:border-critico-borde"
          />
          <span className="cifras text-xs text-tinta-2">{pctSlippage ?? "?"}</span>
        </label>
        <button type="button" onClick={restablecer} className="text-xs text-acento underline underline-offset-2">
          Volver a 0.001 / 0.0005
        </button>
      </div>
      <p className="mt-1 text-xs text-tinta-2">
        Obligatorios a propósito: una simulación sin fricción es una mentira optimista. Alimentan todas las
        peticiones de Simular y se guardan en este navegador.
      </p>
      {motivo ? (
        <p className="mt-1 text-xs font-medium text-critico-tinta" role="alert">
          {motivo} No se puede simular hasta corregirlo.
        </p>
      ) : null}
    </fieldset>
  );
}

export function Cabecera() {
  const { estado } = useEstado();
  const real = estado?.modo.es_real ?? false;
  return (
    <header>
      <div
        className={clases(
          "sticky top-0 z-20 border-b border-borde bg-pagina/95 backdrop-blur",
          real && "border-t-4 border-t-peligro",
        )}
      >
        <div className="mx-auto max-w-7xl px-4">
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
            <div className="flex items-center gap-3">
              <Link href="/mercado/" className="text-base font-bold tracking-tight text-tinta">
                INVEST LL
              </Link>
              <InsigniaModo />
            </div>
            <SelectorTema />
          </div>
          <Navegacion />
        </div>
      </div>
      <div className="mx-auto max-w-7xl space-y-3 px-4 pt-4">
        {MODO_EJEMPLO ? (
          <Aviso tipo="critico">
            <strong>DATOS DE EJEMPLO.</strong> Este panel está usando las respuestas inventadas de{" "}
            <Codigo>web/mocks/</Codigo> (<Codigo>NEXT_PUBLIC_MOCK=1</Codigo>), no la API
            {API_BASE ? ` de ${API_BASE}` : ""}. Ninguna cifra de esta pantalla es real.
          </Aviso>
        ) : null}
        <AvisosDeModo />
        <ControlCostes />
      </div>
    </header>
  );
}
