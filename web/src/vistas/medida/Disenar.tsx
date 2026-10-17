"use client";

import { ArrowLeft, Bot, ChevronRight, SendHorizontal, Sparkles, Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { api, ErrorApi, pedir } from "@/api/cliente";
import type { DetalleEstrategia, MensajeDiseno, RespuestaDiseno } from "@/api/tipos";
import { Markdown } from "@/componentes/Markdown";
import { Aviso, BotonEnlace, Boton, CargandoLento, ErrorApiVista, Esqueleto, Tarjeta, clases } from "@/componentes/ui";
import { useGuardado } from "@/lib/almacen";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { hora, momento } from "@/lib/formato";
import { MiniCurva } from "@/vistas/bots/comun";

import { ChipEstadoEstrategia, LineaPrueba, nombreHerramienta, useConversaciones } from "./comun";

/** Un turno de Claude puede tardar "un par de minutos" (POST /api/medida/disenar): se espera hasta 6. */
const PLAZO_TURNO_MS = 6 * 60_000;

const EJEMPLOS = [
  "Compra ETH cuando rebote de su mínimo de 30 días y vende si cae un 8 %.",
  "Algo tranquilo con Bitcoin: que no llegue a caer más de un 15 %.",
  "Reparte entre BTC, ETH y SOL, pero quédate solo con las que suben en el último mes.",
];

type MapaHerramientas = Record<string, Record<string, string[]>>;

function leerMapa(texto: string): MapaHerramientas {
  try {
    const v: unknown = JSON.parse(texto);
    return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as MapaHerramientas) : {};
  } catch {
    return {};
  }
}

/**
 * Las herramientas que uso Claude en cada turno. La API solo las da para el ULTIMO turno
 * (`RespuestaDiseno.herramientas`; `MensajeDiseno` no las lleva), asi que se recuerdan en este
 * navegador por conversacion y por mensaje.
 */
function useHerramientas(): [MapaHerramientas, (sesion: string, indice: number, h: string[]) => void] {
  const [texto, fijar] = useGuardado("local", "invest-ll.disenos.herramientas", "{}");
  const mapa = useMemo(() => leerMapa(texto), [texto]);
  const anotar = (sesion: string, indice: number, h: string[]) => {
    const actual = leerMapa(texto);
    fijar(JSON.stringify({ ...actual, [sesion]: { ...(actual[sesion] ?? {}), [String(indice)]: h } }));
  };
  return [mapa, anotar];
}

