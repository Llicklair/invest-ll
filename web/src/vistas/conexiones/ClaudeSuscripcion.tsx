"use client";

import { CircleCheck, LoaderCircle, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";
import { Aviso, Boton, Chip, ErrorApiVista, Esqueleto, Tarjeta } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";

const CADA_MS = 3000;
const ESPERA_MAX_MS = 180_000;

/** El estado de Claude y la acción de conectarlo; mientras se inicia sesión, pregunta cada 3 s. */
function useConexionClaude() {
  const [vuelta, setVuelta] = useState(0);
  const [esperando, setEsperando] = useState(false);
  const estado = useConsulta(`claude:${vuelta}`, () => pedir(api.GET("/api/claude")));
  const conectar = useAccion(async () => {
    const r = await pedir(api.POST("/api/claude/conectar"));
    setEsperando(true);
    return r;
  });

  useEffect(() => {
    if (!esperando) return;
    const t = window.setInterval(() => setVuelta((v) => v + 1), CADA_MS);
    const fin = window.setTimeout(() => setEsperando(false), ESPERA_MAX_MS);
    return () => {
      window.clearInterval(t);
      window.clearTimeout(fin);
    };
  }, [esperando]);

  const e = estado.datos;
  // Ya conectado con la suscripción: se deja de preguntar (se ajusta al pintar, no en un efecto).
  if (esperando && e?.con_suscripcion) setEsperando(false);
  const listo = e?.conectado === true && e.con_suscripcion;
  return { estado, e, conectar, esperando, listo };
}

/**
 * Lo mismo, en pequeño, para la barra de Mi plan: "Claude · Max" si está conectado (lleva a su
 * tarjeta en Conexiones) o un botón para conectarlo ahí mismo.
 */
export function ClaudeCompacto() {
  const { e, conectar, esperando, listo } = useConexionClaude();
  if (!e) return null;
  if (listo) {
    return (
      <Link
        href="/conexiones/#claude-suscripcion"
        title={`Claude conectado con tu suscripción${e.plan ? ` ${e.plan}` : ""}: lo usan ${e.usos.join(", ")}.`}
        className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-sube-suave px-3 text-sm font-semibold text-sube-texto"
      >
        <Sparkles aria-hidden="true" className="h-4 w-4" />
        Claude{e.plan ? ` · ${e.plan}` : ""}
      </Link>
    );
  }
  if (!e.instalado) {
    return (
      <Link href="/conexiones/#claude-suscripcion" className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-superficie-2 px-3 text-sm font-semibold text-tinta-suave">
        <Sparkles aria-hidden="true" className="h-4 w-4" />
        Claude sin instalar
      </Link>
    );
  }
  return (
    <Boton tamano="compacto" onClick={() => void conectar.ejecutar()} disabled={conectar.enCurso || esperando} title={conectar.error?.detalle}>
      {conectar.enCurso || esperando ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden="true" className="h-4 w-4" />}
      {esperando ? "Inicia sesión en la ventana…" : "Conectar Claude"}
    </Boton>
  );
}

/**
 * Claude con tu suscripción (docs/panel-v5.md): si Claude Code está conectado y con qué plan, y un
 * botón que abre su inicio de sesión en este equipo. Mientras se inicia sesión, la tarjeta pregunta
 * cada 3 s y se entera sola.
 */
export function ClaudeSuscripcion() {
  const { estado, e, conectar, esperando, listo } = useConexionClaude();
  return (
    <Tarjeta como="section" id="claude-suscripcion" aria-labelledby="titulo-claude" className="space-y-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-marca-suave text-marca" aria-hidden="true">
            <Sparkles className="h-5 w-5" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h2 id="titulo-claude" className="flex flex-wrap items-center gap-2 titular text-xl font-semibold text-tinta">
              Claude, con tu suscripción
              {e ? (
                listo ? (
                  <Chip tono="sube" icono={<CircleCheck className="h-3.5 w-3.5" />}>
                    Conectado{e.plan ? ` · plan ${e.plan}` : ""}
                  </Chip>
                ) : (
                  <Chip tono="neutro">{e.conectado ? "Conectado sin suscripción" : "Sin conectar"}</Chip>
                )
              ) : null}
            </h2>
            <p className="mt-1 text-[0.9375rem] leading-relaxed text-tinta-suave">
              Lo usan {e ? e.usos.join(", ").replace(/, ([^,]*)$/, " y $1") : "Pregunta, Mi plan y Diseñar con Claude"}. Gasta la cuota de tu suscripción de Claude
              (Pro o Max): no se paga aparte.
            </p>
          </div>
        </div>
        {e && !listo && e.instalado ? (
          <Boton variante="primario" onClick={() => void conectar.ejecutar()} disabled={conectar.enCurso || esperando}>
            {conectar.enCurso || esperando ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden="true" className="h-4 w-4" />}
            {esperando ? "Esperando…" : "Conectar con tu suscripción"}
          </Boton>
        ) : null}
      </div>

      {!e && estado.cargando ? <Esqueleto className="h-6 w-64" /> : null}
      {estado.error ? <ErrorApiVista error={estado.error} reintentar={estado.recargar} /> : null}
      {e?.aviso ? <Aviso tipo={e.instalado ? "aviso" : "info"}>{e.aviso}</Aviso> : null}
      {conectar.error ? <ErrorApiVista error={conectar.error} /> : null}
      {esperando && conectar.resultado ? (
        <Aviso tipo="info" vivo titulo="Inicia sesión en la ventana que se ha abierto">
          {conectar.resultado.texto}
        </Aviso>
      ) : null}
      {listo ? (
        <p className="text-sm text-tinta-suave">
          Para usar otra cuenta, cierra la sesión de Claude Code en una terminal (<code className="font-mono">claude auth logout</code>) y vuelve a conectar aquí.
        </p>
      ) : null}
    </Tarjeta>
  );
}
