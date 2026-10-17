"use client";

import { ArrowLeft, CircleAlert, CirclePause, CirclePlay, Clock, Info, OctagonAlert, Play, ShieldAlert, SlidersHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import type { CanalVivo, DetalleBot, EventoBot, OperacionBot } from "@/api/tipos";
import { ProveedorVivo, useAlmacenVivo, useVivo } from "@/api/vivo";
import { EstadoEnVivo } from "@/componentes/EnVivo";
import { EstadoVacio } from "@/componentes/EstadoVacio";
import { Hoja } from "@/componentes/Hoja";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import { Aviso, Boton, CargandoLento, ErrorApiVista, Esqueleto, Seccion, Tarjeta, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoCantidad, formatoImporte } from "@/lib/decimal";
import { fecha, fraccion, fraccionCoherente, momento, signoImporteVisible } from "@/lib/formato";
import { nombreExchange } from "@/lib/nombres";
import { nombreIntervalo } from "@/lib/vivo";

import { ChipEvidenciaBot, CifrasBot, Dato, EstadoChip, NotaBots, PctColor, diasTexto, usdc } from "./comun";
import { CurvaBot } from "./CurvaBot";
import { ChipModo, HojaActivarReal, HojaLimites, LimitesConsumo, PanelReal, pausadoSolo } from "./real";

const CANALES: readonly CanalVivo[] = ["bots", "estado"];
const SONDEO_FICHA_MS = 5000;

/**
 * La ficha de un bot (docs/panel-v3-vivo.md, seccion 3): la curva en vivo frente a mantener, sus
 * posiciones, sus operaciones con el porque, los eventos (arranques, paradas, huecos), los
 * parametros y Parar / Reanudar / Borrar.
 *
 * Las cifras de arriba y la curva del bot llegan por el stream (`bots`, cada ~2 s); el resto del
 * detalle (`GET /api/bots/{id}`) se vuelve a pedir cada 5 s: el stream no trae la ficha entera.
 */
export function FichaBot() {
  const id = useSearchParams().get("id") ?? "";
  return (
    <ProveedorVivo canales={CANALES}>
      <Ficha id={id} />
    </ProveedorVivo>
  );
}

function Ficha({ id }: { id: string }) {
  const nuevo = useSearchParams().get("nuevo") === "1";
  const [vuelta, setVuelta] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => {
      if (!document.hidden) setVuelta((v) => v + 1);
    }, SONDEO_FICHA_MS);
    return () => window.clearInterval(t);
  }, []);
  const detalle = useConsulta(id ? `bot:${id}:${vuelta}` : null, () => pedir(api.GET("/api/bots/{bot_id}", { params: { path: { bot_id: id } } })));
  const plantillas = useConsulta("bots:plantillas", () => pedir(api.GET("/api/bots/plantillas")));
  const lista = useVivo("bots");
  // Lo que devolvio una accion (parar, reanudar) vale hasta la siguiente vuelta del sondeo.
  const [propio, setPropio] = useState<{ datos: DetalleBot; vuelta: number } | null>(null);
  const [hojaReal, setHojaReal] = useState(false);
  const [hojaLimites, setHojaLimites] = useState(false);
  const almacen = useAlmacenVivo();
  /** Lo que devuelve una accion vale hasta el siguiente sondeo, y el stream se entera al momento. */
  const alCambiar = (d: DetalleBot) => {
    setPropio({ datos: d, vuelta });
    const l = almacen.leer("bots");
    if (l) almacen.fijarYa("bots", { ...l, bots: l.bots.map((b) => (b.id === d.id ? { ...b, estado: d.estado, motivo_error: d.motivo_error, aviso: d.aviso, modo: d.modo, limites: d.limites, consumo: d.consumo } : b)) });
  };

  if (!id) {
    return (
      <EstadoVacio icono={CircleAlert} tono="neutro" titulo="¿Qué bot quieres ver?">
        Falta el bot en la dirección. <Link href="/bots/" className="font-medium text-marca underline">Vuelve a la lista</Link>.
      </EstadoVacio>
    );
  }

  const base = propio && propio.vuelta === vuelta ? propio.datos : detalle.datos;
  const vivo = lista?.bots.find((b) => b.id === id) ?? null;
  // Las cifras y la curva del bot, del stream (cada ~2 s); lo demas, de la ficha.
  const bot = base ? { ...base, ...(vivo ?? {}) } : null;
  const plantilla = plantillas.datos?.plantillas.find((p) => p.clave === bot?.plantilla) ?? null;

  if (!bot) {
    if (detalle.error) {
      return (
        <div className="space-y-6">
          <Volver />
          <ErrorApiVista error={detalle.error} reintentar={detalle.recargar} />
        </div>
      );
    }
    return (
      <div className="space-y-6">
        <Volver />
        <CargandoLento texto="Cargando el bot…" lento="Sigue cargando el bot…" />
        <Esqueleto className="h-80" />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <div className="space-y-5">
        <Volver />
        {lista && bot.modo !== "ficticio" ? <PanelReal datos={lista} /> : null}
        <Cabecera bot={bot} onCambio={alCambiar} onActivarReal={() => setHojaReal(true)} />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <NotaBots texto={lista?.nota} />
          <EstadoEnVivo />
        </div>
        {nuevo && bot.operaciones === 0 && bot.estado === "en_marcha" ? (
          <Aviso tipo="hecho" vivo>
            Desplegado. Empieza a operar en su próxima decisión; mientras, aquí verás lo que vale minuto a minuto.
          </Aviso>
        ) : null}
        {bot.modo === "real" ? (
          <Aviso tipo="critico" titulo={`Opera con dinero real en ${nombreExchange(bot.exchange)}`}>
            Compra y vende solo, con tu dinero, sin pedirte confirmación en cada orden y nunca fuera de sus límites. Para pararlo: «Parar» aquí, o «Parar todo lo real» arriba.
          </Aviso>
        ) : null}
        {bot.estado === "error" && bot.motivo_error ? (
          <Aviso tipo="critico" titulo="El bot se ha parado por un error">
            {bot.motivo_error}
          </Aviso>
        ) : pausadoSolo(bot) ? (
          <Aviso tipo="critico" titulo="Necesita que lo mires antes de reanudarlo">
            {bot.aviso}
          </Aviso>
        ) : bot.aviso ? (
          <Aviso tipo="aviso">{bot.aviso}</Aviso>
        ) : null}
      </div>

      <section aria-label="Cuánto ha generado" className="space-y-4">
        <CifrasBot bot={bot} tamano="grande" />
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-tarjeta border border-linea bg-superficie p-4 sm:grid-cols-3 lg:grid-cols-6">
          <Dato etiqueta="Puso">{usdc(bot.capital, { decimales: 0 })}</Dato>
          <Dato etiqueta="Vale ahora">{usdc(bot.valor)}</Dato>
          <Dato etiqueta="En USDC sin invertir">{usdc(base?.efectivo)}</Dato>
          <Dato etiqueta="Hoy">
            <PctColor valor={bot.ganancia_24h_pct} />
          </Dato>
          <Dato etiqueta="Peor caída">{bot.peor_caida === null ? "—" : fraccion(bot.peor_caida, 1)}</Dato>
          <Dato etiqueta="Operaciones">{bot.operaciones.toLocaleString("es-ES")}</Dato>
        </dl>
        <CurvaBot curva={bot.curva} mantener={base?.curva_mantener ?? []} capital={Number(bot.capital)} nombre={bot.nombre} atenuada={detalle.cargando && !detalle.datos} />
        <QueEsEsto clave="mantener" className="text-sm" />
      </section>

      {bot.modo !== "ficticio" || bot.limites ? (
        <Seccion
          titulo="Sus límites"
          bajada={bot.limites ? "Antes de cada orden se comprueba que cabe; si no, no sale y lo apunta." : "Sin límites no puede usarse con dinero real."}
          accion={
            <Boton tamano="compacto" onClick={() => setHojaLimites(true)}>
              <SlidersHorizontal aria-hidden="true" className="h-4 w-4" />
              {bot.limites ? "Cambiar los límites" : "Ponerle límites"}
            </Boton>
          }
        >
          {bot.limites ? (
            <Tarjeta className="p-5">
              <LimitesConsumo bot={bot} className="max-w-xl" />
            </Tarjeta>
          ) : null}
        </Seccion>
      ) : null}

      <Seccion titulo="Lo que tiene" bajada={`Valorado a precios de ahora. Además tiene ${usdc(base?.efectivo)} sin invertir.`}>
        {base?.posiciones.length ? (
          <MarcoTabla etiqueta="Lo que tiene el bot">
            <thead>
              <tr>
                <Th>Moneda</Th>
                <Th numerica>Tiene</Th>
                <Th numerica>Le costó (precio medio)</Th>
                <Th numerica>Precio ahora</Th>
                <Th numerica>Vale</Th>
                <Th numerica>Si vendiera ahora</Th>
              </tr>
            </thead>
            <tbody>
              {base.posiciones.map((p) => {
                const s = signoImporteVisible(p.ganancia);
                return (
                  <tr key={p.coin}>
                    <Td>
                      <span className="font-medium text-tinta">{p.nombre}</span> <span className="text-tinta-suave">{p.coin}</span>
                    </Td>
                    <Td numerica>{formatoCantidad(p.cantidad)}</Td>
                    <Td numerica>{formatoImporte(p.precio_medio)}</Td>
                    <Td numerica>{formatoImporte(p.precio)}</Td>
                    <Td numerica>{usdc(p.valor)}</Td>
                    <Td numerica className={clases("font-medium", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : undefined)}>
                      {s === null ? "—" : `${usdc(p.ganancia, { conSigno: true })} (${fraccionCoherente(p.ganancia_pct, s)})`}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </MarcoTabla>
        ) : (
          <p className="text-[0.9375rem] text-tinta-suave">Ahora no tiene ninguna moneda: todo está en USDC.</p>
        )}
      </Seccion>

      <Operaciones operaciones={base?.lista_operaciones ?? []} total={bot.operaciones} />

      <Seccion titulo="Lo que ha pasado" bajada="Arranques, paradas, cortes de conexión y los huecos en que el panel estuvo cerrado.">
        <ul className="space-y-2">
          {(base?.eventos ?? []).map((e, i) => (
            <FilaEvento key={`${e.at}-${i}`} evento={e} />
          ))}
        </ul>
      </Seccion>

      <Seccion titulo="Cómo está ajustado" bajada={plantilla ? `${plantilla.nombre}: ${plantilla.frase}` : undefined}>
        <Tarjeta className="space-y-5 p-5">
          <dl className="grid gap-x-6 gap-y-3 text-[0.9375rem] sm:grid-cols-[minmax(10rem,auto)_1fr]">
            <dt className="text-tinta-suave">Dónde</dt>
            <dd className="text-tinta">
              <ChipModo modo={bot.modo} exchange={bot.exchange} />
            </dd>
            <dt className="text-tinta-suave">Monedas</dt>
            <dd className="text-tinta">{bot.monedas.join(", ")}</dd>
            {bot.estrategia ? (
              <>
                <dt className="text-tinta-suave">Estrategia a medida</dt>
                <dd className="text-tinta">
                  <Link href={`/estrategias/medida/ficha/?id=${encodeURIComponent(bot.estrategia)}`} className="font-semibold text-marca underline underline-offset-4">
                    {bot.nombre_plantilla.replace(/^A medida: /, "")}
                  </Link>
                </dd>
              </>
            ) : null}
            <dt className="text-tinta-suave">En marcha desde</dt>
            <dd className="text-tinta">
              {fecha(bot.desde)} <span className="text-tinta-suave">({diasTexto(bot.dias)})</span>
            </dd>
            {Object.entries(base?.parametros ?? {}).map(([clave, valor]) => {
              const def = plantilla?.parametros.find((p) => p.clave === clave);
              return (
                <div key={clave} className="contents">
                  <dt className="text-tinta-suave">{def?.nombre ?? clave}</dt>
                  <dd className="text-tinta">
                    <span className="cifras font-medium">{def?.tipo === "intervalo" ? nombreIntervalo(valor) : valor.replace(".", ",")}</span>
                    {def ? <span className="mt-0.5 block text-sm leading-relaxed text-tinta-suave">{def.explicacion}</span> : null}
                  </dd>
                </div>
              );
            })}
          </dl>
          <div className="flex flex-wrap items-center gap-3 border-t border-linea pt-4">
            <ChipEvidenciaBot evidencia={bot.evidencia} />
            <MedidorRiesgo nivel={bot.riesgo} texto={plantilla?.riesgo_texto} compacto />
            <span className="text-sm text-tinta-suave">{bot.evidencia.texto}</span>
          </div>
          {plantilla?.avisos.length ? (
            <Aviso tipo="aviso" titulo="Lo que conviene saber" className="text-sm">
              <ul className="list-disc space-y-0.5 pl-4">
                {plantilla.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Aviso>
          ) : null}
        </Tarjeta>
      </Seccion>

      {base ? (
        <>
          <HojaActivarReal
            bot={{ ...base, ...bot }}
            real={lista?.real ?? null}
            abierta={hojaReal}
            onCerrar={() => setHojaReal(false)}
            onActivado={alCambiar}
            onPonerLimites={() => {
              setHojaReal(false);
              setHojaLimites(true);
            }}
          />
          <HojaLimites bot={{ ...base, ...bot }} abierta={hojaLimites} onCerrar={() => setHojaLimites(false)} onCambio={alCambiar} />
        </>
      ) : null}
    </div>
  );
}

function Volver() {
  return (
    <Link href="/bots/" className="inline-flex min-h-11 items-center gap-1.5 text-[0.9375rem] font-medium text-marca hover:underline">
      <ArrowLeft aria-hidden="true" className="h-4 w-4" /> Tus bots
    </Link>
  );
}

function Cabecera({ bot, onCambio, onActivarReal }: { bot: DetalleBot; onCambio: (d: DetalleBot) => void; onActivarReal: () => void }) {
  const router = useRouter();
  const [borrar, setBorrar] = useState(false);
  const accion = useAccion(async (que: "parar" | "reanudar") => {
    const d =
      que === "parar"
        ? await pedir(api.POST("/api/bots/{bot_id}/parar", { params: { path: { bot_id: bot.id } } }))
        : await pedir(api.POST("/api/bots/{bot_id}/reanudar", { params: { path: { bot_id: bot.id } } }));
    // La lista del stream tarda ~2 s: onCambio actualiza este bot al momento.
    onCambio(d);
    return d;
  });
  const borrado = useAccion(async () => {
    await pedirSinCuerpo(api.DELETE("/api/bots/{bot_id}", { params: { path: { bot_id: bot.id } } }));
    router.push("/bots/");
    return true;
  });

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <ChipModo modo={bot.modo} exchange={bot.exchange} />
          <p className="text-sm font-medium text-tinta-suave">
            {bot.nombre_plantilla} · {bot.monedas.join(" y ")}
          </p>
        </div>
        <h1 className="titular mt-1 text-[2rem] leading-tight font-semibold text-tinta lg:text-[2.5rem]">{bot.nombre}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <EstadoChip estado={bot.estado} />
          <span className="text-sm text-tinta-suave">
            {diasTexto(bot.dias)} en marcha{bot.ultima_actividad ? ` · última operación el ${momento(bot.ultima_actividad)}` : ""}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {bot.estado === "en_marcha" ? (
          <Boton onClick={() => void accion.ejecutar("parar")} disabled={accion.enCurso}>
            <CirclePause aria-hidden="true" className="h-5 w-5" />
            {accion.enCurso ? "Parando…" : "Parar"}
          </Boton>
        ) : (
          <Boton onClick={() => void accion.ejecutar("reanudar")} disabled={accion.enCurso}>
            <CirclePlay aria-hidden="true" className="h-5 w-5" />
            {accion.enCurso ? "Reanudando…" : "Reanudar"}
          </Boton>
        )}
        {bot.modo !== "real" ? (
          <Boton variante="peligro" onClick={onActivarReal}>
            <ShieldAlert aria-hidden="true" className="h-5 w-5" />
            Activar dinero real
          </Boton>
        ) : null}
        <Boton variante="peligro" onClick={() => setBorrar(true)}>
          <Trash2 aria-hidden="true" className="h-5 w-5" />
          Borrar
        </Boton>
      </div>
      {accion.error ? <ErrorApiVista error={accion.error} className="w-full" /> : null}
      <Hoja
        abierta={borrar}
        onCerrar={() => {
          borrado.limpiar();
          setBorrar(false);
        }}
        cerrable={!borrado.enCurso}
        titulo={`¿Borrar «${bot.nombre}»?`}
        bajada={
          bot.modo === "ficticio"
            ? "Se borran el bot, su registro de operaciones y sus eventos. Es dinero ficticio, pero no se puede deshacer."
            : `Se borran el bot, su registro de operaciones y sus eventos. No se puede deshacer. Lo que tenga comprado en ${nombreExchange(bot.exchange)} no se vende al borrarlo: compruébalo allí.`
        }
        pie={
          <div className="flex flex-wrap gap-3">
            <Boton variante="real" disabled={borrado.enCurso} onClick={() => void borrado.ejecutar()}>
              {borrado.enCurso ? "Borrando…" : "Sí, borrarlo"}
            </Boton>
            <Boton onClick={() => setBorrar(false)} disabled={borrado.enCurso}>
              Cancelar
            </Boton>
          </div>
        }
      >
        <div className="space-y-4 text-[0.9375rem] leading-relaxed text-tinta">
          <p>
            Ahora vale <strong className="cifras font-semibold">{usdc(bot.valor)}</strong> ({bot.operaciones} {bot.operaciones === 1 ? "operación" : "operaciones"} en {diasTexto(bot.dias)}).
          </p>
          {bot.estado === "en_marcha" ? <p>Si solo quieres que deje de operar, mejor <strong>pararlo</strong>: conserva lo que tiene y su historia.</p> : null}
          {borrado.error ? <ErrorApiVista error={borrado.error} /> : null}
        </div>
      </Hoja>
    </header>
  );
}

const ICONO_EVENTO: Record<EventoBot["tipo"], typeof Play> = { arranque: Play, parada: CirclePause, error: OctagonAlert, hueco: Clock, info: Info };
const NOMBRE_EVENTO: Record<EventoBot["tipo"], string> = { arranque: "Arranque", parada: "Parada", error: "Error", hueco: "Hueco", info: "Aviso" };

function FilaEvento({ evento }: { evento: EventoBot }) {
  const Icono = ICONO_EVENTO[evento.tipo];
  return (
    <li className="flex items-start gap-3 rounded-xl border border-linea bg-superficie px-4 py-3">
      <span
        className={clases(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          evento.tipo === "error" ? "bg-real-suave text-real-tinta" : evento.tipo === "hueco" ? "bg-pruebas-suave text-pruebas-tinta" : "bg-superficie-2 text-tinta-suave",
        )}
        aria-hidden="true"
      >
        <Icono className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <p className="text-[0.9375rem] text-tinta">
          <span className="font-semibold">{NOMBRE_EVENTO[evento.tipo]}.</span> {evento.texto}
        </p>
        <p className="text-sm text-tinta-suave">{momento(evento.at)}</p>
      </div>
    </li>
  );
}

function Operaciones({ operaciones, total }: { operaciones: readonly OperacionBot[]; total: number }) {
  const [todas, setTodas] = useState(false);
  const vistas = todas ? operaciones : operaciones.slice(0, 12);
  return (
    <Seccion titulo="Sus operaciones" bajada="Cada compra y venta con su porqué, la más reciente primero.">
      {operaciones.length ? (
        <>
          <ol className="divide-y divide-linea rounded-tarjeta border border-linea bg-superficie">
            {vistas.map((o, i) => (
              <li key={`${o.at}-${i}`} className="flex flex-wrap items-start gap-x-4 gap-y-1 px-4 py-3 sm:flex-nowrap">
                <span
                  className={clases(
                    "mt-0.5 inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-[0.8125rem] font-semibold",
                    o.lado === "compra" ? "bg-sube-suave text-sube-texto" : "bg-baja-suave text-baja-texto",
                  )}
                >
                  {o.lado === "compra" ? "Compra" : "Venta"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[0.9375rem] leading-relaxed text-tinta">{o.motivo}</p>
                  <p className="cifras text-sm text-tinta-suave">
                    {momento(o.at)} · {usdc(o.importe)} · comisión {formatoImporte(o.comision, { decimales: 2 })} USDC
                  </p>
                </div>
              </li>
            ))}
          </ol>
          {operaciones.length > 12 ? (
            <Boton tamano="compacto" variante="fantasma" onClick={() => setTodas((t) => !t)} aria-expanded={todas}>
              {todas ? "Ver solo las últimas" : `Ver las ${operaciones.length}${total > operaciones.length ? ` más recientes (de ${total})` : ""}`}
            </Boton>
          ) : null}
        </>
      ) : (
        <p className="text-[0.9375rem] text-tinta-suave">Aún no ha comprado ni vendido nada.</p>
      )}
    </Seccion>
  );
}
