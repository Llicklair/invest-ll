"use client";

import { TriangleAlert } from "lucide-react";

import type { Estrategia } from "@/api/tipos";
import { GraficaTusNumeros } from "@/componentes/graficas/TusNumeros";
import { Hoja } from "@/componentes/Hoja";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { ChipEvidencia, Ejecucion } from "@/componentes/TarjetaEstrategia";
import { Cargando, ErrorApiVista } from "@/componentes/ui";
import { duracion, eurosNum, fecha, fraccion, mesYAnio, numero } from "@/lib/formato";

import { useSimulaciones } from "./datos";

function Cifras({ e }: { e: Estrategia }) {
  const h = e.historico;
  if (!h) return null;
  const filas: [string, string][] = [
    ["Si hubieras puesto 10.000 €", `el ${fecha(h.desde)}, el ${fecha(h.hasta)} tendrías ${eurosNum(h.valor_final)}.`],
    ["Cuánto creció de media al año", fraccion(h.crecimiento_anual, 1)],
    ["Su peor caída", `${fraccion(h.peor_caida, 0)} desde su máximo, en ${mesYAnio(h.peor_caida_fecha)}.`],
    ["Lo más que tardó en recuperarse", `${duracion(h.peor_racha_anios)} hasta volver a su máximo.`],
    ["Tiempo invertido", `${fraccion(h.tiempo_invertido, 0, false)} del tiempo; el resto, en liquidez.`],
    ["Operaciones", `Unas ${numero(h.operaciones_al_anio, 0)} al año.`],
  ];
  return (
    <dl className="divide-y divide-linea rounded-xl border border-linea">
      {filas.map(([t, d]) => (
        <div key={t} className="grid gap-1 px-4 py-3 sm:grid-cols-[13rem_1fr] sm:gap-4">
          <dt className="text-sm text-tinta-suave">{t}</dt>
          <dd className="cifras text-[0.9375rem] text-tinta">{d}</dd>
        </div>
      ))}
    </dl>
  );
}

function Grafica({ e }: { e: Estrategia }) {
  const anio = e.historico ? Number(e.historico.desde.slice(0, 4)) : 2018;
  const sim = useSimulaciones(e.disponible ? [e.clave] : [], "10000", "0", anio);
  const r = sim.datos?.get(e.clave);
  if (sim.error) return <ErrorApiVista error={sim.error} reintentar={sim.recargar} />;
  if (!r) return sim.cargando ? <Cargando texto="Calculando su historia…" /> : null;
  return (
    <GraficaTusNumeros
      titulo={`10.000 € desde ${fecha(r.desde)}`}
      series={[{ resultado: r, hueco: 0 }]}
      alto={240}
      pie={<>Probada sobre el pasado, con comisiones. Lo que hizo no es una promesa de lo que hará.</>}
    />
  );
}

/** "Ver como funciona": la estrategia entera, en llano (docs/panel-v2.md, 4.2). */
export function HojaEstrategia({ estrategia: e, onCerrar }: { estrategia: Estrategia | null; onCerrar: () => void }) {
  return (
    <Hoja abierta={e !== null} onCerrar={onCerrar} titulo={e?.nombre ?? ""} bajada={e?.frase}>
      {e ? (
        <div className="space-y-7">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <MedidorRiesgo nivel={e.riesgo} texto={e.riesgo_texto} />
            <ChipEvidencia estrategia={e} />
          </div>

          <section aria-labelledby="como-titulo">
            <h3 id="como-titulo" className="text-lg font-semibold text-tinta">
              Cómo funciona
            </h3>
            <ol className="mt-3 space-y-3">
              {e.como_funciona.map((paso, i) => (
                <li key={paso} className="flex gap-3">
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-marca-suave text-sm font-semibold text-marca"
                    aria-hidden="true"
                  >
                    {i + 1}
                  </span>
                  <span className="text-[0.9375rem] leading-relaxed text-tinta">{paso}</span>
                </li>
              ))}
            </ol>
            <Ejecucion estrategia={e} className="mt-4" />
            {e.activos.length ? (
              <p className="mt-2 text-[0.9375rem] text-tinta-suave">Compra: {e.activos.join(" · ")}.</p>
            ) : null}
          </section>

          <section aria-labelledby="quien-titulo">
            <h3 id="quien-titulo" className="text-lg font-semibold text-tinta">
              Para quién es
            </h3>
            <p className="mt-2 text-[0.9375rem] leading-relaxed text-tinta">{e.para_quien}</p>
          </section>

          {e.avisos.length ? (
            <section aria-labelledby="avisos-titulo" className="rounded-xl bg-pruebas-suave px-4 py-4">
              <h3 id="avisos-titulo" className="flex items-center gap-2 font-semibold text-pruebas-tinta">
                <TriangleAlert aria-hidden="true" className="h-5 w-5" strokeWidth={1.75} />
                Lo que tienes que saber
              </h3>
              <ul className="mt-2 space-y-2 text-[0.9375rem] leading-relaxed text-tinta">
                {e.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="pasado-titulo" className="space-y-4">
            <h3 id="pasado-titulo" className="text-lg font-semibold text-tinta">
              Lo que hizo en el pasado
            </h3>
            {e.disponible ? (
              <>
                <Grafica e={e} />
                <Cifras e={e} />
                <QueEsEsto clave="prueba-pasado" />
              </>
            ) : (
              <p className="text-[0.9375rem] text-tinta-suave">{e.motivo ?? "Faltan datos para calcularla."}</p>
            )}
          </section>
        </div>
      ) : null}
    </Hoja>
  );
}
