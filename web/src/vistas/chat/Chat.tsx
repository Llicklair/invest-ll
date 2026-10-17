"use client";

import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";

import { api, ErrorApi, pedir } from "@/api/cliente";
import type { MensajeChat } from "@/api/tipos";
import { Aviso, Boton, Cargando, ErrorApiVista, Nota, clases } from "@/componentes/ui";
import { useGuardado } from "@/lib/almacen";
import { useAccion } from "@/lib/consulta";

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

/**
 * Hablar con Claude sobre TU situacion. Lee y explica; no puede ejecutar nada. El id de sesion
 * se conserva (en esta pestana del navegador) para que la conversacion siga entre mensajes.
 */
export function Chat() {
  const [guardada, guardar] = useGuardado("sesion", "invest-ll.chat", JSON.stringify(VACIA));
  const conversacion = useMemo(() => leerConversacion(guardada), [guardada]);
  const [pregunta, setPregunta] = useState("");
  const [pendiente, setPendiente] = useState<string | null>(null);

  const [sesionPerdida, setSesionPerdida] = useState(false);
  const preguntar = useAccion(async (texto: string) => {
    setPendiente(texto);
    setSesionPerdida(false);
    try {
      const r = await pedir(api.POST("/api/chat", { body: { pregunta: texto, sesion: conversacion.sesion } }));
      guardar(JSON.stringify({ sesion: r.sesion, historial: r.historial } satisfies Conversacion));
      setPregunta("");
      return r;
    } catch (e) {
      // 404: la API ya no conoce esta sesion (se reinicio). Se olvida el id para que el proximo
      // mensaje abra una nueva; lo hablado se queda a la vista, pero Claude ya no lo recuerda.
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-semibold text-tinta">Chat</h1>
        {conversacion.sesion ? (
          <Boton
            className="min-h-7 px-2 py-0.5 text-xs"
            onClick={() => {
              guardar(null);
              preguntar.limpiar();
            }}
          >
            Empezar otra conversación
          </Boton>
        ) : null}
      </div>
      <Nota>
        Claude lee tu cartera, tus triggers y tus datos (con sus fechas). <strong className="text-tinta">NO puede ejecutar
        nada</strong>: propone comandos y ejecutarlos es cosa tuya. <strong className="text-tinta">Cada mensaje gasta cuota
        de tu suscripción.</strong>
      </Nota>

      <ol className="space-y-3" aria-label="Conversación" aria-live="polite">
        {conversacion.historial.map((m, i) => (
          <li
            key={i}
            className={clases(
              "max-w-3xl rounded-md border px-3 py-2 text-sm",
              m.autor === "operador" ? "ml-auto border-borde bg-superficie-2" : "border-borde bg-superficie",
            )}
          >
            <div className="mb-0.5 text-xs font-semibold text-tinta-2">{m.autor === "operador" ? "Tú" : "Claude"}</div>
            <div className="break-words whitespace-pre-wrap">{m.texto}</div>
          </li>
        ))}
        {pendiente ? (
          <li className="ml-auto max-w-3xl rounded-md border border-borde bg-superficie-2 px-3 py-2 text-sm opacity-70">
            <div className="mb-0.5 text-xs font-semibold text-tinta-2">Tú</div>
            <div className="whitespace-pre-wrap">{pendiente}</div>
          </li>
        ) : null}
      </ol>
      {preguntar.enCurso ? <Cargando texto="Preguntando a Claude (tu suscripción)…" /> : null}
      {preguntar.error ? <ErrorApiVista error={preguntar.error} /> : null}
      {sesionPerdida ? (
        <Aviso tipo="aviso">
          La API ya no conoce esa sesión de chat. Tu próxima pregunta abrirá una nueva: lo de arriba sigue a la vista,
          pero Claude no lo recordará.
        </Aviso>
      ) : null}

      <form onSubmit={enviar} className="space-y-2">
        <label htmlFor="pregunta" className="text-sm font-medium">
          Pregunta sobre tu cartera, tus datos o qué comando usar
        </label>
        <textarea
          id="pregunta"
          rows={3}
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          onKeyDown={teclas}
          className="w-full rounded-md border border-borde bg-superficie px-3 py-2 text-sm text-tinta"
          placeholder="¿Por qué ha saltado el trigger de GLD?"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Boton type="submit" variante="primario" disabled={!pregunta.trim() || preguntar.enCurso}>
            Preguntar (gasta cuota)
          </Boton>
          <span className="text-xs text-tinta-2">
            Intro envía · Mayús+Intro, salto de línea
            {conversacion.sesion ? ` · sesión ${conversacion.sesion}` : ""}
          </span>
        </div>
      </form>
    </div>
  );
}
