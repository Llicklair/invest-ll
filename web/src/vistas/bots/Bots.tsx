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
import { Aviso, BotonEnlace, Encabezado, Esqueleto, Segmentado, Tarjeta, clases } from "@/componentes/ui";
import { useGuardado } from "@/lib/almacen";
import { formatoImporte } from "@/lib/decimal";
import { fraccion } from "@/lib/formato";
import { horaSegundos } from "@/lib/vivo";

import { FeedActividad } from "./Actividad";
import { TarjetaMotor } from "./Motor";
import { TablaBots } from "./TablaBots";
import { ChipEvidenciaBot, CifrasBot, Dato, EstadoChip, MiniCurva, NotaBots, PctColor, diasTexto, usdc } from "./comun";
import { ChipModo, LimitesConsumo, PanelReal, bordeModo, hayNoFicticio, pausadoSolo } from "./real";

const CANALES: readonly CanalVivo[] = ["bots", "estado", "actividad"];

type Orden = "movimiento" | "ganancia" | "dias" | "riesgo";
type Vista = "tabla" | "tarjetas";

/**
 * Bots (docs/panel-v3-vivo.md, seccion 3; docs/panel-v5.md §4), al estilo de los vaults de
 * Hyperliquid: arriba el total, en vivo; debajo una tabla en directo (o una tarjeta por bot) y, al
 * lado, "Ahora mismo": cada compra, venta y aviso de todos los bots según ocurre.
 */
export function Bots() {
  return (
    <ProveedorVivo canales={CANALES}>
      <ListaBots />
    </ProveedorVivo>
  );
}

const PESO_MODO: Record<ResumenBot["modo"], number> = { real: 0, pruebas: 1, ficticio: 2 };

/** Lo real primero, luego pruebas y ficticio; dentro de cada modo, el orden elegido. */
function ordenar(bots: readonly ResumenBot[], orden: Orden): ResumenBot[] {
  const copia = [...bots];
  if (orden === "movimiento") copia.sort((a, b) => (Date.parse(b.ultima_actividad ?? "") || 0) - (Date.parse(a.ultima_actividad ?? "") || 0));
  if (orden === "ganancia") copia.sort((a, b) => (b.ganancia_pct ?? -Infinity) - (a.ganancia_pct ?? -Infinity));
  if (orden === "dias") copia.sort((a, b) => b.dias - a.dias);
  if (orden === "riesgo") copia.sort((a, b) => a.riesgo - b.riesgo || (b.ganancia_pct ?? 0) - (a.ganancia_pct ?? 0));
  return copia.sort((a, b) => PESO_MODO[a.modo] - PESO_MODO[b.modo]);
}

function ListaBots() {
  const datos = useVivo("bots");
  const [orden, setOrden] = useState<Orden>("movimiento");
  const [vistaGuardada, fijarVista] = useGuardado("local", "invest-ll.bots.vista", "tabla");
  const vista: Vista = vistaGuardada === "tarjetas" ? "tarjetas" : "tabla";
  const lista = useMemo(() => (datos ? ordenar(datos.bots, orden) : []), [datos, orden]);

  return (
    <div className="space-y-8">
      <Encabezado
        antetitulo="En vivo"
        titulo="Bots"
        bajada="Bots que compran y venden solos: con dinero ficticio, en la red de pruebas de un exchange o, si tú lo activas, con dinero real y los límites que pongas. Aquí ves, en vivo, cuánto genera cada uno y si lo hace mejor que solo mantener."
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

      {datos && hayNoFicticio(datos) ? <PanelReal datos={datos} /> : null}

      <TarjetaMotor />

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
          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <section aria-labelledby="titulo-tus-bots" className="min-w-0 space-y-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <h2 id="titulo-tus-bots" className="titular text-[1.375rem] font-semibold text-tinta">
                  Tus bots <span className="text-tinta-suave">({datos.bots.length})</span>
                </h2>
                <div className="flex flex-wrap items-end gap-3">
                  <Segmentado
                    etiqueta="Ordenar por"
                    opciones={[
                      { valor: "movimiento", texto: "Último movimiento" },
                      { valor: "ganancia", texto: "Ganancia" },
                      { valor: "dias", texto: "Días" },
                      { valor: "riesgo", texto: "Riesgo" },
                    ]}
                    valor={orden}
                    onCambio={setOrden}
                    className="[&>legend]:mb-1 [&>legend]:text-sm"
                  />
                  <Segmentado
                    etiqueta="Ver como"
                    opciones={[
                      { valor: "tabla", texto: "Tabla" },
                      { valor: "tarjetas", texto: "Tarjetas" },
                    ]}
                    valor={vista}
                    onCambio={(v) => fijarVista(v)}
                    className="[&>legend]:mb-1 [&>legend]:text-sm"
                  />
                </div>
              </div>
              {vista === "tabla" ? (
                <Tarjeta className="overflow-hidden pt-3">
                  <TablaBots bots={lista} etiqueta="Tus bots, en directo" />
                </Tarjeta>
              ) : (
                <ul className="grid items-start gap-4 md:grid-cols-2">
                  {lista.map((b) => (
                    <li key={b.id} className="min-w-0">
                      <TarjetaBot bot={b} />
                    </li>
                  ))}
                </ul>
              )}
              <div className="text-sm text-tinta-suave">
                <QueEsEsto clave="mantener" />
              </div>
            </section>
            <FeedActividad limite={15} className="xl:sticky xl:top-6" />
          </div>
        </>
      )}
    </div>
  );
}

