"use client";

import { ArrowRight, Bot, CalendarDays, Hand, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import type { Estrategia, Plan } from "@/api/tipos";
import { BarraAccion } from "@/componentes/BarraAccion";
import { CampoImporte } from "@/componentes/CampoImporte";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { Aviso, Boton, ErrorApiVista, Selector, Tarjeta, clases } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { euros } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";

import type { PartePrecargada } from "./Propuesta";

interface Parte {
  clave: string;
  inicial: string;
  mensual: string;
}

const SIN = "";

function textoImporte(decimal: string): string {
  return formatoImporte(decimal, { decimales: 0 });
}

/** El borrador inicial: lo precargado (recomendacion o plan actual), por mercado. */
export function borradorDe(estrategias: readonly Estrategia[], partes: readonly PartePrecargada[]): { bolsa: Parte; cripto: Parte } {
  const de = (mercado: "bolsa" | "cripto"): Parte => {
    const p = partes.find((x) => estrategias.find((e) => e.clave === x.estrategia)?.mercado === mercado);
    return p ? { clave: p.estrategia, inicial: textoImporte(p.inicial), mensual: textoImporte(p.mensual) } : { clave: SIN, inicial: "", mensual: "" };
  };
  const bolsa = de("bolsa");
  // Sin nada precargado (desde el catalogo), se empieza con Equilibrada y sin cripto.
  if (!partes.length) bolsa.clave = "bolsa-equilibrada";
  return { bolsa, cripto: de("cripto") };
}

function BloqueParte({
  mercado,
  parte,
  onCambio,
  estrategias,
  error,
}: {
  mercado: "bolsa" | "cripto";
  parte: Parte;
  onCambio: (p: Parte) => void;
  estrategias: readonly Estrategia[];
  error: string | null;
}) {
  const opciones = estrategias.filter((e) => e.mercado === mercado && !e.laboratorio && !e.retirada);
  const elegida = opciones.find((e) => e.clave === parte.clave);
  const Icono = mercado === "bolsa" ? Hand : Bot;
  return (
    <Tarjeta className={clases("space-y-5 p-5 sm:p-6", !elegida && "bg-superficie-2/50")}>
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-marca-suave text-marca" aria-hidden="true">
          <Icono className="h-5 w-5" strokeWidth={1.75} />
        </span>
        <div>
          <h3 className="titular text-xl font-semibold text-tinta">{mercado === "bolsa" ? "Bolsa" : "Cripto"}</h3>
          <p className="text-sm text-tinta-suave">
            {mercado === "bolsa" ? "La compras tú en tu bróker; te decimos qué y cuánto." : "Automático en Binance; tú confirmas cada orden."}
          </p>
        </div>
      </div>
      <Selector
        etiqueta="Estrategia"
        value={parte.clave}
        onChange={(e) => onCambio({ ...parte, clave: e.target.value })}
      >
        <option value={SIN}>{mercado === "bolsa" ? "Sin bolsa" : "Sin cripto"}</option>
        {opciones.map((e) => (
          <option key={e.clave} value={e.clave} disabled={!e.disponible}>
            {e.nombre} · {e.riesgo_texto.toLowerCase()}
            {!e.disponible ? " (faltan datos)" : ""}
          </option>
        ))}
      </Selector>
      {elegida ? (
        <>
          <MedidorRiesgo nivel={elegida.riesgo} texto={elegida.riesgo_texto} compacto />
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <CampoImporte etiqueta="Para empezar" valor={parte.inicial} onCambio={(v) => onCambio({ ...parte, inicial: v })} />
            <CampoImporte etiqueta="Cada mes" valor={parte.mensual} onCambio={(v) => onCambio({ ...parte, mensual: v })} />
          </div>
        </>
      ) : null}
      {error ? <p className="text-sm font-medium text-real-tinta">{error}</p> : null}
    </Tarjeta>
  );
}

/**
 * Paso 3 · Tu plan (docs/panel-v2.md, 4.2): importes por estrategia (precargados del reparto),
 * el dia del mes para aportar y el resumen en una frase. Como mucho una de bolsa y una de cripto.
 * Guardar lleva a Invertir, a "Que toca hoy".
 */
export function TuPlan({
  estrategias,
  inicial,
  planActual,
  onBorrado,
}: {
  estrategias: readonly Estrategia[];
  inicial: { bolsa: Parte; cripto: Parte; dia: number };
  planActual: Plan | null;
  onBorrado: () => void;
}) {
  const router = useRouter();
  const { refrescarDatos } = useEstado();
  const [bolsa, setBolsa] = useState<Parte>(inicial.bolsa);
  const [cripto, setCripto] = useState<Parte>(inicial.cripto);
  const [dia, setDia] = useState(inicial.dia);
  const [intentado, setIntentado] = useState(false);
  const [confirmarBorrado, setConfirmarBorrado] = useState(false);

  const nombre = (clave: string) => estrategias.find((e) => e.clave === clave)?.nombre ?? clave;
  const partes = [bolsa, cripto].filter((p) => p.clave !== SIN);
  const valor = (t: string) => leerImporte(t === "" ? "0" : t);
  const errorParte = (p: Parte): string | null => {
    if (p.clave === SIN) return null;
    if (valor(p.inicial) === null || valor(p.mensual) === null) return "Escribe los importes solo con números, por ejemplo 5.400.";
    if (Number(valor(p.inicial)) === 0 && Number(valor(p.mensual)) === 0) return "Pon algo para empezar o algo cada mes (o quita esta parte).";
    return null;
  };
  const errorGeneral = partes.length === 0 ? "Elige al menos una estrategia: de bolsa, de cripto o de las dos." : null;
  const hayError = errorGeneral !== null || partes.some((p) => errorParte(p) !== null);

  const guardar = useAccion(async () => {
    const r = await pedir(
      api.PUT("/api/plan", {
        body: {
          partes: partes.map((p) => ({ estrategia: p.clave, inicial: valor(p.inicial) ?? "0", mensual: valor(p.mensual) ?? "0" })),
          dia_del_mes: dia,
        },
      }),
    );
    refrescarDatos();
    router.push("/invertir/");
    return r;
  });

  const borrar = useAccion(async () => {
    await pedirSinCuerpo(api.DELETE("/api/plan"));
    refrescarDatos();
    onBorrado();
    return true;
  });

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    setIntentado(true);
    if (!hayError) void guardar.ejecutar();
  };

  const mensuales = partes.filter((p) => Number(valor(p.mensual) ?? 0) > 0);
  const iniciales = partes.filter((p) => Number(valor(p.inicial) ?? 0) > 0);
  const lista = (ps: Parte[], campo: "inicial" | "mensual") =>
    ps.map((p) => `${euros(valor(p[campo]) ?? "0", { decimales: 0 })} en ${nombre(p.clave)}`).join(" y ");

  return (
    <form onSubmit={enviar} noValidate className="space-y-8 pb-24">
      <div className="max-w-2xl">
        <h2 className="titular text-[1.75rem] leading-tight font-semibold text-tinta lg:text-[2rem]">
          {planActual ? "Tu plan" : "Tu plan, a tu medida"}
        </h2>
        <p className="mt-2 text-[0.9375rem] leading-relaxed text-tinta-suave lg:text-base">
          Ajusta los importes si quieres. Como mucho una estrategia de bolsa y una de cripto: así cada parte se entiende sola.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BloqueParte mercado="bolsa" parte={bolsa} onCambio={setBolsa} estrategias={estrategias} error={intentado ? errorParte(bolsa) : null} />
        <BloqueParte mercado="cripto" parte={cripto} onCambio={setCripto} estrategias={estrategias} error={intentado ? errorParte(cripto) : null} />
      </div>

      <Tarjeta className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[16rem_1fr] lg:items-center">
        <Selector etiqueta="Día del mes para aportar" value={String(dia)} onChange={(e) => setDia(Number(e.target.value))}>
          {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
            <option key={d} value={d}>
              El día {d}
            </option>
          ))}
        </Selector>
        <div className="flex gap-3 rounded-xl bg-marca-suave px-4 py-4 text-tinta" aria-live="polite">
          <CalendarDays aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-marca" strokeWidth={1.75} />
          <p className="text-[0.9375rem] leading-relaxed">
            {partes.length === 0 ? (
              "Elige al menos una estrategia."
            ) : (
              <>
                {mensuales.length ? (
                  <>
                    Cada día {dia} pondrás <strong className="font-semibold">{lista(mensuales, "mensual")}</strong>.{" "}
                  </>
                ) : (
                  "No aportarás nada cada mes. "
                )}
                {iniciales.length ? (
                  <>
                    Para empezar, <strong className="font-semibold">{lista(iniciales, "inicial")}</strong>.
                  </>
                ) : null}
              </>
            )}
          </p>
        </div>
      </Tarjeta>

      {intentado && errorGeneral ? <Aviso tipo="critico">{errorGeneral}</Aviso> : null}
      {guardar.error ? <ErrorApiVista error={guardar.error} prefijo="No se guardó el plan:" /> : null}

      {planActual ? (
        <div className="space-y-3">
          {!confirmarBorrado ? (
            <Boton variante="peligro" tamano="compacto" onClick={() => setConfirmarBorrado(true)}>
              <Trash2 aria-hidden="true" className="h-4 w-4" />
              Borrar mi plan
            </Boton>
          ) : (
            <Aviso tipo="aviso" titulo="¿Borrar tu plan?">
              <p>No se vende ni se toca nada de lo que tienes: solo dejaremos de decirte qué toca cada mes.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Boton variante="peligro" tamano="compacto" onClick={() => void borrar.ejecutar()} disabled={borrar.enCurso}>
                  Sí, borrarlo
                </Boton>
                <Boton variante="fantasma" tamano="compacto" onClick={() => setConfirmarBorrado(false)}>
                  No, dejarlo
                </Boton>
              </div>
            </Aviso>
          )}
          {borrar.error ? <ErrorApiVista error={borrar.error} prefijo="No se borró:" /> : null}
        </div>
      ) : null}

      <BarraAccion>
        <p className="hidden text-[0.9375rem] text-tinta-suave sm:block">Guardarlo no compra nada: te dirá qué toca hacer.</p>
        <Boton type="submit" variante="primario" disabled={guardar.enCurso} className="max-sm:flex-1">
          {guardar.enCurso ? "Guardando…" : "Guardar mi plan"}
          <ArrowRight aria-hidden="true" className="h-4 w-4" />
        </Boton>
      </BarraAccion>
    </form>
  );
}
