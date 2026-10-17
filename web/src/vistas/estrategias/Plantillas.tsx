"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { api, pedir } from "@/api/cliente";
import type { PlantillaBot } from "@/api/tipos";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { Aviso, BotonEnlace, CargandoLento, Encabezado, EnlaceFlecha, ErrorApiVista, Tarjeta } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";
import { ChipEvidenciaBot } from "@/vistas/bots/comun";

/**
 * Hasta v5, /estrategias/ era el cuestionario del plan, con `#plan` y `#catalogo`: quien llegue por
 * esas anclas va a Mi plan, que es donde estan ahora.
 */
function useAnclasDelPlan() {
  const router = useRouter();
  useEffect(() => {
    const ancla = window.location.hash;
    if (ancla === "#plan" || ancla === "#catalogo") router.replace(`/plan/${ancla}`);
  }, [router]);
}

function TarjetaPlantilla({ p }: { p: PlantillaBot }) {
  return (
    <Tarjeta como="article" className="flex h-full flex-col p-5 sm:p-6" aria-labelledby={`plantilla-${p.clave}`}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <h2 id={`plantilla-${p.clave}`} className="titular text-xl font-semibold text-tinta">
          {p.nombre}
        </h2>
        <MedidorRiesgo nivel={p.riesgo} texto={p.riesgo_texto} compacto />
      </div>
      <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-tinta">{p.frase}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <ChipEvidenciaBot evidencia={p.evidencia} />
        <span className="text-sm text-tinta-suave">Operaciones: {p.operaciones_esperadas.toLowerCase()}</span>
      </div>
      <p className="mt-3 text-sm text-tinta-suave">{p.evidencia.texto}</p>

      <details className="group mt-4 rounded-xl bg-superficie-2 px-4 py-3">
        <summary className="flex min-h-8 cursor-pointer list-none items-center justify-between gap-2 text-[0.9375rem] font-semibold text-tinta">
          Cómo funciona
          <ArrowRight aria-hidden="true" className="h-4 w-4 transition-transform group-open:rotate-90 motion-reduce:transition-none" />
        </summary>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-[0.9375rem] text-tinta">
          {p.como_funciona.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
        {p.avisos.length ? (
          <Aviso tipo="aviso" titulo="Antes de desplegarlo" className="mt-3 text-sm">
            <ul className="list-disc space-y-0.5 pl-4">
              {p.avisos.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </Aviso>
        ) : null}
      </details>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-5">
        <span className="text-sm text-tinta-suave">
          {p.monedas === "una" ? "Una moneda" : "Una o varias monedas"} · p. ej. {p.monedas_sugeridas.join(", ")}
        </span>
        <BotonEnlace href={`/bots/nuevo/?plantilla=${encodeURIComponent(p.clave)}`} tamano="compacto">
          Desplegar un bot con esta
        </BotonEnlace>
      </div>
    </Tarjeta>
  );
}

/**
 * Estrategias → Plantillas (docs/panel-v5.md, seccion 2): las reglas fijas que puede seguir un bot,
 * explicadas, con su riesgo y lo que se sabe de ellas. Si ninguna encaja, A medida.
 */
export function Plantillas() {
  useAnclasDelPlan();
  const plantillas = useConsulta("bots:plantillas", () => pedir(api.GET("/api/bots/plantillas")));

  return (
    <div>
      <Encabezado
        titulo="Estrategias"
        bajada="Las reglas que siguen los bots para comprar y vender. Empieza por una plantilla; si quieres una regla tuya, A medida."
      />
      {plantillas.error ? <ErrorApiVista error={plantillas.error} reintentar={plantillas.recargar} /> : null}
      {!plantillas.datos && !plantillas.error ? <CargandoLento texto="Cargando las plantillas…" lento="Sigue cargando las plantillas…" /> : null}
      {plantillas.datos ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {plantillas.datos.plantillas.map((p) => (
            <TarjetaPlantilla key={p.clave} p={p} />
          ))}
          <Tarjeta className="flex h-full flex-col justify-between gap-4 border-dashed p-5 sm:p-6">
            <div>
              <p className="flex items-center gap-2 titular text-xl font-semibold text-tinta">
                <Sparkles aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
                ¿Ninguna es lo que buscas?
              </p>
              <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-tinta-suave">
                Cuéntale a Claude qué quieres («compra ETH cuando rebote de su mínimo de 30 días») y la escribe, la prueba sobre el pasado
                y te enseña sus pegas.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <BotonEnlace href="/estrategias/medida/disenar/" variante="primario" tamano="compacto">
                Diseñar con Claude
              </BotonEnlace>
              <EnlaceFlecha href="/estrategias/medida/">Ver tus estrategias a medida</EnlaceFlecha>
            </div>
          </Tarjeta>
        </div>
      ) : null}
    </div>
  );
}