export const ETIQUETA_MODO = { ficticio: "Dinero ficticio", pruebas: "Red de pruebas", real: "Dinero real" } as const;

function Resumen({ datos }: { datos: DatosBots }) {
  // El dinero ficticio, el de pruebas y el real no se suman: con más de un modo, un bloque por modo.
  const mezcla = datos.por_modo.some((t) => t.modo !== "ficticio");
  if (mezcla) {
    return (
      <Tarjeta como="section" aria-label="El total de tus bots, por modo" className="p-5 sm:p-6">
        <div className="grid gap-4 sm:grid-cols-3">
          {datos.por_modo.map((t) => (
            <div
              key={t.modo}
              className={clases(
                "min-w-0 rounded-xl p-4",
                t.modo === "real" ? "border-2 border-real/60 bg-real-suave/40" : t.modo === "pruebas" ? "bg-pruebas-suave/60" : "bg-superficie-2",
              )}
            >
              <p className={clases("text-sm font-semibold", t.modo === "real" ? "text-real-tinta" : t.modo === "pruebas" ? "text-pruebas-tinta" : "text-tinta-suave")}>
                {ETIQUETA_MODO[t.modo]} · {t.bots} {t.bots === 1 ? "bot" : "bots"}
              </p>
              <p className="titular mt-1 text-[1.75rem] leading-none font-medium tracking-tight text-tinta">
                {formatoImporte(t.valor).replace(/^-/, "−")} <span className="text-[0.5em] text-tinta-suave">USDC</span>
              </p>
              <Variacion importe={t.ganancia} pct={t.ganancia_pct} moneda="USDC" coletilla={`de ${usdc(t.capital, { decimales: 0 })} puestos`} className="mt-2" />
            </div>
          ))}
        </div>
        <p className="mt-4 text-sm leading-relaxed text-tinta-suave">
          Valorado a precios de las {horaSegundos(datos.at)} · {datos.bots.filter((b) => b.estado === "en_marcha").length} de {datos.bots.length} en marcha. Cada modo va aparte: el dinero
          ficticio, el de pruebas y el real no se suman.
        </p>
      </Tarjeta>
    );
  }
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
    <Tarjeta como="article" className={clases("relative flex flex-col gap-4 p-5 hover:border-linea-control/60", bordeModo(bot.modo), bot.modo === "real" && "border-real/50")}>
      <ChipModo modo={bot.modo} exchange={bot.exchange} className="self-start" />
      <header className="-mt-1 flex items-start justify-between gap-3">
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
      ) : pausadoSolo(bot) ? (
        <Aviso tipo="critico" titulo="Necesita que lo mires" className="relative z-10 text-sm">
          {bot.aviso}
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

      {bot.limites ? (
        <div className="rounded-xl border border-linea px-3 py-3">
          <p className="mb-2 text-sm font-semibold text-tinta">Sus límites</p>
          <LimitesConsumo bot={bot} />
        </div>
      ) : null}

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
