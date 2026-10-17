"use client";

import { ArrowRight, Bot, CandlestickChart, Sprout } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { Bots as DatosBots, CanalVivo, Inicio as DatosInicio, ResumenBot } from "@/api/tipos";
import { ProveedorVivo, useVivo } from "@/api/vivo";
import { Variacion } from "@/componentes/CifraGrande";
import { AvisoDatos } from "@/componentes/DatosAlDia";
import { EstadoEnVivo } from "@/componentes/EnVivo";
import { Aviso, BotonEnlace, Chip, EnlaceFlecha, ErrorApiVista, Esqueleto, Tarjeta, TextoApi, clases } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useModo } from "@/contexto/modo";
import { useConsulta } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { haceCuanto } from "@/lib/formato";
import { horaSegundos } from "@/lib/vivo";
import { EstadoChip, MiniCurva, PctColor, usdc } from "@/vistas/bots/comun";
import { ChipModo, pausadoSolo } from "@/vistas/bots/real";

import { MercadoEnUnaLinea, QueTocaHacer, TuDinero, TuPlan } from "./plan";

/** El Resumen solo necesita los bots y el estado de la fuente: ni libro ni velas. */
const CANALES_RESUMEN: readonly CanalVivo[] = ["bots", "estado"];

/** Repinta cada segundo lo que dice "hace 12 s". */
function useAhora(cadaMs = 1000): number {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setAhora(Date.now()), cadaMs);
    return () => window.clearInterval(t);
  }, [cadaMs]);
  return ahora;
}

// -- Sin nada todavia ----------------------------------------------------------------------------

const CAMINOS = [
  {
    href: "/plan/",
    icono: Sprout,
    titulo: "Invertir a largo plazo",
    texto: "Cinco preguntas sin jerga, una propuesta explicada y tu plan: qué comprar cada mes y cuánto habría llegado a bajar.",
    accion: "Hacer mi plan",
  },
  {
    href: "/bots/nuevo/",
    icono: Bot,
    titulo: "Poner un bot a trabajar",
    texto: "Un bot sigue una regla fija y compra y vende solo, con dinero ficticio y precios de verdad. Verás en directo si gana a solo mantener.",
    accion: "Desplegar un bot",
  },
] as const;

function Bienvenida() {
  return (
    <div className="mx-auto max-w-3xl py-4 lg:py-10">
      <p className="text-[0.9375rem] font-medium text-tinta-suave">Bienvenida</p>
      <h1 className="titular mt-3 text-[2.5rem] leading-[1.08] font-semibold text-tinta sm:text-[3.25rem]">
        Hola. Vamos a ver qué hacer con tu dinero.
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-tinta-suave">
        Hay dos maneras de empezar. Ninguna mueve dinero de verdad hasta que tú lo decidas, y cada cifra te dice de cuándo es.
      </p>
      <ul className="mt-10 grid gap-4 sm:grid-cols-2">
        {CAMINOS.map((c) => {
          const Icono = c.icono;
          return (
            <li key={c.href}>
              <Tarjeta className="flex h-full flex-col p-6">
                <span className="flex h-11 w-11 items-center justify-center rounded-full bg-marca-suave text-marca" aria-hidden="true">
                  <Icono className="h-5 w-5" strokeWidth={1.75} />
                </span>
                <h2 className="titular mt-4 text-xl font-semibold text-tinta">{c.titulo}</h2>
                <p className="mt-1.5 flex-1 text-[0.9375rem] leading-relaxed text-tinta-suave">{c.texto}</p>
                <BotonEnlace href={c.href} variante="primario" className="mt-6 self-start">
                  {c.accion}
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </BotonEnlace>
              </Tarjeta>
            </li>
          );
        })}
      </ul>
      <p className="mt-8">
        <EnlaceFlecha href="/operar/">O mira el mercado en directo, sin comprar nada</EnlaceFlecha>
      </p>
    </div>
  );
}

// -- Lo que necesita atencion ---------------------------------------------------------------------

function NecesitaAtencion({ bots, inicio }: { bots: DatosBots | null; inicio: DatosInicio | null }) {
  const conProblema = (bots?.bots ?? []).filter((b) => b.estado === "error" || pausadoSolo(b) || (b.aviso && b.modo !== "ficticio"));
  const avisosPlan = inicio?.avisos ?? [];
  return (
    <div className="space-y-3 empty:hidden">
      {conProblema.map((b) => (
        <Aviso key={b.id} tipo={b.estado === "error" || pausadoSolo(b) ? "critico" : "aviso"} titulo={`${b.nombre} necesita que lo mires`}>
          {b.motivo_error ?? b.aviso}{" "}
          <Link href={`/bots/ficha/?id=${encodeURIComponent(b.id)}`} className="font-semibold underline underline-offset-4">
            Ver el bot
          </Link>
        </Aviso>
      ))}
      {avisosPlan.map((a) => (
        <Aviso key={a} tipo="aviso">
          <TextoApi texto={a} />
        </Aviso>
      ))}
      <AvisoDatos />
    </div>
  );
}

