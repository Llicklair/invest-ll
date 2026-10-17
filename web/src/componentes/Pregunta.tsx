"use client";

import { MessageCircleQuestionMark, SendHorizontal } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { api, ErrorApi, pedir } from "@/api/cliente";
import type { MensajeChat } from "@/api/tipos";
import { useGuardado } from "@/lib/almacen";
import { useAccion } from "@/lib/consulta";

import { Hoja } from "./Hoja";
import { Aviso, Boton, Cargando, ErrorApiVista, clases } from "./ui";

interface Conversacion {
  sesion: string | null;
  historial: MensajeChat[];
}

const VACIA: Conversacion = { sesion: null, historial: [] };

function leerConversacion(texto: string): Conversacion {
  try {
    const v: unknown = JSON.parse(texto);
    if (typeof v === "object" && v !== null && "historial" in v && Array.isArray((v as Conversacion).historial)) {
      const c = v as Conversacion;
      return { sesion: typeof c.sesion === "string" ? c.sesion : null, historial: c.historial };
    }
  } catch {
    // conversacion guardada ilegible: se empieza de cero
  }
  return VACIA;
}

const SUGERENCIAS = [
  "¿Qué significa que una estrategia «se mueva mucho»?",
  "¿Por qué me recomendáis tan poca cripto?",
  "¿Qué pasa si no hago lo que toca este mes?",
];

/**
 * Pregunta: hablar con Claude sobre TU situacion. No es una seccion sino un boton flotante en
 * todas las pantallas que abre una hoja (docs/panel-v2.md, seccion 3). Lee y explica; no puede
 * ejecutar nada. Gasta cuota de la suscripcion, y lo dice antes de cada envio.
 */
export function Pregunta() {
  const [abierta, setAbierta] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setAbierta(true)}
        className="boton-pregunta fixed right-4 bottom-[calc(80px+env(safe-area-inset-bottom))] z-30 inline-flex h-14 w-14 items-center justify-center gap-2 rounded-full border border-linea bg-superficie font-semibold text-tinta shadow-alta hover:bg-superficie-2 sm:w-auto sm:px-5 lg:right-8 lg:bottom-8"
        aria-label="Pregunta: habla con Claude sobre tu dinero"
        aria-haspopup="dialog"
      >
        <MessageCircleQuestionMark aria-hidden="true" className="h-6 w-6 text-marca sm:h-5 sm:w-5" strokeWidth={1.75} />
        <span className="hidden sm:inline">Pregunta</span>
      </button>
      <Hoja
        abierta={abierta}
        onCerrar={() => setAbierta(false)}
        titulo="Pregunta"
        bajada="Claude lee tu cartera, tu plan y tus datos (con sus fechas) y te lo explica. No puede comprar ni vender nada."
      >
        <Chat />
      </Hoja>
    </>
  );
}