function Esperando() {
  const [inicio] = useState(() => Date.now());
  const [ahora, setAhora] = useState(inicio);
  useEffect(() => {
    const t = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const s = Math.round((ahora - inicio) / 1000);
  const tiempo = s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  return (
    <li className="rounded-tarjeta border border-dashed border-linea-control/60 bg-superficie px-4 py-4 sm:px-5" role="status" aria-live="polite">
      <p className="flex items-center gap-2.5 text-[0.9375rem] font-semibold text-tinta">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-linea border-t-marca" aria-hidden="true" />
        Claude está trabajando
        <span className="cifras font-normal text-tinta-suave">· lleva {tiempo}</span>
      </p>
      <p className="mt-1.5 pl-[26px] text-sm leading-relaxed text-tinta-suave">
        Un turno puede tardar un par de minutos: escribe la estrategia, la valida y la prueba sobre el pasado con velas de verdad. Cuando termine verás su respuesta y
        las herramientas que usó. No cierres esta pestaña mientras tanto.
      </p>
    </li>
  );
}

function Mensaje({ m, herramientas, ultimo }: { m: MensajeDiseno; herramientas: string[] | undefined; ultimo: boolean }) {
  if (m.autor === "marcos") {
    return (
      <li className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-marca px-4 py-3 text-[0.9375rem] leading-relaxed text-marca-tinta">
        <span className="sr-only">Tú, a las {hora(m.at)}: </span>
        <p className="break-words whitespace-pre-wrap">{m.texto}</p>
      </li>
    );
  }
  return (
    <li className="rounded-tarjeta border border-linea bg-superficie px-4 py-4 sm:px-5" data-ultimo={ultimo ? "" : undefined}>
      <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-tinta">
        <Sparkles aria-hidden="true" className="h-4 w-4 text-marca" />
        Claude <span className="font-normal text-tinta-suave">· {hora(m.at)}</span>
      </p>
      <Markdown texto={m.texto} className="text-[0.9375rem] leading-relaxed text-tinta" />
      {herramientas?.length ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-linea pt-3 text-xs text-tinta-suave">
          <Wrench aria-hidden="true" className="h-3.5 w-3.5" />
          <span className="font-medium">Lo que hizo:</span>
          {herramientas.map((h, i) => (
            <span key={`${h}-${i}`} className="rounded-full bg-superficie-2 px-2 py-0.5">
              {nombreHerramienta(h)}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}

/** La estrategia que va saliendo de la conversacion, con su ultima prueba. */
function LaQueSale({ detalle, cargando }: { detalle: DetalleEstrategia | null; cargando: boolean }) {
  if (!detalle) {
    return (
      <Tarjeta className="p-5">
        <p className="text-sm font-semibold text-tinta-suave">La estrategia que va saliendo</p>
        {cargando ? <Esqueleto className="mt-3 h-40" /> : <p className="mt-2 text-[0.9375rem] text-tinta-suave">Aquí aparecerá en cuanto Claude la escriba, con su última prueba sobre el pasado.</p>}
      </Tarjeta>
    );
  }
  const p = detalle.ultima_prueba;
  return (
    <Tarjeta className={clases("space-y-4 p-5", cargando && "opacity-70")}>
      <div>
        <p className="text-sm font-semibold text-tinta-suave">La estrategia que va saliendo</p>
        <h2 className="titular mt-1 text-xl leading-snug font-semibold text-tinta">{detalle.nombre}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <ChipEstadoEstrategia estado={detalle.estado} />
          <span className="text-sm text-tinta-suave">Versión {detalle.version}</span>
        </div>
      </div>
      <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-tinta marker:text-tinta-suave">
        {detalle.reglas_en_llano.slice(0, 4).map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <div className="space-y-2 border-t border-linea pt-3">
        <p className="text-sm font-semibold text-tinta">Su última prueba</p>
        <LineaPrueba p={p} />
        {p ? (
          <div>
            <MiniCurva curva={p.curva} capital={Number(p.capital)} alto={64} />
            <p className="mt-1 text-xs text-tinta-suave">La línea fina es lo que puso: {formatoImporte(p.capital, { decimales: 0 })} USDC.</p>
          </div>
        ) : null}
        {p?.aviso_sobreajuste ? (
          <Aviso tipo="aviso" className="text-sm">
            {p.aviso_sobreajuste}
          </Aviso>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2 border-t border-linea pt-3">
        <BotonEnlace href={`/estrategias/medida/ficha/?id=${encodeURIComponent(detalle.id)}`} tamano="compacto">
          Ver su ficha <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </BotonEnlace>
        <BotonEnlace href={`/bots/nuevo/?estrategia=${encodeURIComponent(detalle.id)}`} tamano="compacto" variante="fantasma">
          <Bot aria-hidden="true" className="h-4 w-4" /> Desplegar como bot
        </BotonEnlace>
      </div>
    </Tarjeta>
  );
}

/**
 * Disenar con Claude (docs/panel-v4-real.md §2): una conversacion donde dices lo que quieres y
 * Claude, con las herramientas del conector, escribe la estrategia, la valida, la prueba sobre el
 * pasado y te ensena el resultado con sus pegas. Gasta cuota, y lo dice; puede desplegar en
 * ficticio pero NUNCA activar dinero real. Al lado, la estrategia que va saliendo.
 */
export function Disenar() {
  const router = useRouter();
  const sesion = useSearchParams().get("sesion");
  const [, recordar] = useConversaciones();
  const [herramientas, anotar] = useHerramientas();
  const [local, setLocal] = useState<RespuestaDiseno | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [pendiente, setPendiente] = useState<string | null>(null);
  const [turnos, setTurnos] = useState(0);
  const lista = useRef<HTMLOListElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  const guardada = useConsulta(sesion && (!local || local.sesion !== sesion) ? `diseno:${sesion}` : null, () =>
    pedir(api.GET("/api/medida/disenar/{sesion}", { params: { path: { sesion: sesion ?? "" } } })),
  );
  const conv: RespuestaDiseno | null = local && (!sesion || local.sesion === sesion) ? local : sesion ? guardada.datos : null;
  const historial = conv?.historial ?? [];
  // Un turno sin estrategia (una pregunta, una negativa) deja a la vista la de antes, de ESTA conversacion.
  const [ultima, setUltima] = useState<{ sesion: string; id: string } | null>(null);
  const estrategiaId = conv?.estrategia ?? (conv && ultima?.sesion === conv.sesion ? ultima.id : null);
  const detalle = useConsulta(estrategiaId ? `medida:${estrategiaId}:${turnos}` : null, () =>
    pedir(api.GET("/api/medida/{estrategia_id}", { params: { path: { estrategia_id: estrategiaId ?? "" } } })),
  );

  const enviar = useAccion(async (texto: string) => {
    setPendiente(texto);
    const control = new AbortController();
    const plazo = window.setTimeout(() => control.abort(), PLAZO_TURNO_MS);
    try {
      const r = await pedir(api.POST("/api/medida/disenar", { body: { mensaje: texto, sesion: conv?.sesion ?? null }, signal: control.signal }));
      setLocal(r);
      setMensaje("");
      setTurnos((t) => t + 1);
      if (r.estrategia) setUltima({ sesion: r.sesion, id: r.estrategia });
      const indice = r.historial.length - 1;
      anotar(r.sesion, indice, r.herramientas);
      recordar({ sesion: r.sesion, titulo: r.historial.find((m) => m.autor === "marcos")?.texto.slice(0, 90) ?? texto.slice(0, 90), at: new Date().toISOString() });
      if (r.sesion !== sesion) router.replace(`/estrategias/medida/disenar/?sesion=${encodeURIComponent(r.sesion)}`, { scroll: false });
      return r;
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === null && control.signal.aborted) {
        throw new ErrorApi(null, "Claude no ha terminado en 6 minutos. Puede que siga trabajando: vuelve a abrir esta conversación dentro de un rato (lo hablado queda guardado).");
      }
      throw e;
    } finally {
      window.clearTimeout(plazo);
      setPendiente(null);
    }
  });

  // Al llegar la respuesta, se lleva a la vista su principio (no el final: se lee de arriba abajo).
  useEffect(() => {
    if (!turnos) return;
    lista.current?.querySelector<HTMLElement>("[data-ultimo]")?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [turnos]);

  const mandar = (e?: FormEvent) => {
    e?.preventDefault();
    const texto = mensaje.trim();
    if (texto && !enviar.enCurso) void enviar.ejecutar(texto);
  };
  const teclas = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      mandar();
    }
  };

  const perdida = guardada.error?.estado === 404;
  const indiceUltimoClaude = historial.reduce((u, m, i) => (m.autor === "claude" ? i : u), -1);
  const herramientasDe = (i: number): string[] | undefined => {
    const recordadas = conv ? herramientas[conv.sesion]?.[String(i)] : undefined;
    if (recordadas) return recordadas;
    return i === indiceUltimoClaude ? conv?.herramientas : undefined;
  };

  return (
    <div className="space-y-6">
      <Link href="/estrategias/medida/" className="inline-flex min-h-11 items-center gap-1.5 text-[0.9375rem] font-medium text-marca hover:underline">
        <ArrowLeft aria-hidden="true" className="h-4 w-4" /> A medida
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="titular text-[2rem] leading-tight font-semibold text-tinta lg:text-[2.5rem]">Diseñar con Claude</h1>
          <p className="mt-2 text-base leading-relaxed text-tinta-suave lg:text-lg">
            Dile qué quieres con tus palabras. Claude escribe la estrategia, la prueba sobre el pasado y te enseña cómo le habría ido, con sus pegas.
          </p>
        </div>
        {conv && !enviar.enCurso ? (
          <Boton
            tamano="compacto"
            onClick={() => {
              setLocal(null);
              setUltima(null);
              setMensaje("");
              enviar.limpiar();
              router.push("/estrategias/medida/disenar/");
            }}
          >
            Empezar otra conversación
          </Boton>
        ) : null}
      </header>

      <Aviso tipo="info" titulo="Antes de escribir">
        Cada mensaje gasta cuota de tu suscripción de Claude. Claude puede escribir y probar estrategias, y desplegarlas en un bot con dinero ficticio; <strong className="font-semibold">nunca puede activar dinero real ni subir límites</strong>: eso solo lo haces tú, desde la ficha del bot.
      </Aviso>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-8">
        <section aria-label="Conversación" className="min-w-0 space-y-4">
          {sesion && !conv && guardada.cargando ? <CargandoLento texto="Abriendo la conversación…" lento="Sigue abriendo la conversación…" /> : null}
          {perdida ? (
            <Aviso tipo="aviso" titulo="Esa conversación ya no existe">
              {guardada.error?.detalle} Puedes empezar otra: tus estrategias siguen en la biblioteca.
            </Aviso>
          ) : guardada.error ? (
            <ErrorApiVista error={guardada.error} reintentar={guardada.recargar} prefijo="No se pudo abrir la conversación:" />
          ) : null}

          {!historial.length && !pendiente && !(sesion && guardada.cargando) ? (
            <div className="space-y-2">
              <p className="text-sm text-tinta-suave">Por ejemplo:</p>
              <ul className="space-y-2">
                {EJEMPLOS.map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      onClick={() => {
                        setMensaje(s);
                        campo.current?.focus();
                      }}
                      className="min-h-11 w-full rounded-xl border border-linea bg-superficie px-4 py-2.5 text-left text-[0.9375rem] text-tinta hover:bg-superficie-2"
                    >
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <ol ref={lista} className="space-y-3" role="log" aria-label="Mensajes" aria-live="polite">
            {historial.map((m, i) => (
              <Mensaje key={`${m.at}-${i}`} m={m} herramientas={m.autor === "claude" ? herramientasDe(i) : undefined} ultimo={i === indiceUltimoClaude} />
            ))}
            {pendiente ? (
              <li className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-marca px-4 py-3 text-[0.9375rem] text-marca-tinta opacity-80">
                <span className="sr-only">Tú: </span>
                <p className="break-words whitespace-pre-wrap">{pendiente}</p>
              </li>
            ) : null}
            {pendiente ? <Esperando /> : null}
          </ol>
          {enviar.error ? (
            <ErrorApiVista
              error={enviar.error}
              prefijo="Claude no pudo responder:"
              reintentar={mensaje.trim() ? () => void enviar.ejecutar(mensaje.trim()) : undefined}
            />
          ) : null}

          <form onSubmit={mandar} className="space-y-2 rounded-tarjeta border border-linea bg-superficie p-3 sm:p-4">
            <label htmlFor="mensaje-diseno" className="text-[0.9375rem] font-medium text-tinta">
              {historial.length ? "Tu respuesta" : "¿Qué quieres que haga tu estrategia?"}
            </label>
            <div className="flex items-end gap-2">
              <textarea
                id="mensaje-diseno"
                ref={campo}
                rows={3}
                value={mensaje}
                onChange={(e) => setMensaje(e.target.value)}
                onKeyDown={teclas}
                disabled={enviar.enCurso || perdida}
                aria-describedby="mensaje-diseno-ayuda"
                className="min-h-12 w-full resize-y rounded-xl border border-linea-control/70 bg-superficie px-4 py-3 text-base text-tinta disabled:opacity-60"
                placeholder={historial.length ? "Por ejemplo: pruébala con la mitad del capital" : "Con tus palabras, sin jerga"}
              />
              <button
                type="submit"
                disabled={!mensaje.trim() || enviar.enCurso || perdida}
                aria-label="Enviar a Claude (gasta cuota)"
                className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-marca text-marca-tinta disabled:opacity-40"
              >
                <SendHorizontal aria-hidden="true" className="h-5 w-5" />
              </button>
            </div>
            <p id="mensaje-diseno-ayuda" className="text-sm text-tinta-suave">
              Intro envía · Mayús+Intro, salto de línea · gasta cuota{conv ? ` · conversación del ${momento(historial[0]?.at)}` : ""}
            </p>
          </form>
        </section>

        <aside aria-label="La estrategia que va saliendo" className="min-w-0 space-y-3 lg:sticky lg:top-8">
          <LaQueSale detalle={detalle.datos} cargando={detalle.cargando} />
          {detalle.error ? <ErrorApiVista error={detalle.error} reintentar={detalle.recargar} /> : null}
          {!estrategiaId && conv ? (
            <Boton tamano="compacto" variante="fantasma" onClick={() => router.push("/estrategias/medida/")}>
              Ver tu biblioteca
            </Boton>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
