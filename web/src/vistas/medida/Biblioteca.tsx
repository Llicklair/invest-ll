"use client";

import { ChevronRight, MessagesSquare, PencilLine, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { ResumenEstrategia } from "@/api/tipos";
import { EstadoVacio } from "@/componentes/EstadoVacio";
import { Hoja } from "@/componentes/Hoja";
import { Boton, BotonEnlace, CargandoLento, Encabezado, ErrorApiVista, Esqueleto, Seccion, Tarjeta } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";
import { momento } from "@/lib/formato";
import { nombreIntervalo } from "@/lib/vivo";

import { ChipAutor, ChipEstadoEstrategia, LineaPrueba, NavEstrategias, useConversaciones } from "./comun";
import { EditorEstrategia } from "./Editor";

const PLANTILLA_NUEVA = JSON.stringify(
  {
    formato: 1,
    nombre: "Mi estrategia",
    monedas: ["BTC"],
    intervalo: "1d",
    entrar: { ">": [{ retorno: { n: 30 } }, 0] },
    salir: { "<=": [{ retorno: { n: 30 } }, 0] },
    tamano: { fraccion: 1, reparto: "una" },
    riesgo: { stop_perdida: null, toma_beneficio: null, stop_que_sigue: null },
    explicacion: "Está en Bitcoin mientras sube en 30 días; si no, en USDC.",
  },
  null,
  2,
);

function TarjetaMedida({ e }: { e: ResumenEstrategia }) {
  return (
    <Tarjeta como="article" className="relative flex flex-col gap-3 p-5 hover:border-linea-control/60">
      <div className="flex flex-wrap items-center gap-2">
        <ChipEstadoEstrategia estado={e.estado} />
        <ChipAutor autor={e.autor} />
      </div>
      <div>
        <h3 className="titular text-xl leading-snug font-semibold text-tinta">
          <Link href={`/estrategias/medida/ficha/?id=${encodeURIComponent(e.id)}`} className="after:absolute after:inset-0 after:rounded-tarjeta hover:underline focus-visible:outline-none">
            {e.nombre}
          </Link>
        </h3>
        <p className="mt-0.5 text-sm text-tinta-suave">
          Versión {e.version} · {e.monedas.join(", ")} · velas de {nombreIntervalo(e.intervalo)} · cambiada el {momento(e.actualizada)}
        </p>
      </div>
      <p className="line-clamp-3 text-[0.9375rem] leading-relaxed text-tinta">{e.explicacion}</p>
      <div className="mt-auto space-y-2 border-t border-linea pt-3">
        <LineaPrueba p={e.ultima_prueba} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-tinta-suave">{e.bots.length ? `La usa${e.bots.length > 1 ? "n" : ""} ${e.bots.length} bot${e.bots.length > 1 ? "s" : ""}` : "Ningún bot la usa"}</span>
          <span className="inline-flex items-center gap-0.5 text-sm font-semibold text-marca" aria-hidden="true">
            Ver ficha <ChevronRight className="h-4 w-4" />
          </span>
        </div>
      </div>
    </Tarjeta>
  );
}

/**
 * Estrategias · A medida (docs/panel-v4-real.md §2 y §4): tu biblioteca de estrategias, escritas
 * con Claude o a mano, con su camino (borrador · probada · en ficticio · real), su version, su
 * autor y su ultima prueba frente a mantener. La puerta principal es "Disenar con Claude".
 */
export function Biblioteca() {
  const router = useRouter();
  const lista = useConsulta("medida:lista", () => pedir(api.GET("/api/medida")));
  const [conversaciones] = useConversaciones();
  const [aMano, setAMano] = useState(false);

  return (
    <div>
      <Encabezado
        titulo="Estrategias"
        bajada="Estrategias a medida: describes lo que quieres, Claude la escribe en un formato cerrado, se prueba sobre el pasado y, si te convence, la pones a funcionar en un bot."
        accion={
          <BotonEnlace href="/estrategias/medida/disenar/" variante="primario">
            <Sparkles aria-hidden="true" className="h-5 w-5" />
            Diseñar con Claude
          </BotonEnlace>
        }
      />
      <NavEstrategias />

      <div className="space-y-12">
        <Seccion
          titulo="Tu biblioteca"
          bajada="Borrador → probada sobre el pasado → en ficticio (se recomiendan 7 días) → con dinero real. Pasar a real solo lo haces tú, desde la ficha de un bot."
          accion={
            <Boton tamano="compacto" onClick={() => setAMano(true)}>
              <PencilLine aria-hidden="true" className="h-4 w-4" />
              Escribir una a mano
            </Boton>
          }
        >
          {lista.error ? <ErrorApiVista error={lista.error} reintentar={lista.recargar} prefijo="No se pudo leer tu biblioteca:" /> : null}
          {!lista.datos && !lista.error ? (
            <div className="space-y-3">
              <CargandoLento texto="Leyendo tus estrategias…" lento="Sigue leyendo tus estrategias…" />
              <div className="grid gap-4 md:grid-cols-2">
                <Esqueleto className="h-60" />
                <Esqueleto className="h-60" />
              </div>
            </div>
          ) : null}
          {lista.datos && !lista.datos.estrategias.length ? (
            <EstadoVacio icono={Sparkles} tono="neutro" titulo="Aún no tienes ninguna estrategia a medida">
              Cuéntale a Claude qué quieres («compra ETH cuando rebote de su mínimo de 30 días y vende si cae un 8 %»): la escribe, la prueba sobre el pasado y te
              enseña sus resultados con sus pegas. Gasta cuota de tu suscripción.
            </EstadoVacio>
          ) : null}
          {lista.datos?.estrategias.length ? (
            <ul className="grid items-stretch gap-4 md:grid-cols-2">
              {lista.datos.estrategias.map((e) => (
                <li key={e.id} className="flex min-w-0 flex-col [&>article]:flex-1">
                  <TarjetaMedida e={e} />
                </li>
              ))}
            </ul>
          ) : null}
        </Seccion>

        {conversaciones.length ? (
          <Seccion titulo="Tus conversaciones con Claude" nivel={2} bajada="Las de este navegador. Cada una guarda lo hablado y las versiones que salieron.">
            <ul className="divide-y divide-linea rounded-tarjeta border border-linea bg-superficie">
              {conversaciones.map((c) => (
                <li key={c.sesion}>
                  <Link
                    href={`/estrategias/medida/disenar/?sesion=${encodeURIComponent(c.sesion)}`}
                    className="flex min-h-14 items-center gap-3 px-4 py-3 hover:bg-superficie-2"
                  >
                    <MessagesSquare aria-hidden="true" className="h-5 w-5 shrink-0 text-marca" strokeWidth={1.75} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[0.9375rem] text-tinta">«{c.titulo}»</span>
                      <span className="block text-sm text-tinta-suave">{momento(c.at)}</span>
                    </span>
                    <ChevronRight aria-hidden="true" className="h-4 w-4 text-tinta-suave" />
                  </Link>
                </li>
              ))}
            </ul>
          </Seccion>
        ) : null}
      </div>

      <Hoja
        abierta={aMano}
        onCerrar={() => setAMano(false)}
        ancho="ancho"
        titulo="Escribir una estrategia a mano"
        bajada="En su formato cerrado (JSON). La API la valida al guardar y te dice en llano lo que no vale. Después, pruébala desde su ficha."
      >
        <EditorEstrategia inicial={PLANTILLA_NUEVA} onGuardada={(d) => router.push(`/estrategias/medida/ficha/?id=${encodeURIComponent(d.id)}&nueva=1`)} />
      </Hoja>
    </div>
  );
}
