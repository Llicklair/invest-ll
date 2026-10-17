"use client";

import { ArrowRight, Compass, MessagesSquare, ShieldCheck, TrendingDown } from "lucide-react";
import Link from "next/link";

import { api, pedir, type ErrorApi } from "@/api/cliente";
import type { Hoy, Inicio as DatosInicio } from "@/api/tipos";
import { CambioPct, CifraGrande, Variacion } from "@/componentes/CifraGrande";
import { AvisoDatos } from "@/componentes/DatosAlDia";
import { NadaQueHacer } from "@/componentes/EstadoVacio";
import { FilaAccion } from "@/componentes/TarjetaAccion";
import { Aviso, BotonEnlace, Chip, EnlaceFlecha, ErrorApiVista, Esqueleto, Tarjeta, TextoApi } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useModo } from "@/contexto/modo";
import { useConsulta } from "@/lib/consulta";
import { signoDecimal } from "@/lib/decimal";
import { diaYMes, enMoneda, euros, fechaCorta } from "@/lib/formato";

const PASOS_BIENVENIDA = [
  { icono: MessagesSquare, titulo: "Cinco preguntas", texto: "Cuánto tienes, cuándo lo necesitarás y qué harías si bajara. Sin jerga." },
  { icono: Compass, titulo: "Qué te proponemos y por qué", texto: "Un reparto concreto, explicado con tus propias respuestas." },
  { icono: TrendingDown, titulo: "Lo bueno y lo malo", texto: "Cuánto habría crecido con tus números y, igual de grande, cuánto llegó a bajar." },
];

function Bienvenida({ datos }: { datos: DatosInicio }) {
  return (
    <div className="mx-auto max-w-3xl py-4 lg:py-10">
      <p className="text-[0.9375rem] font-medium text-tinta-suave">Bienvenida</p>
      <h1 className="titular mt-3 text-[2.5rem] leading-[1.08] font-semibold text-tinta sm:text-[3.25rem]">
        Hola. Vamos a ver qué hacer con tu dinero.
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-tinta-suave">
        Cinco preguntas, sin jerga. Al final verás qué te proponemos, cuánto habría crecido y —igual de importante— cuánto
        habría llegado a bajar.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <BotonEnlace href="/estrategias/" variante="primario" className="sm:min-w-48">
          Empezar
          <ArrowRight aria-hidden="true" className="h-4 w-4" />
        </BotonEnlace>
        <EnlaceFlecha href="/estrategias/#catalogo" className="justify-center sm:justify-start sm:px-3">
          Ya sé lo que quiero: ver las estrategias
        </EnlaceFlecha>
      </div>

      <ol className="mt-12 grid gap-3 sm:grid-cols-3">
        {PASOS_BIENVENIDA.map((p, i) => {
          const Icono = p.icono;
          return (
            <li key={p.titulo}>
              <Tarjeta className="h-full p-5">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-marca-suave text-marca" aria-hidden="true">
                  <Icono className="h-5 w-5" strokeWidth={1.75} />
                </span>
                <p className="mt-4 font-semibold text-tinta">
                  <span className="sr-only">Paso {i + 1}: </span>
                  {p.titulo}
                </p>
                <p className="mt-1 text-[0.9375rem] leading-relaxed text-tinta-suave">{p.texto}</p>
              </Tarjeta>
            </li>
          );
        })}
      </ol>

      <p className="mt-8 flex items-start gap-2 text-[0.9375rem] text-tinta-suave">
        <ShieldCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
        Nada de esto mueve dinero. Cuando decidas invertir, cada orden te dirá qué va a pasar y tendrás que confirmarla
        tecleando la cantidad.
      </p>

      {datos.hay_movimientos ? (
        <Tarjeta className="mt-8 flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <p className="text-sm text-tinta-suave">Ya tienes movimientos anotados</p>
            <p className="titular mt-1 text-2xl font-medium text-tinta">{enMoneda(datos.patrimonio.valor, datos.patrimonio.moneda)}</p>
          </div>
          <EnlaceFlecha href="/cartera/">Ver tu cartera</EnlaceFlecha>
        </Tarjeta>
      ) : null}
    </div>
  );
}

