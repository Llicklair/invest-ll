"use client";

import { Bot, ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { Bots as DatosBots, CanalVivo, ResumenBot } from "@/api/tipos";
import { ProveedorVivo, useVivo } from "@/api/vivo";
import { Variacion } from "@/componentes/CifraGrande";
import { EstadoEnVivo } from "@/componentes/EnVivo";
import { EstadoVacio } from "@/componentes/EstadoVacio";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { Aviso, BotonEnlace, Encabezado, Esqueleto, Segmentado, Tarjeta } from "@/componentes/ui";
import { formatoImporte } from "@/lib/decimal";
import { fraccion } from "@/lib/formato";
import { horaSegundos } from "@/lib/vivo";

import { ChipEvidenciaBot, CifrasBot, Dato, EstadoChip, MiniCurva, NotaBots, PctColor, diasTexto, usdc } from "./comun";

const CANALES: readonly CanalVivo[] = ["bots", "estado"];

type Orden = "ganancia" | "dias" | "riesgo";

/**
 * Bots (docs/panel-v3-vivo.md, seccion 3), al estilo de los vaults de Hyperliquid: arriba el
 * total, en vivo; debajo una tarjeta por bot con lo que ha generado frente a solo mantener.
 */
export function Bots() {
  return (
    <ProveedorVivo canales={CANALES}>
      <ListaBots />
    </ProveedorVivo>
  );
}

function ordenar(bots: readonly ResumenBot[], orden: Orden): ResumenBot[] {
  const copia = [...bots];
  if (orden === "ganancia") copia.sort((a, b) => (b.ganancia_pct ?? -Infinity) - (a.ganancia_pct ?? -Infinity));
  if (orden === "dias") copia.sort((a, b) => b.dias - a.dias);
  if (orden === "riesgo") copia.sort((a, b) => a.riesgo - b.riesgo || (b.ganancia_pct ?? 0) - (a.ganancia_pct ?? 0));
  return copia;
}

function ListaBots() {
  const datos = useVivo("bots");
  const [orden, setOrden] = useState<Orden>("ganancia");
  const lista = useMemo(() => (datos ? ordenar(datos.bots, orden) : []), [datos, orden]);

  return (
    <div className="space-y-8">
      <Encabezado
        antetitulo="En vivo"
        titulo="Bots"
        bajada="Bots que compran y venden solos con dinero ficticio. Aquí ves, en vivo, cuánto genera cada uno y si lo hace mejor que solo mantener sus monedas."
        accion={
          // Sin bots, el boton es el del estado vacio (un solo primario por pantalla).
          datos && !datos.bots.length ? undefined : (
            <BotonEnlace href="/bots/nuevo/" variante="primario">
              <Plus aria-hidden="true" className="h-5 w-5" />
              Desplegar un bot
            </BotonEnlace>
          )
        }
      />
      <div className="-mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <NotaBots texto={datos?.nota} />
        <EstadoEnVivo />
      </div>

      {!datos ? (
        <div className="space-y-4">
          <Esqueleto className="h-28" />
          <div className="grid gap-4 md:grid-cols-2">
            <Esqueleto className="h-96" />
            <Esqueleto className="h-96" />
          </div>
        </div>
      ) : !datos.bots.length ? (
        <EstadoVacio
          icono={Bot}
          tono="neutro"
          titulo="Aún no has desplegado ningún bot"
          accion={
            <BotonEnlace href="/bots/nuevo/" variante="primario">
              Desplegar un bot
            </BotonEnlace>
          }
        >
          Un bot sigue una regla fija (por ejemplo, «estar en Bitcoin mientras sube») y compra y vende solo, con dinero ficticio y precios de verdad. Aquí verás cuánto
          genera y si gana a solo mantener.
        </EstadoVacio>
      ) : (
        <>
          <Resumen datos={datos} />
          <section aria-labelledby="titulo-tus-bots" className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 id="titulo-tus-bots" className="titular text-[1.375rem] font-semibold text-tinta">
                Tus bots <span className="text-tinta-suave">({datos.bots.length})</span>
              </h2>
              <Segmentado
                etiqueta="Ordenar por"
                opciones={[
                  { valor: "ganancia", texto: "Ganancia" },
                  { valor: "dias", texto: "Días" },
                  { valor: "riesgo", texto: "Riesgo" },
                ]}
                valor={orden}
                onCambio={setOrden}
                className="[&>legend]:mb-1 [&>legend]:text-sm"
              />
            </div>
            <ul className="grid items-start gap-4 md:grid-cols-2">
              {lista.map((b) => (
                <li key={b.id} className="min-w-0">
                  <TarjetaBot bot={b} />
                </li>
              ))}
            </ul>
            <div className="text-sm text-tinta-suave">
              <QueEsEsto clave="mantener" />
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Resumen({ datos }: { datos: DatosBots }) {
  return (
    <Tarjeta como="section" aria-label="El total de tus bots" className="p-5 sm:p-6">
      <div className="grid gap-5 sm:grid-cols-[1.3fr_1fr_1fr]">
        <div>
          <p className="text-[0.9375rem] font-medium text-tinta-suave">Lo que valen ahora</p>
          <p className="titular mt-1 text-[2.5rem] leading-none font-medium tracking-tight text-tinta">
            {formatoImporte(datos.valor).replace(/^-/, "−")} <span className="text-[0.5em] text-tinta-suave">USDC</span>
          </p>
          <Variacion importe={datos.ganancia} pct={datos.ganancia_pct} moneda="USDC" coletilla="entre todos" className="mt-3" />
        </div>
        <dl className="cifras grid content-start gap-1 text-[0.9375rem]">
          <dt className="text-sm text-tinta-suave">Capital ficticio puesto</dt>
          <dd className="font-semibold text-tinta">{usdc(datos.capital)}</dd>
          <dt className="mt-2 text-sm text-tinta-suave">En marcha</dt>
          <dd className="font-semibold text-tinta">
            {datos.bots.filter((b) => b.estado === "en_marcha").length} de {datos.bots.length}
          </dd>
        </dl>
        <p className="self-end text-sm leading-relaxed text-tinta-suave">
          Valorado a precios de las {horaSegundos(datos.at)}. Cada bot se compara con solo mantener sus monedas desde que arrancó.
        </p>
      </div>
    </Tarjeta>
  );
}

/** La tarjeta de un bot, como un vault: nombre, estado, cuanto ha generado frente a mantener. */
export function TarjetaBot({ bot }: { bot: ResumenBot }) {
  const capital = Number(bot.capital);
  return (
    <Tarjeta como="article" className="relative flex flex-col gap-4 p-5 hover:border-linea-control/60">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="titular text-xl leading-snug font-semibold text-tinta">
            <Link href={`/bots/ficha/?id=${encodeURIComponent(bot.id)}`} className="after:absolute after:inset-0 after:rounded-tarjeta hover:underline focus-visible:outline-none">
              {bot.nombre}
            </Link>
          </h3>
          <p className="mt-0.5 text-sm text-tinta-suave">
            {bot.nombre_plantilla} · {bot.monedas.join(" y ")} · {diasTexto(bot.dias)}
          </p>
        </div>
        <EstadoChip estado={bot.estado} className="shrink-0" />
      </header>

      {bot.estado === "error" && bot.motivo_error ? (
        <Aviso tipo="critico" className="relative z-10 text-sm">
          {bot.motivo_error}
        </Aviso>
      ) : bot.aviso ? (
        <Aviso tipo="aviso" className="relative z-10 text-sm">
          {bot.aviso}
        </Aviso>
      ) : null}

      <CifrasBot bot={bot} />

      <div>
        <MiniCurva curva={bot.curva} capital={capital} />
        <p className="mt-1 flex justify-between text-xs text-tinta-suave">
          <span>Lo que vale: {usdc(bot.valor, { decimales: 0 })}</span>
          <span>Puso {usdc(bot.capital, { decimales: 0 })}</span>
        </p>
      </div>

      <dl className="grid grid-cols-4 gap-2 border-y border-linea py-3">
        <Dato etiqueta="Hoy">
          <PctColor valor={bot.ganancia_24h_pct} />
        </Dato>
        <Dato etiqueta="Peor caída">{bot.peor_caida === null ? "—" : fraccion(bot.peor_caida, 1)}</Dato>
        <Dato etiqueta="Días">{bot.dias.toLocaleString("es-ES", { maximumFractionDigits: 1 })}</Dato>
        <Dato etiqueta="Operaciones">{bot.operaciones.toLocaleString("es-ES")}</Dato>
      </dl>

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <ChipEvidenciaBot evidencia={bot.evidencia} />
          <MedidorRiesgo nivel={bot.riesgo} compacto />
        </div>
        <span className="inline-flex items-center gap-0.5 text-sm font-semibold text-marca" aria-hidden="true">
          Ver ficha <ChevronRight className="h-4 w-4" />
        </span>
      </div>
      <p className="-mt-2 text-xs leading-relaxed text-tinta-suave">{bot.evidencia.texto}</p>
    </Tarjeta>
  );
}