function Chat() {
  const [guardada, guardar] = useGuardado("sesion", "invest-ll.chat", JSON.stringify(VACIA));
  const conversacion = useMemo(() => leerConversacion(guardada), [guardada]);
  const [pregunta, setPregunta] = useState("");
  const [pendiente, setPendiente] = useState<string | null>(null);
  const [sesionPerdida, setSesionPerdida] = useState(false);
  const campo = useRef<HTMLTextAreaElement>(null);

  const preguntar = useAccion(async (texto: string) => {
    setPendiente(texto);
    setSesionPerdida(false);
    try {
      const r = await pedir(api.POST("/api/chat", { body: { pregunta: texto, sesion: conversacion.sesion } }));
      guardar(JSON.stringify({ sesion: r.sesion, historial: r.historial } satisfies Conversacion));
      setPregunta("");
      return r;
    } catch (e) {
      // 404: la API ya no conoce esta sesion (se reinicio). Se olvida el id; lo hablado se queda a
      // la vista, pero Claude ya no lo recuerda.
      if (e instanceof ErrorApi && e.estado === 404 && conversacion.sesion) {
        guardar(JSON.stringify({ sesion: null, historial: conversacion.historial } satisfies Conversacion));
        setSesionPerdida(true);
      }
      throw e;
    } finally {
      setPendiente(null);
    }
  });

  const enviar = (e?: FormEvent) => {
    e?.preventDefault();
    const texto = pregunta.trim();
    if (texto && !preguntar.enCurso) void preguntar.ejecutar(texto);
  };
  const teclas = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  };

  return (
    <div className="flex min-h-full flex-col gap-4">
      <Aviso tipo="info">Cada pregunta gasta cuota de tu suscripción de Claude.</Aviso>

      {conversacion.historial.length === 0 && !pendiente ? (
        <div className="space-y-2">
          <p className="text-sm text-tinta-suave">Por ejemplo:</p>
          <ul className="space-y-2">
            {SUGERENCIAS.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => {
                    setPregunta(s);
                    campo.current?.focus();
                  }}
                  className="min-h-11 w-full rounded-xl border border-linea px-4 py-2.5 text-left text-[0.9375rem] text-tinta hover:bg-superficie-2"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <ol className="space-y-3" aria-label="Conversación" aria-live="polite">
        {conversacion.historial.map((m, i) => (
          <li
            key={i}
            className={clases(
              "max-w-[90%] rounded-2xl px-4 py-3 text-[0.9375rem] leading-relaxed",
              m.autor === "operador" ? "ml-auto rounded-br-md bg-marca text-marca-tinta" : "rounded-bl-md bg-superficie-2 text-tinta",
            )}
          >
            <span className="sr-only">{m.autor === "operador" ? "Tú: " : "Claude: "}</span>
            <div className="break-words whitespace-pre-wrap">{m.texto}</div>
          </li>
        ))}
        {pendiente ? (
          <li className="ml-auto max-w-[90%] rounded-2xl rounded-br-md bg-marca px-4 py-3 text-[0.9375rem] text-marca-tinta opacity-70">
            <span className="sr-only">Tú: </span>
            <div className="whitespace-pre-wrap">{pendiente}</div>
          </li>
        ) : null}
      </ol>
      {preguntar.enCurso ? <Cargando texto="Preguntando a Claude…" /> : null}
      {preguntar.error ? <ErrorApiVista error={preguntar.error} /> : null}
      {sesionPerdida ? (
        <Aviso tipo="aviso">
          Claude ya no recuerda esta conversación (la API se reinició). Tu próxima pregunta empezará una nueva.
        </Aviso>
      ) : null}

      {/* Fijo abajo de la hoja: el -bottom compensa el relleno del contenedor que hace scroll. */}
      <form
        onSubmit={enviar}
        className="sticky -bottom-5 -mx-5 mt-auto space-y-2 border-t border-linea bg-superficie px-5 pt-3 pb-5 lg:-bottom-6 lg:-mx-8 lg:px-8 lg:pb-6"
      >
        <label htmlFor="pregunta" className="sr-only">
          Tu pregunta
        </label>
        <div className="flex items-end gap-2">
          <textarea
            id="pregunta"
            ref={campo}
            rows={2}
            value={pregunta}
            onChange={(e) => setPregunta(e.target.value)}
            onKeyDown={teclas}
            className="min-h-12 w-full resize-none rounded-xl border border-linea-control/70 bg-superficie px-4 py-3 text-base text-tinta"
            placeholder="Escribe tu pregunta"
          />
          <button
            type="submit"
            disabled={!pregunta.trim() || preguntar.enCurso}
            aria-label="Enviar la pregunta (gasta cuota)"
            className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-marca text-marca-tinta disabled:opacity-40"
          >
            <SendHorizontal aria-hidden="true" className="h-5 w-5" />
          </button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-tinta-suave">
          <span>Intro envía · Mayús+Intro, salto de línea</span>
          {conversacion.historial.length ? (
            <Boton
              tamano="compacto"
              variante="fantasma"
              onClick={() => {
                guardar(null);
                preguntar.limpiar();
              }}
            >
              Empezar otra conversación
            </Boton>
          ) : null}
        </div>
      </form>
    </div>
  );
}