function TuDinero({ datos }: { datos: DatosInicio }) {
  const p = datos.patrimonio;
  const ficticio = p.cartera === "pruebas";
  if (!datos.hay_movimientos) {
    return (
      <Tarjeta className="p-6 sm:p-8">
        <CifraGrande
          etiqueta="Tu dinero hoy"
          valor="0"
          marca={ficticio ? <Chip tono="pruebas">Dinero ficticio</Chip> : null}
          pie="Aún no has anotado ninguna compra. Cuando hagas la primera, aquí verás cuánto vale y cuánto ganas o pierdes."
        />
      </Tarjeta>
    );
  }
  const conEfectivo = signoDecimal(p.efectivo) === 1;
  return (
    <Tarjeta className="p-6 sm:p-8">
      <CifraGrande
        etiqueta="Tu dinero hoy"
        valor={p.valor}
        moneda={p.moneda}
        marca={ficticio ? <Chip tono="pruebas">Dinero ficticio · modo pruebas</Chip> : null}
        variacion={
          <div className="space-y-2">
            <p className="cifras text-[0.9375rem] text-tinta">
              Has puesto {enMoneda(p.puesto, p.moneda)}
              {conEfectivo ? (
                <span className="text-tinta-suave">
                  {" "}
                  · {enMoneda(p.efectivo, p.moneda)} de ello, sin invertir todavía
                </span>
              ) : null}
            </p>
            <Variacion importe={p.ganancia} pct={p.ganancia_pct} moneda={p.moneda} coletilla="si vendieras hoy" />
          </div>
        }
        pie={
          <>
            {p.incompleto
              ? "Falta el precio de algo de lo que tienes: la cifra no está completa. "
              : p.fecha_precios
                ? `Con los precios del cierre del ${fechaCorta(p.fecha_precios)}. `
                : ""}
            {p.nota_moneda ? `${p.nota_moneda.replace(/\.?\s*$/, ".")} ` : ""}
            {signoDecimal(p.realizado) ? (
              <>
                Con lo que ya vendiste, {signoDecimal(p.realizado) === 1 ? "ganaste" : "perdiste"}{" "}
                <span className="cifras">{enMoneda(p.realizado.replace(/^-/, ""), p.moneda)}</span>.
              </>
            ) : null}
          </>
        }
      />
    </Tarjeta>
  );
}

function QueTocaHacer({
  hoy,
  error,
  recargar,
  cargando,
}: {
  hoy: Hoy | null;
  error: ErrorApi | null;
  recargar: () => void;
  cargando: boolean;
}) {
  return (
    <section aria-labelledby="toca-titulo" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="toca-titulo" className="titular text-2xl font-semibold text-tinta">
          Qué toca hacer
        </h2>
        {hoy && hoy.acciones.length ? <EnlaceFlecha href="/invertir/">Ver todo en Invertir</EnlaceFlecha> : null}
      </div>
      {error ? <ErrorApiVista error={error} reintentar={recargar} /> : null}
      {!hoy && cargando ? <Esqueleto className="h-40" /> : null}
      {/* Los avisos de "hoy" (la pausa, datos que faltan) ya van arriba, en los de Inicio: aqui
          se repetian. Lo que si se dice aqui es que no toca nada, y por que (`resumen`). */}
      {hoy ? (
        <>
          {hoy.acciones.length ? (
            <Tarjeta className="p-2 sm:p-3">
              <p className="px-3 pt-2 pb-1 text-[0.9375rem] text-tinta-suave">{hoy.resumen}</p>
              <ul className="divide-y divide-linea">
                {hoy.acciones.slice(0, 3).map((a) => (
                  <FilaAccion key={a.id} accion={a} />
                ))}
              </ul>
              {hoy.acciones.length > 3 ? (
                <p className="px-3 pt-1 pb-2 text-sm text-tinta-suave">Y {hoy.acciones.length - 3} más en Invertir.</p>
              ) : null}
            </Tarjeta>
          ) : (
            <NadaQueHacer resumen={hoy.resumen} />
          )}
        </>
      ) : null}
    </section>
  );
}