// -- Los bots, en directo -------------------------------------------------------------------------

/** Primero lo que se ha movido hace menos; sin actividad, al final. */
function porActividad(a: ResumenBot, b: ResumenBot): number {
  return Date.parse(b.ultima_actividad ?? "") - Date.parse(a.ultima_actividad ?? "") || 0;
}

function FilaBot({ bot, ahora }: { bot: ResumenBot; ahora: number }) {
  return (
    <tr className="group relative border-t border-linea hover:bg-superficie-2/60">
      <th scope="row" className="min-w-[11rem] py-3 pr-3 pl-4 text-left font-normal sm:pl-5">
        <Link
          href={`/bots/ficha/?id=${encodeURIComponent(bot.id)}`}
          className="font-semibold text-tinta after:absolute after:inset-0 hover:underline focus-visible:outline-none"
        >
          {bot.nombre}
        </Link>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-tinta-suave">
          {bot.modo !== "ficticio" ? <ChipModo modo={bot.modo} exchange={bot.exchange} /> : null}
          {bot.nombre_plantilla} · {bot.monedas.join(", ")}
        </span>
      </th>
      <td className="px-3 py-3 max-md:hidden">
        <EstadoChip estado={bot.estado} />
      </td>
      <td className="cifras px-3 py-3 text-right font-medium whitespace-nowrap text-tinta">{usdc(bot.valor, { decimales: 2 })}</td>
      <td className="cifras px-3 py-3 text-right whitespace-nowrap">
        <PctColor valor={bot.ganancia_pct} />
      </td>
      <td className="cifras px-3 py-3 text-right whitespace-nowrap max-sm:hidden">
        <PctColor valor={bot.ganancia_24h_pct} />
      </td>
      <td className="w-32 px-3 py-3 max-lg:hidden">
        <MiniCurva curva={bot.curva} capital={Number(bot.capital)} alto={32} />
      </td>
      <td className="py-3 pr-4 pl-3 text-right text-sm whitespace-nowrap text-tinta-suave max-sm:hidden sm:pr-5">
        {bot.ultima_actividad ? haceCuanto(bot.ultima_actividad, ahora) : "sin operar aún"}
      </td>
    </tr>
  );
}

