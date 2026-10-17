"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import type { AnteCaida, Horizonte, QuiereCripto } from "@/api/tipos";
import { CampoImporte } from "@/componentes/CampoImporte";
import { OpcionesRadio } from "@/componentes/OpcionesRadio";
import { Boton, Tarjeta, clases } from "@/componentes/ui";
import { leerImporte } from "@/lib/importe";

import type { Respuestas } from "./estado";

const HORIZONTES: readonly { valor: Horizonte; texto: string }[] = [
  { valor: "menos-2", texto: "En menos de 2 años" },
  { valor: "2-5", texto: "Entre 2 y 5 años" },
  { valor: "5-10", texto: "Entre 5 y 10 años" },
  { valor: "mas-10", texto: "En más de 10 años" },
];

const CAIDAS: readonly { valor: AnteCaida; texto: string; detalle: string }[] = [
  { valor: "vender", texto: "Vendería para no perder más", detalle: "Es lo que hace mucha gente, y es normal." },
  { valor: "esperar", texto: "Esperaría a que se recupere", detalle: "Aunque tardara un par de años." },
  { valor: "comprar", texto: "Aprovecharía para poner más", detalle: "Si tuviera dinero para hacerlo." },
];

const CRIPTOS: readonly { valor: QuiereCripto; texto: string; detalle: string }[] = [
  { valor: "no", texto: "No", detalle: "Solo bolsa y bonos." },
  { valor: "poco", texto: "Un poco", detalle: "Una parte pequeña, con freno." },
  { valor: "si", texto: "Sí", detalle: "Algo más, pero siempre con límite." },
];

const PREGUNTAS = 5;

type Errores = Partial<Record<keyof Respuestas, string>>;

function erroresDe(r: Respuestas): Errores {
  const e: Errores = {};
  if (r.inicial.trim() === "") e.inicial = "Escribe una cantidad. Si no quieres empezar con nada, escribe 0.";
  else if (leerImporte(r.inicial) === null) e.inicial = "Eso no parece una cantidad: escribe solo el número, por ejemplo 6.000.";
  if (r.mensual.trim() === "") e.mensual = "Escribe una cantidad. Si no vas a añadir nada cada mes, escribe 0.";
  else if (leerImporte(r.mensual) === null) e.mensual = "Eso no parece una cantidad: escribe solo el número, por ejemplo 200.";
  if (!r.horizonte) e.horizonte = "Elige una respuesta.";
  if (!r.ante_caida) e.ante_caida = "Elige una respuesta: la que harías de verdad.";
  if (!r.cripto) e.cripto = "Elige una respuesta.";
  return e;
}

const CAMPO_DE_PREGUNTA: (keyof Respuestas)[] = ["inicial", "mensual", "horizonte", "ante_caida", "cripto"];

/**
 * Paso 1 · Cuentanos. Cinco preguntas: en el movil, una por pantalla; en escritorio, todas a la
 * vez (docs/panel-v2.md, 4.2). Es el mismo formulario: en el movil se oculta con CSS lo que no
 * toca, asi que no hay saltos al hidratar ni dos versiones que mantener.
 */
