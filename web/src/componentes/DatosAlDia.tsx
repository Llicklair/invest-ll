"use client";

import { CircleCheck, CircleDashed, CircleX, Database, RefreshCw } from "lucide-react";
import { useEffect, useRef } from "react";

import { api, pedir, type ErrorApi } from "@/api/cliente";
import type { EstadoDatos, FuenteDatos, PasoDatos, TrabajoDatos } from "@/api/tipos";
import { useEstado } from "@/contexto/estado";
import { useAccion, useConsulta } from "@/lib/consulta";
import { fecha, hora, momento } from "@/lib/formato";

import { Aviso, Boton, Chip, ErrorApiVista, Esqueleto, Nota, Tarjeta, clases } from "./ui";

/** Cada cuanto se pregunta como va una actualizacion en marcha. */
const SONDEO_MS = 2500;

interface Datos {
  datos: EstadoDatos | null;
  error: ErrorApi | null;
  cargando: boolean;
  recargar: () => void;
  actualizar: () => void;
  errorActualizar: ErrorApi | null;
  pidiendo: boolean;
}

/**
 * `GET /api/datos` y "Actualizar ahora" (`POST /api/datos/actualizar`, contrato v2.1). Mientras
 * hay una actualizacion en marcha se vuelve a preguntar cada pocos segundos; al terminar, todo el
 * panel relee lo que dependa de los datos (`refrescarDatos`). Fuera de eso, nada se refresca solo.
 */
export function useDatos(): Datos {
  const { versionDatos, refrescarDatos } = useEstado();
  const consulta = useConsulta(`datos-al-dia:${versionDatos}`, () => pedir(api.GET("/api/datos")));
  const enMarcha = consulta.datos?.trabajo?.en_marcha === true;
  const antes = useRef(enMarcha);
  const { recargar } = consulta;

  useEffect(() => {
    if (!enMarcha || consulta.cargando) return;
    const t = window.setTimeout(recargar, SONDEO_MS);
    return () => window.clearTimeout(t);
  }, [enMarcha, consulta.cargando, consulta.datos, recargar]);

  useEffect(() => {
    // Acaba de terminar: las mesas, las estrategias y el plan se calculan con datos nuevos.
    if (antes.current && !enMarcha && consulta.datos) refrescarDatos();
    antes.current = enMarcha;
  }, [enMarcha, consulta.datos, refrescarDatos]);

  const pedirActualizar = useAccion(async () => {
    try {
      return await pedir(api.POST("/api/datos/actualizar"));
    } finally {
      // Tambien con un 409 ("ya hay una en marcha"): lo que hay que ensenar es esa, paso a paso.
      recargar();
    }
  });

  return {
    datos: consulta.datos,
    error: consulta.error,
    cargando: consulta.cargando,
    recargar,
    actualizar: () => void pedirActualizar.ejecutar(),
    errorActualizar: pedirActualizar.error,
    pidiendo: pedirActualizar.enCurso,
  };
}

function cuando(f: FuenteDatos): string {
  if (!f.hasta) return "Sin datos todavía";
  const hace = f.dias === null ? "" : f.dias === 0 ? " · de hoy" : f.dias === 1 ? " · de ayer" : ` · hace ${f.dias} días`;
  return `Hasta el ${fecha(f.hasta)}${hace}`;
}

function IconoPaso({ estado }: { estado: PasoDatos["estado"] }) {
  if (estado === "en_marcha") {
    return <span className="mt-0.5 inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-linea border-t-marca" aria-hidden="true" />;
  }
  const Icono = estado === "bien" ? CircleCheck : estado === "mal" ? CircleX : CircleDashed;
  return (
    <Icono
      aria-hidden="true"
      strokeWidth={1.75}
      className={clases("mt-0.5 h-5 w-5 shrink-0", estado === "bien" ? "text-sube-texto" : estado === "mal" ? "text-real-tinta" : "text-tinta-suave")}
    />
  );
}

const TEXTO_PASO: Record<PasoDatos["estado"], string> = {
  pendiente: "en espera",
  en_marcha: "en marcha",
  bien: "hecho",
  mal: "ha fallado",
};