function TuPlan({ datos }: { datos: DatosInicio }) {
  if (!datos.plan) return null;
  return (
    <Tarjeta como="section" className="p-5 sm:p-6" aria-labelledby="plan-titulo">
      <div className="flex items-center justify-between gap-3">
        <h2 id="plan-titulo" className="titular text-xl font-semibold text-tinta">
          Tu plan
        </h2>
        <Link href="/estrategias/#plan" className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline">
          Cambiarlo
        </Link>
      </div>
      <ul className="mt-2 divide-y divide-linea">
        {datos.plan.map((p) => (
          <li key={p.estrategia} className="py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-semibold text-tinta">{p.nombre}</span>
              <span className="cifras font-semibold text-tinta">{euros(p.valor)}</span>
            </div>
            <div className="mt-0.5 flex items-baseline justify-between gap-3 text-sm text-tinta-suave">
              <span>{p.mercado === "bolsa" ? "Bolsa · en tu bróker" : "Cripto · en Binance"}</span>
              <span className="cifras">puesto {euros(p.puesto)}</span>
            </div>
          </li>
        ))}
      </ul>
      {datos.proxima_fecha ? (
        <p className="mt-2 rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">
          Próxima aportación: <strong className="font-semibold">el {diaYMes(datos.proxima_fecha)}</strong>
        </p>
      ) : null}
    </Tarjeta>
  );
}

function MercadoEnUnaLinea({ datos }: { datos: DatosInicio }) {
  if (!datos.mercado.length) return null;
  return (
    <Tarjeta como="section" className="p-5 sm:p-6" aria-labelledby="mercado-titulo">
      <div className="flex items-center justify-between gap-3">
        <h2 id="mercado-titulo" className="titular text-xl font-semibold text-tinta">
          El mercado este mes
        </h2>
        <Link href="/mercado/" className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline">
          Ver más
        </Link>
      </div>
      <ul className="mt-2 divide-y divide-linea">
        {datos.mercado.map((m) => (
          <li key={m.symbol} className="flex items-baseline justify-between gap-3 py-2.5">
            <span className="text-tinta">{m.nombre}</span>
            <CambioPct pct={m.var_1m} />
          </li>
        ))}
      </ul>
      <p className="mt-2 text-sm text-tinta-suave">
        Variación en un mes, hasta el cierre del {fechaCorta(datos.mercado[0]?.fecha)}. No es una señal: es cómo ha ido.
      </p>
    </Tarjeta>
  );
}

/** Inicio: ¿como va mi dinero y que tengo que hacer? (docs/panel-v2.md, 4.1). */
export function Inicio() {
  const { versionDatos } = useEstado();
  const { modo } = useModo();
  const inicio = useConsulta(`inicio:${versionDatos}:${modo ?? "?"}`, () => pedir(api.GET("/api/inicio")));
  const conPlan = inicio.datos?.plan ? true : false;
  const hoy = useConsulta(conPlan ? `hoy:${versionDatos}:${modo ?? "?"}` : null, () => pedir(api.GET("/api/plan/hoy")));
  const d = inicio.datos;

  if (inicio.error && !d) {
    return (
      <div className="space-y-4">
        <h1 className="titular text-[2rem] font-semibold text-tinta">Inicio</h1>
        <ErrorApiVista error={inicio.error} prefijo="No se pudo leer cómo va tu dinero:" reintentar={inicio.recargar} />
      </div>
    );
  }
  if (!d) {
    return (
      <div className="space-y-6" aria-busy="true">
        <span className="sr-only" role="status">
          Cargando tu dinero…
        </span>
        <Esqueleto className="h-10 w-56" />
        <Esqueleto className="h-56" />
        <Esqueleto className="h-40" />
      </div>
    );
  }
  if (!d.plan) return <Bienvenida datos={d} />;

  return (
    <div className={inicio.cargando ? "opacity-70 transition-opacity" : undefined}>
      <h1 className="titular mb-8 text-[2rem] leading-tight font-semibold text-tinta lg:text-[2.5rem]">Inicio</h1>
      <div className="mb-6 space-y-3 empty:hidden">
        {d.avisos.map((a) => (
          <Aviso key={a} tipo="aviso">
            <TextoApi texto={a} />
          </Aviso>
        ))}
        <AvisoDatos />
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-8">
        <div className="min-w-0 space-y-8">
          <TuDinero datos={d} />
          <QueTocaHacer hoy={hoy.datos} error={hoy.error} recargar={hoy.recargar} cargando={hoy.cargando} />
        </div>
        <div className="min-w-0 space-y-6">
          <TuPlan datos={d} />
          <MercadoEnUnaLinea datos={d} />
        </div>
      </div>
    </div>
  );
}
