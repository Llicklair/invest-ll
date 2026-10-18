"use client";

import { CirclePlay, LoaderCircle, Power, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { components } from "@/api/esquema";
import { Boton, ErrorApiVista, Esqueleto, Tarjeta, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { momento } from "@/lib/formato";

type EstadoMotor = components["schemas"]["EstadoMotor"];

const CADA_MS = 15_000;

function Interruptor({ etiqueta, ayuda, activo, onCambio, ocupado }: { etiqueta: string; ayuda: string; activo: boolean; onCambio: (v: boolean) => void; ocupado: boolean }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl px-1 py-1 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-foco">
      <input type="checkbox" className="peer sr-only" checked={activo} disabled={ocupado} onChange={(e) => onCambio(e.target.checked)} />
      <span aria-hidden="true" className={clases("relative mt-0.5 inline-flex h-6 w-10 shrink-0 rounded-full transition-colors", activo ? "bg-marca" : "bg-linea-control/50")}>
        <span className={clases("absolute top-0.5 h-5 w-5 rounded-full bg-superficie shadow transition-transform", activo ? "translate-x-[18px]" : "translate-x-0.5")} />
      </span>
      <span>
        <span className="block text-[0.9375rem] font-medium text-tinta">{etiqueta}</span>
        <span className="block text-sm text-tinta-suave">{ayuda}</span>
      </span>
    </label>
  );
}

/**
 * El motor de los bots (docs/panel-v5.md §8): vive aparte del panel y sigue aunque cierres esta
 * ventana. Aquí se ve si está en marcha, se arranca, se reinicia para traer código nuevo y se
 * eligen sus opciones (arrancar con Windows y que el PC no se duerma con bots en marcha).
 */
export function TarjetaMotor() {
  const [vuelta, setVuelta] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => {
      if (!document.hidden) setVuelta((v) => v + 1);
    }, CADA_MS);
    return () => window.clearInterval(t);
  }, []);
  const consulta = useConsulta(`motor:${vuelta}`, () => pedir(api.GET("/api/motor")));
  const [propio, setPropio] = useState<{ e: EstadoMotor; vuelta: number } | null>(null);
  const accion = useAccion(async (que: "arrancar" | "reiniciar") => {
    const e = que === "arrancar" ? await pedir(api.POST("/api/motor/arrancar")) : await pedir(api.POST("/api/motor/reiniciar"));
    setPropio({ e, vuelta });
    return e;
  });
  const opciones = useAccion(async (cambio: components["schemas"]["OpcionesMotor"]) => {
    const e = await pedir(api.PUT("/api/motor/opciones", { body: cambio }));
    setPropio({ e, vuelta });
    return e;
  });
  const e = propio && propio.vuelta === vuelta ? propio.e : consulta.datos;

  if (!e) return consulta.error ? <ErrorApiVista error={consulta.error} reintentar={consulta.recargar} /> : <Esqueleto className="h-28" />;
  const ocupado = accion.enCurso || opciones.enCurso;
  return (
    <Tarjeta como="section" aria-labelledby="titulo-motor" className={clases("space-y-4 p-5", !e.en_marcha && "border-real/40")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="titulo-motor" className="flex flex-wrap items-center gap-2 text-[0.9375rem] font-semibold text-tinta">
            <span aria-hidden="true" className={clases("h-2.5 w-2.5 rounded-full", e.en_marcha ? "bg-sube animate-pulse motion-reduce:animate-none" : "bg-real")} />
            {e.en_marcha ? "El motor de los bots está en marcha" : "El motor de los bots está parado"}
            {e.en_marcha && e.desde ? <span className="font-normal text-tinta-suave">· desde el {momento(e.desde)}</span> : null}
          </h2>
          <p className="mt-1 text-[0.9375rem] text-tinta-suave">{e.texto}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!e.en_marcha ? (
            <Boton variante="primario" disabled={ocupado} onClick={() => void accion.ejecutar("arrancar")}>
              {accion.enCurso ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <CirclePlay aria-hidden="true" className="h-4 w-4" />}
              {accion.enCurso ? "Arrancando…" : "Arrancar el motor"}
            </Boton>
          ) : e.codigo_nuevo ? (
            <Boton disabled={ocupado} onClick={() => void accion.ejecutar("reiniciar")} title="Los bots se paran unos segundos y lo apuntan como hueco">
              {accion.enCurso ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden="true" className="h-4 w-4" />}
              {accion.enCurso ? "Reiniciando…" : "Reiniciar con el código nuevo"}
            </Boton>
          ) : null}
        </div>
      </div>
      {e.en_marcha && e.codigo_nuevo ? (
        <p className="rounded-xl bg-pruebas-suave px-3 py-2 text-sm text-pruebas-tinta">
          El código del panel cambió después de arrancar el motor: lo nuevo de los bots no se usa hasta reiniciarlo (se paran unos segundos).
        </p>
      ) : null}
      <div className="grid gap-2 border-t border-linea pt-3 sm:grid-cols-2">
        <Interruptor
          etiqueta="Arrancar con Windows"
          ayuda="Al iniciar sesión, el motor arranca solo, oculto: no hace falta abrir el panel."
          activo={e.arranca_con_windows}
          ocupado={ocupado}
          onCambio={(v) => void opciones.ejecutar({ arranca_con_windows: v })}
        />
        <Interruptor
          etiqueta="Que el PC no se duerma con bots en marcha"
          ayuda="Mientras haya algún bot en marcha, Windows no se suspende solo (la pantalla sí se apaga)."
          activo={e.mantener_despierto}
          ocupado={ocupado}
          onCambio={(v) => void opciones.ejecutar({ mantener_despierto: v })}
        />
      </div>
      <p className="text-xs leading-relaxed text-tinta-suave">
        <Power aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />
        Apagado o dormido, el ordenador no opera: al volver, cada bot apunta el hueco y sigue donde estaba. En una terminal: <code className="font-mono">invest-ll-motor</code>{" "}
        (estado, arrancar, parar, reiniciar).
      </p>
      {accion.error ? <ErrorApiVista error={accion.error} /> : null}
      {opciones.error ? <ErrorApiVista error={opciones.error} /> : null}
    </Tarjeta>
  );
}