/** El progreso de una actualizacion, paso a paso (o como acabo la ultima). */
export function Progreso({ trabajo, compacto = false }: { trabajo: TrabajoDatos; compacto?: boolean }) {
  const hechos = trabajo.pasos.filter((p) => p.estado === "bien" || p.estado === "mal").length;
  const mal = trabajo.pasos.filter((p) => p.estado === "mal");
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <p className="text-[0.9375rem] text-tinta">
        {trabajo.en_marcha ? (
          <>
            <strong className="font-semibold">Actualizando…</strong> paso {Math.min(hechos + 1, trabajo.pasos.length)} de{" "}
            {trabajo.pasos.length}. Empezó a las {hora(trabajo.empezado)}; puedes seguir usando el panel.
          </>
        ) : (
          <>
            <strong className="font-semibold">{mal.length ? "La última actualización acabó con fallos" : "Última actualización"}</strong>
            {trabajo.terminado ? `: terminó el ${momento(trabajo.terminado)}.` : "."}
          </>
        )}
      </p>
      <ol className={clases("space-y-2", compacto && "text-sm")}>
        {trabajo.pasos.map((p) => (
          <li key={p.nombre} className="flex items-start gap-2.5">
            <IconoPaso estado={p.estado} />
            <div className="min-w-0 [overflow-wrap:anywhere]">
              <p className={clases("text-tinta", p.estado === "pendiente" && "text-tinta-suave")}>
                {p.nombre}
                <span className="sr-only">: {TEXTO_PASO[p.estado]}</span>
              </p>
              {p.detalle ? <p className={clases("text-sm", p.estado === "mal" ? "text-real-tinta" : "text-tinta-suave")}>{p.detalle}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * Ajustes · Datos (y Mercado): de cuando son las tres fuentes que usa el panel y "Actualizar
 * ahora", con el progreso paso a paso. Sustituye a "Actualizar todos los historicos".
 */
export function SeccionDatos() {
  const d = useDatos();
  const datos = d.datos;
  const enMarcha = datos?.trabajo?.en_marcha === true;
  return (
    <div className="space-y-4">
      {d.error && !datos ? <ErrorApiVista error={d.error} prefijo="No se pudo saber de cuándo son los datos:" reintentar={d.recargar} /> : null}
      {!datos && d.cargando ? <Esqueleto className="h-40" /> : null}
      {datos ? (
        <Tarjeta className="space-y-5 p-5 sm:p-6">
          <ul className="divide-y divide-linea">
            {datos.fuentes.map((f) => (
              <li key={f.clave} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3 first:pt-0">
                <div className="min-w-0">
                  <p className="font-medium text-tinta">{f.nombre}</p>
                  <p className="cifras text-sm text-tinta-suave">{cuando(f)}</p>
                </div>
                <Chip tono={f.al_dia ? "sube" : "pruebas"}>{f.al_dia ? "Al día" : "No son de hoy"}</Chip>
              </li>
            ))}
          </ul>
          {datos.aviso && !enMarcha ? <Aviso tipo="aviso">{datos.aviso}</Aviso> : null}
          {datos.trabajo ? (
            <div className="rounded-xl bg-superficie-2 px-4 py-4">
              <Progreso trabajo={datos.trabajo} />
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Boton variante={datos.al_dia ? "secundario" : "primario"} onClick={d.actualizar} disabled={enMarcha || d.pidiendo}>
              <RefreshCw aria-hidden="true" className={clases("h-4 w-4", (enMarcha || d.pidiendo) && "animate-spin")} />
              {enMarcha ? "Actualizando…" : "Actualizar ahora"}
            </Boton>
            {!enMarcha ? <p className="text-sm text-tinta-suave">Tarda unos minutos.</p> : null}
          </div>
          {d.errorActualizar ? <ErrorApiVista error={d.errorActualizar} prefijo="No se empezó:" /> : null}
          <Nota>
            Solo descarga precios públicos de mercado (de Yahoo Finance y de Binance): no envía nada ni toca tu dinero. Las cuentas
            del panel se hacen siempre con precios de cierre descargados, nunca en vivo.
          </Nota>
        </Tarjeta>
      ) : null}
    </div>
  );
}

/**
 * Inicio: un aviso discreto solo si algo no esta al dia (o mientras se actualiza), con su boton.
 * Si todo esta al dia no se dice nada: no es una notificacion.
 */
export function AvisoDatos() {
  const d = useDatos();
  const datos = d.datos;
  if (!datos) return null;
  const trabajo = datos.trabajo;
  if (trabajo?.en_marcha) {
    return (
      <div className="rounded-xl border border-linea bg-superficie px-4 py-3">
        <Progreso trabajo={trabajo} compacto />
      </div>
    );
  }
  if (datos.al_dia) return null;
  const fallidos = trabajo ? trabajo.pasos.filter((p) => p.estado === "mal").map((p) => p.nombre) : [];
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 rounded-xl border border-linea bg-superficie px-4 py-3">
      <p className="flex min-w-0 flex-1 basis-64 items-start gap-2.5 text-[0.9375rem] text-tinta [overflow-wrap:anywhere]">
        <Database aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-tinta-suave" strokeWidth={1.75} />
        <span>
          {datos.aviso ?? "Algunos precios no son de hoy."}
          {fallidos.length ? ` La última actualización no pudo con: ${fallidos.join(", ").toLowerCase()}.` : ""}
        </span>
      </p>
      <Boton variante="secundario" tamano="compacto" onClick={d.actualizar} disabled={d.pidiendo}>
        <RefreshCw aria-hidden="true" className={clases("h-4 w-4", d.pidiendo && "animate-spin")} />
        Actualizar ahora
      </Boton>
      {d.errorActualizar ? <ErrorApiVista className="basis-full" error={d.errorActualizar} prefijo="No se empezó:" /> : null}
    </div>
  );
}