export function Cuestionario({
  respuestas,
  onCambio,
  onTerminar,
  onCatalogo,
}: {
  respuestas: Respuestas;
  onCambio: (r: Respuestas) => void;
  onTerminar: () => void;
  onCatalogo: () => void;
}) {
  const [actual, setActual] = useState(0);
  const [mostrarErrores, setMostrarErrores] = useState<Set<keyof Respuestas>>(new Set());
  const bloques = useRef<(HTMLDivElement | null)[]>([]);
  const errores = erroresDe(respuestas);
  const error = (campo: keyof Respuestas) => (mostrarErrores.has(campo) ? (errores[campo] ?? null) : null);

  const fijar = <K extends keyof Respuestas>(campo: K, valor: Respuestas[K]) => onCambio({ ...respuestas, [campo]: valor });

  const ir = (i: number) => {
    setActual(i);
    window.requestAnimationFrame(() => {
      const bloque = bloques.current[i];
      bloque?.querySelector<HTMLElement>("input")?.focus({ preventScroll: true });
      bloque?.scrollIntoView({ block: "nearest" });
    });
  };

  const siguiente = () => {
    const campo = CAMPO_DE_PREGUNTA[actual];
    if (campo && errores[campo]) {
      setMostrarErrores((s) => new Set(s).add(campo));
      return;
    }
    ir(Math.min(PREGUNTAS - 1, actual + 1));
  };

  const terminar = (e: FormEvent) => {
    e.preventDefault();
    const conError = CAMPO_DE_PREGUNTA.filter((c) => errores[c]);
    if (conError.length) {
      setMostrarErrores(new Set(conError));
      const primera = CAMPO_DE_PREGUNTA.indexOf(conError[0] ?? "inicial");
      ir(primera);
      return;
    }
    onTerminar();
  };

  const bloque = (i: number) =>
    clases("p-5 sm:p-7", i !== actual && "max-lg:hidden");

  return (
    <form onSubmit={terminar} noValidate>
      <div className="mb-6 max-w-2xl">
        <h2 className="titular text-[1.75rem] leading-tight font-semibold text-tinta lg:text-[2rem]">Cuéntanos un poco</h2>
        <p className="mt-2 text-[0.9375rem] leading-relaxed text-tinta-suave lg:text-base">
          No hay respuestas buenas o malas. Contesta lo que harías de verdad: con eso elegimos qué te proponemos.
        </p>
        <p className="mt-3 text-sm font-medium text-tinta-suave lg:hidden" aria-live="polite">
          Pregunta {actual + 1} de {PREGUNTAS}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Tarjeta className={bloque(0)}>
          <div ref={(el) => { bloques.current[0] = el; }}>
            <CampoImporte
              grande
              etiqueta="¿Con cuánto quieres empezar?"
              ayuda="Lo que pondrías el primer día. Puede ser 0."
              valor={respuestas.inicial}
              onCambio={(v) => fijar("inicial", v)}
              error={error("inicial")}
              atajos={["0", "1000", "5000", "10000"]}
              ejemplo="p. ej. 6.000"
            />
          </div>
        </Tarjeta>
        <Tarjeta className={bloque(1)}>
          <div ref={(el) => { bloques.current[1] = el; }}>
            <CampoImporte
              grande
              etiqueta="¿Cuánto podrías añadir cada mes?"
              ayuda="Lo que te sobra cada mes sin apretarte. Puede ser 0."
              valor={respuestas.mensual}
              onCambio={(v) => fijar("mensual", v)}
              error={error("mensual")}
              atajos={["0", "50", "100", "200", "500"]}
              ejemplo="p. ej. 200"
            />
          </div>
        </Tarjeta>
        <Tarjeta className={clases(bloque(2), "lg:col-span-2")}>
          <div ref={(el) => { bloques.current[2] = el; }}>
            <OpcionesRadio
              pregunta="¿Cuándo vas a necesitar este dinero?"
              opciones={HORIZONTES}
              valor={respuestas.horizonte}
              onCambio={(v) => fijar("horizonte", v)}
              error={error("horizonte")}
              columnas={2}
            />
          </div>
        </Tarjeta>
        <Tarjeta className={clases(bloque(3), "lg:col-span-2")}>
          <div ref={(el) => { bloques.current[3] = el; }}>
            <OpcionesRadio
              pregunta="Imagina que lo que inviertes cae a la mitad en unos meses. ¿Qué harías?"
              ayuda="Pasa más a menudo de lo que parece: la bolsa lo hizo en 2008 y el bitcoin varias veces."
              opciones={CAIDAS}
              valor={respuestas.ante_caida}
              onCambio={(v) => fijar("ante_caida", v)}
              error={error("ante_caida")}
              columnas={3}
            />
          </div>
        </Tarjeta>
        <Tarjeta className={clases(bloque(4), "lg:col-span-2")}>
          <div ref={(el) => { bloques.current[4] = el; }}>
            <OpcionesRadio
              pregunta="¿Quieres algo de criptomonedas?"
              ayuda="Bitcoin y similares. Suben y bajan mucho más que la bolsa."
              opciones={CRIPTOS}
              valor={respuestas.cripto}
              onCambio={(v) => fijar("cripto", v)}
              error={error("cripto")}
              columnas={3}
            />
          </div>
        </Tarjeta>
      </div>

      {/* Movil: una pregunta por pantalla. */}
      <div className="mt-6 flex items-center gap-3 lg:hidden">
        {actual > 0 ? (
          <Boton variante="secundario" onClick={() => ir(actual - 1)} aria-label="Pregunta anterior">
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            Atrás
          </Boton>
        ) : null}
        {actual < PREGUNTAS - 1 ? (
          <Boton variante="primario" className="flex-1" onClick={siguiente}>
            Siguiente
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </Boton>
        ) : (
          <Boton type="submit" variante="primario" className="flex-1">
            Ver mi propuesta
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </Boton>
        )}
      </div>

      {/* Escritorio: todas juntas y un boton. */}
      <div className="mt-8 hidden flex-wrap items-center gap-4 lg:flex">
        <Boton type="submit" variante="primario" className="min-w-56">
          Ver mi propuesta
          <ArrowRight aria-hidden="true" className="h-4 w-4" />
        </Boton>
        {Object.keys(errores).length && mostrarErrores.size ? (
          <p className="text-[0.9375rem] font-medium text-real-tinta" role="alert">
            Falta alguna respuesta: está marcada arriba.
          </p>
        ) : null}
      </div>

      <p className="mt-8 text-[0.9375rem] text-tinta-suave">
        ¿Ya sabes lo que quieres?{" "}
        <button type="button" onClick={onCatalogo} className="inline-flex min-h-11 items-center font-semibold text-marca underline-offset-4 hover:underline">
          Ver todas las estrategias sin responder
        </button>
      </p>
    </form>
  );
}
