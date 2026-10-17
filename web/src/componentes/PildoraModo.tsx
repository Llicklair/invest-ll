"use client";

import { Calculator, CircleQuestionMark, FlaskConical, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { NOMBRE_MODO, useModo } from "@/contexto/modo";

import { clases } from "./ui";

/**
 * El modo, siempre a la vista (docs/panel-v2.md, seccion 3): Simulacion / Pruebas / Dinero real.
 * Lleva a Ajustes · Conexion, que es donde se cambia. Icono + palabra: el color nunca va solo.
 */
export function PildoraModo({ className, compacta = false }: { className?: string; compacta?: boolean }) {
  const { modo, error, cargando } = useModo();

  let texto = "Leyendo el modo…";
  let detalle = "";
  let estilo = "bg-superficie-2 text-tinta-suave";
  let Icono = CircleQuestionMark;
  if (modo === "real") {
    texto = NOMBRE_MODO.real;
    detalle = "las órdenes mueven dinero de verdad";
    estilo = "bg-real text-real-boton-tinta";
    Icono = ShieldAlert;
  } else if (modo === "pruebas") {
    texto = NOMBRE_MODO.pruebas;
    detalle = "dinero ficticio";
    estilo = "bg-pruebas-suave text-pruebas-tinta ring-1 ring-pruebas/40";
    Icono = FlaskConical;
  } else if (modo === "simulacion") {
    texto = NOMBRE_MODO.simulacion;
    detalle = "no se envía nada";
    estilo = "bg-superficie-2 text-tinta ring-1 ring-linea";
    Icono = Calculator;
  } else if (error && !cargando) {
    texto = "Modo desconocido";
    detalle = "no uses nada que mueva dinero";
    estilo = "bg-real-suave text-real-tinta ring-1 ring-real/40";
  }

  if (compacta) {
    // En el carril estrecho (Operar): solo el icono del modo, con su nombre para el lector y al pasar.
    return (
      <Link
        href="/ajustes/#conexion"
        className={clases("inline-flex h-11 w-11 items-center justify-center rounded-full", estilo, className)}
        aria-live="polite"
        title={detalle ? `${texto}: ${detalle}. Cambiar en Ajustes · Conexión` : texto}
      >
        <Icono aria-hidden="true" className="h-5 w-5" strokeWidth={2} />
        <span className="sr-only">Modo: {texto}</span>
      </Link>
    );
  }
  return (
    <Link
      href="/ajustes/#conexion"
      className={clases(
        // 36 px a la vista; el area que se pulsa llega a 44 px con el ::before.
        "relative inline-flex min-h-9 items-center gap-1.5 rounded-full px-3 text-sm font-semibold whitespace-nowrap before:absolute before:inset-x-0 before:-inset-y-1",
        estilo,
        className,
      )}
      aria-live="polite"
      title={detalle ? `${texto}: ${detalle}. Cambiar en Ajustes · Conexión` : undefined}
    >
      <Icono aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
      <span className="sr-only">Modo: </span>
      {texto}
      {detalle && modo === "pruebas" ? <span className="hidden font-normal sm:inline">· {detalle}</span> : null}
    </Link>
  );
}