function TusBots({ datos }: { datos: DatosBots | null }) {
  const ahora = useAhora();
  if (!datos) return <Esqueleto className="h-72" />;
  const mezcla = datos.bots.some((b) => b.modo !== "ficticio");
  const enMarcha = datos.bots.filter((b) => b.estado === "en_marcha").length;
  const lista = [...datos.bots].sort(porActividad).slice(0, 8);
  return (
    <Tarjeta como="section" aria-labelledby="titulo-bots" className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 p-5 sm:p-6">
        <div>
          <h2 id="titulo-bots" className="flex flex-wrap items-center gap-2 titular text-xl font-semibold text-tinta">
            Tus bots
            {!mezcla ? <Chip tono="pruebas">Dinero ficticio</Chip> : null}
          </h2>
          {datos.bots.length ? (
            <>
              <p className="titular mt-3 text-[2.25rem] leading-none font-medium tracking-tight text-tinta">
                {formatoImporte(datos.valor).replace(/^-/, "−")} <span className="text-[0.5em] text-tinta-suave">USDC</span>
              </p>
              <Variacion importe={datos.ganancia} pct={datos.ganancia_pct} moneda="USDC" coletilla="desde que los pusiste" className="mt-2" />
              <p className="mt-2 text-sm text-tinta-suave">
                Puesto {usdc(datos.capital)} · {enMarcha} de {datos.bots.length} en marcha · precios de las {horaSegundos(datos.at)}
                {mezcla ? " · suma dinero ficticio, de pruebas y real" : ""}
              </p>
            </>
          ) : null}
        </div>
        <EstadoEnVivo />
      </div>
      {datos.bots.length ? (
        <>
          <table className="w-full text-[0.9375rem]">
            <caption className="sr-only">Tus bots, el que se movió hace menos primero</caption>
            <thead className="text-xs text-tinta-suave">
              <tr>
                <th scope="col" className="pb-2 pl-4 text-left font-medium sm:pl-5">
                  Bot
                </th>
                <th scope="col" className="px-3 pb-2 text-left font-medium max-md:hidden">
                  Estado
                </th>
                <th scope="col" className="px-3 pb-2 text-right font-medium">
                  Vale
                </th>
                <th scope="col" className="px-3 pb-2 text-right font-medium">
                  Ganancia
                </th>
                <th scope="col" className="px-3 pb-2 text-right font-medium max-sm:hidden">
                  Hoy
                </th>
                <th scope="col" className="px-3 pb-2 font-medium max-lg:hidden">
                  <span className="sr-only">Curva</span>
                </th>
                <th scope="col" className="pr-4 pb-2 pl-3 text-right font-medium max-sm:hidden sm:pr-5">
                  Última actividad
                </th>
              </tr>
            </thead>
            <tbody>
              {lista.map((b) => (
                <FilaBot key={b.id} bot={b} ahora={ahora} />
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-linea px-5 py-3 sm:px-6">
            <EnlaceFlecha href="/bots/">{datos.bots.length > lista.length ? `Ver los ${datos.bots.length} bots` : "Ver tus bots"}</EnlaceFlecha>
            <Link href="/bots/nuevo/" className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline">
              Desplegar otro
            </Link>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-linea px-5 py-4 sm:px-6">
          <p className="text-[0.9375rem] text-tinta-suave">Aún no tienes bots. Uno sigue una regla fija y compra y vende solo, con dinero ficticio.</p>
          <BotonEnlace href="/bots/nuevo/">Desplegar un bot</BotonEnlace>
        </div>
      )}
    </Tarjeta>
  );
}

// -- El plan a largo plazo ------------------------------------------------------------------------

function TuPlanResumido({ datos }: { datos: DatosInicio }) {
  const { versionDatos } = useEstado();
  const { modo } = useModo();
  const hoy = useConsulta(`hoy:${versionDatos}:${modo ?? "?"}`, () => pedir(api.GET("/api/plan/hoy")));
  return (
    <section aria-labelledby="titulo-plan" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="titulo-plan" className="titular text-xl font-semibold text-tinta">
          Tu plan a largo plazo
        </h2>
        <EnlaceFlecha href="/plan/">Ir a Mi plan</EnlaceFlecha>
      </div>
      <TuDinero datos={datos} />
      <QueTocaHacer hoy={hoy.datos} error={hoy.error} recargar={hoy.recargar} cargando={hoy.cargando} />
    </section>
  );
}

function SinPlan() {
  return (
    <Tarjeta className="flex flex-wrap items-center justify-between gap-4 p-5">
      <div className="flex items-start gap-3">
        <Sprout aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-marca" strokeWidth={1.75} />
        <div>
          <p className="font-semibold text-tinta">Aún no tienes un plan a largo plazo</p>
          <p className="text-[0.9375rem] text-tinta-suave">Cinco preguntas y te proponemos un reparto, con lo bueno y lo malo.</p>
        </div>
      </div>
      <EnlaceFlecha href="/plan/">Hacer mi plan</EnlaceFlecha>
    </Tarjeta>
  );
}

// -- La pagina ------------------------------------------------------------------------------------

function PanelResumen() {
  const { versionDatos } = useEstado();
  const { modo } = useModo();
  const inicio = useConsulta(`inicio:${versionDatos}:${modo ?? "?"}`, () => pedir(api.GET("/api/inicio")));
  const bots = useVivo("bots");
  const d = inicio.datos;

  if (d && bots && !d.plan && !d.hay_movimientos && !bots.bots.length) return <Bienvenida />;

  return (
    <div className={clases("space-y-8", inicio.cargando && "opacity-90 transition-opacity")}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="titular text-[2rem] leading-tight font-semibold text-tinta lg:text-[2.5rem]">Resumen</h1>
          <p className="mt-2 text-base text-tinta-suave lg:text-lg">Todo tu dinero y lo que está pasando ahora.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <BotonEnlace href="/operar/" tamano="compacto">
            <CandlestickChart aria-hidden="true" className="h-4 w-4" />
            Operar
          </BotonEnlace>
        </div>
      </header>

      <NecesitaAtencion bots={bots} inicio={d} />

      <TusBots datos={bots} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-8">
        <div className="min-w-0 space-y-8">
          {inicio.error && !d ? (
            <ErrorApiVista error={inicio.error} prefijo="No se pudo leer cómo va tu plan:" reintentar={inicio.recargar} />
          ) : !d ? (
            <Esqueleto className="h-56" />
          ) : d.plan ? (
            <TuPlanResumido datos={d} />
          ) : (
            <SinPlan />
          )}
        </div>
        <div className="min-w-0 space-y-6">
          {d?.plan ? <TuPlan datos={d} /> : null}
          {d ? <MercadoEnUnaLinea datos={d} /> : null}
        </div>
      </div>
    </div>
  );
}

/**
 * Resumen (docs/panel-v5.md, seccion 3): el panel de control. Todo tu dinero, los bots en directo
 * y lo que necesita que lo mires. Sin nada todavia, la bienvenida con los dos caminos.
 */
export function Resumen() {
  return (
    <ProveedorVivo canales={CANALES_RESUMEN}>
      <PanelResumen />
    </ProveedorVivo>
  );
}
