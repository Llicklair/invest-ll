"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { API_BASE, MODO_EJEMPLO } from "@/api/cliente";
import { SeccionDatos } from "@/componentes/DatosAlDia";
import { Encabezado, Nota, Seccion, Tarjeta, clases } from "@/componentes/ui";
import { useGuardado } from "@/lib/almacen";

import { Conexion } from "./Conexion";

const TEMAS = [
  { valor: "sistema", texto: "Como el sistema", icono: Monitor },
  { valor: "claro", texto: "Claro", icono: Sun },
  { valor: "oscuro", texto: "Oscuro", icono: Moon },
] as const;

function Tema() {
  const [tema, fijar] = useGuardado("local", "invest-ll.tema", "sistema");
  return (
    <fieldset>
      <legend className="sr-only">Tema</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        {TEMAS.map((t) => {
          const elegido = (tema === "claro" || tema === "oscuro" ? tema : "sistema") === t.valor;
          const Icono = t.icono;
          return (
            <label
              key={t.valor}
              className={clases(
                "flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border px-4 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco",
                elegido ? "border-marca bg-marca-suave font-semibold text-tinta" : "border-linea bg-superficie text-tinta hover:bg-superficie-2",
              )}
            >
              <input
                type="radio"
                name="tema"
                className="sr-only"
                checked={elegido}
                onChange={() => fijar(t.valor === "sistema" ? null : t.valor)}
              />
              <Icono aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
              {t.texto}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Solo en `npm run dev:mock`: cambiar de escenario de ejemplo para recorrer los estados. */
function useListaEscenarios(): { nombre: string; descripcion: string }[] | null {
  const [lista, setLista] = useState<{ nombre: string; descripcion: string }[] | null>(null);
  useEffect(() => {
    // Misma condicion que en api/cliente.ts: en un `next build` es falsa al compilar y el modulo
    // de ejemplo ni se empaqueta.
    if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK === "1") {
      void import("@mocks/escenarios").then((m) =>
        setLista(m.ESCENARIOS.map((e) => ({ nombre: e, descripcion: m.DESCRIPCION_ESCENARIOS[e] }))),
      );
    }
  }, []);
  return lista;
}

function Escenarios() {
  const lista = useListaEscenarios();
  if (!MODO_EJEMPLO || !lista) return null;
  return (
    <Seccion titulo="Escenarios de ejemplo" id="ejemplo" bajada="Solo existe con los datos de ejemplo (web/mocks/). Cambiar de escenario recarga la página y empieza de cero.">
      <ul className="grid gap-2 sm:grid-cols-2">
        {lista.map(({ nombre: e, descripcion }) => (
          <li key={e}>
            <a
              href={`/?escenario=${e}`}
              className="block min-h-11 rounded-xl border border-linea bg-superficie px-4 py-3 hover:bg-superficie-2"
            >
              <span className="block font-semibold text-tinta">{e}</span>
              <span className="block text-sm text-tinta-suave">{descripcion}</span>
            </a>
          </li>
        ))}
      </ul>
    </Seccion>
  );
}

/** Ajustes (docs/panel-v2.md, 4.5): la conexion con Binance, el tema, los datos y acerca de. */
export function Ajustes() {
  return (
    <div className="space-y-14">
      <Encabezado antetitulo="Más" titulo="Ajustes" bajada="La conexión con Binance, cómo se ve el panel y de dónde salen los datos." />

      <Seccion
        titulo="Conexión con Binance"
        id="conexion"
        bajada="Tres pasos para pasar de la simulación al dinero real, sin saltarse ninguno."
      >
        <Conexion />
      </Seccion>

      <Seccion titulo="Tema" id="tema">
        <Tema />
      </Seccion>

      <Seccion titulo="Datos" id="datos" bajada="Los precios con los que se calcula todo: de cuándo son y cómo traer los nuevos. Se descargan de internet; el panel no los inventa.">
        <SeccionDatos />
      </Seccion>

      <Escenarios />

      <Seccion titulo="Acerca de" id="acerca">
        <Tarjeta className="space-y-3 p-5 sm:p-6">
          <p className="text-[0.9375rem] leading-relaxed text-tinta">
            INVEST LL es un sistema que no puede mentirte sobre sus propios resultados: toda cifra lleva su fecha, las simulaciones
            descuentan comisiones, nada notifica ni empuja a operar, y cada orden se confirma tecleando la cantidad.
          </p>
          <Nota>
            Panel servido por la API local{API_BASE ? ` (${API_BASE})` : ""}. El código y los documentos de diseño están en el
            repositorio (docs/panel-v2.md).
          </Nota>
        </Tarjeta>
      </Seccion>
    </div>
  );
}
