"use client";

// El plan a largo plazo dentro del Resumen (docs/panel-v5.md, seccion 3): lo que era Inicio cuando
// ya hay un plan, en piezas.

import Link from "next/link";

import type { ErrorApi } from "@/api/cliente";
import type { Hoy, Inicio as DatosInicio } from "@/api/tipos";
import { CambioPct, CifraGrande, Variacion } from "@/componentes/CifraGrande";
import { NadaQueHacer } from "@/componentes/EstadoVacio";
import { FilaAccion } from "@/componentes/TarjetaAccion";
import { Chip, EnlaceFlecha, ErrorApiVista, Esqueleto, Tarjeta } from "@/componentes/ui";
import { signoDecimal } from "@/lib/decimal";
import { diaYMes, enMoneda, fechaCorta } from "@/lib/formato";

export function TuDinero({ datos }: { datos: DatosInicio }) {
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

export function QueTocaHacer({
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
        {hoy && hoy.acciones.length ? <EnlaceFlecha href="/plan/invertir/">Ver todo en Invertir</EnlaceFlecha> : null}
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

export function TuPlan({ datos }: { datos: DatosInicio }) {
  if (!datos.plan) return null;
  return (
    <Tarjeta como="section" className="p-5 sm:p-6" aria-labelledby="plan-titulo">
      <div className="flex items-center justify-between gap-3">
        <h2 id="plan-titulo" className="titular text-xl font-semibold text-tinta">
          Tu plan
        </h2>
        <Link href="/plan/#plan" className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline">
          Cambiarlo
        </Link>
      </div>
      <ul className="mt-2 divide-y divide-linea">
        {datos.plan.map((p) => (
          <li key={p.estrategia} className="py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-semibold text-tinta">{p.nombre}</span>
              {/* Cada parte en la moneda de sus acciones (contrato v2.1): euros en el bróker, USDT en Binance. */}
              <span className="cifras font-semibold text-tinta">{enMoneda(p.valor, p.moneda)}</span>
            </div>
            <div className="mt-0.5 flex items-baseline justify-between gap-3 text-sm text-tinta-suave">
              <span>{p.mercado === "bolsa" ? "Bolsa · en tu bróker" : "Cripto · en Binance"}</span>
              <span className="cifras">puesto {enMoneda(p.puesto, p.moneda)}</span>
            </div>
            {signoDecimal(p.efectivo) === 1 ? (
              <p className="cifras mt-0.5 text-sm text-tinta-suave">
                {enMoneda(p.efectivo, p.moneda)} de ello, sin invertir en tu bróker: lo que cobraste al vender y aún no has vuelto a
                invertir.
              </p>
            ) : null}
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

export function MercadoEnUnaLinea({ datos }: { datos: DatosInicio }) {
  if (!datos.mercado.length) return null;
  return (
    <Tarjeta como="section" className="p-5 sm:p-6" aria-labelledby="mercado-titulo">
      <div className="flex items-center justify-between gap-3">
        <h2 id="mercado-titulo" className="titular text-xl font-semibold text-tinta">
          El mercado este mes
        </h2>
        <Link href="/operar/mercados/" className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline">
          Ver más
        </Link>
      </div>
      <ul className="mt-2 divide-y divide-linea">
        {datos.mercado.map((m) => (
          <li key={m.symbol} className="flex items-baseline justify-between gap-3 py-2.5">
            <span className="text-tinta">{m.nombre}</span>
            <span className="shrink-0 whitespace-nowrap">
              <CambioPct pct={m.var_1m} />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-sm text-tinta-suave">
        Variación en un mes, hasta el cierre del {fechaCorta(datos.mercado[0]?.fecha)}. No es una señal: es cómo ha ido.
      </p>
    </Tarjeta>
  );
}
