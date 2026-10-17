"use client";

import { Bot, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { ConfigMcp, EstadoExchange, ExchangeDisponible } from "@/api/tipos";
import { Aviso, BloqueComandos, CargandoLento, Codigo, ErrorApiVista, Esqueleto, Seccion, Tarjeta, clases } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";
import { momento } from "@/lib/formato";

import { AsistenteExchange, ChipEstadoExchange } from "./AsistenteExchange";
import { TarjetaModoPlan } from "./Conexion";

/** Lo que se sabe de cada red, en una linea: "Pruebas: claves guardadas, probadas el 17 oct". */
function LineaRedes({ estado, disponible }: { estado: EstadoExchange; disponible: ExchangeDisponible }) {
  const partes = estado.redes.map((r) => {
    const nombre = r.red === "pruebas" ? "Pruebas" : "Dinero real";
    if (!r.claves_guardadas) return `${nombre}: sin claves`;
    if (r.origen === "entorno") return `${nombre}: claves del entorno`;
    return `${nombre}: claves guardadas${r.comprobado ? `, probadas el ${momento(r.comprobado)}` : ", sin probar"}`;
  });
  if (!disponible.tiene_pruebas) partes.unshift("Sin red de pruebas");
  return <p className="mt-0.5 text-sm text-tinta-suave">{partes.join(" · ")}</p>;
}

/** Una letra en un circulo: los exchanges no llevan su logo (nada de marcas ajenas en el panel). */
function Inicial({ nombre, activo }: { nombre: string; activo: EstadoExchange["activo"] }) {
  return (
    <span
      aria-hidden="true"
      className={clases(
        "titular flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-lg font-semibold",
        activo === "real" ? "bg-real-suave text-real-tinta" : activo === "pruebas" ? "bg-pruebas-suave text-pruebas-tinta" : "bg-superficie-2 text-tinta-suave",
      )}
    >
      {nombre.charAt(0)}
    </span>
  );
}

function ListaExchanges() {
  const [version, setVersion] = useState(0);
  const conexiones = useConsulta(`conexiones:${version}`, () => pedir(api.GET("/api/conexiones")));
  const disponibles = useConsulta("conexiones:disponibles", () => pedir(api.GET("/api/conexiones/disponibles")));
  const [abierto, setAbierto] = useState<string | null>(null);
  const recargar = () => setVersion((v) => v + 1);

  const error = conexiones.error ?? disponibles.error;
  if (!conexiones.datos || !disponibles.datos) {
    if (error) return <ErrorApiVista error={error} prefijo="No se pudieron leer las conexiones:" reintentar={() => (conexiones.error ? conexiones.recargar() : disponibles.recargar())} />;
    return (
      <div className="space-y-3">
        <CargandoLento texto="Leyendo tus exchanges…" lento="Sigue leyendo tus exchanges…" />
        <Esqueleto className="h-64" />
      </div>
    );
  }

  const estados = new Map(conexiones.datos.exchanges.map((e) => [e.id, e]));
  const filas = disponibles.datos
    .map((d) => ({ d, e: estados.get(d.id) }))
    .filter((x): x is { d: ExchangeDisponible; e: EstadoExchange } => x.e !== undefined);
  const conectados = filas.filter((x) => x.e.activo !== "sin_conectar").length;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[0.9375rem] text-tinta-suave">
          {conectados === 0
            ? "Aún no has conectado ningún exchange. Empieza por la red de pruebas de uno: dinero ficticio, órdenes de verdad."
            : `${conectados} de ${filas.length} conectados. Ninguno es especial: cada bot elige el suyo.`}
        </p>
        <ul className="mt-3 overflow-hidden rounded-tarjeta border border-linea bg-superficie shadow-suave">
          {filas.map(({ d, e }) => {
            const esAbierto = abierto === d.id;
            const idPanel = `exchange-${d.id}`;
            return (
              <li key={d.id} className="border-b border-linea last:border-b-0">
                <div className="flex items-center gap-x-3 px-4 py-4 sm:gap-x-4 sm:px-6">
                  <Inicial nombre={d.nombre} activo={e.activo} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <h3 className="text-lg font-semibold text-tinta">{d.nombre}</h3>
                      <ChipEstadoExchange activo={e.activo} />
                    </div>
                    <LineaRedes estado={e} disponible={d} />
                  </div>
                  <button
                    type="button"
                    aria-expanded={esAbierto}
                    aria-controls={idPanel}
                    onClick={() => setAbierto(esAbierto ? null : d.id)}
                    className="inline-flex min-h-11 items-center gap-1.5 rounded-xl px-3 text-[0.9375rem] font-semibold text-marca hover:bg-marca-suave"
                  >
                    {esAbierto ? "Cerrar" : e.activo === "sin_conectar" ? "Conectar" : "Ver"}
                    <span className="sr-only"> {d.nombre}</span>
                    <ChevronDown aria-hidden="true" className={clases("h-4 w-4 transition-transform", esAbierto && "rotate-180")} />
                  </button>
                </div>
                {esAbierto ? <AsistenteExchange id={idPanel} exchange={d} estado={e} onCambio={recargar} /> : null}
              </li>
            );
          })}
        </ul>
      </div>
      <ConectarClaude mcp={conexiones.datos.mcp} />
    </div>
  );
}

/** El bloque para anadir el conector MCP de INVEST LL a Claude Code o Claude Desktop. */
function ConectarClaude({ mcp }: { mcp: ConfigMcp }) {
  return (
    <Seccion
      nivel={3}
      titulo="Conectar con Claude"
      id="claude"
      bajada="Para hablar con tu sistema desde Claude Code o Claude Desktop, con las mismas herramientas que usa «Diseñar con Claude»."
    >
      <Tarjeta className="space-y-5 p-5 sm:p-6">
        <Aviso tipo="info" titulo="Qué puede y qué no puede hacer Claude con él">
          {mcp.nota}
        </Aviso>
        <div className="space-y-2">
          <p className="text-[0.9375rem] text-tinta">
            Pega este bloque en la configuración de Claude Code (el fichero <Codigo>.mcp.json</Codigo> de tu proyecto) o de Claude Desktop (Ajustes → Desarrollador →
            Editar configuración):
          </p>
          <BloqueComandos lineas={mcp.bloque_json.split("\n")} />
          <p className="text-sm text-tinta-suave">
            Arranca con <Codigo>{[mcp.comando, ...mcp.argumentos].join(" ")}</Codigo>. Lo que hagas desde allí gasta cuota de tu suscripción de Claude.
          </p>
        </div>
      </Tarjeta>
    </Seccion>
  );
}

/**
 * Conexiones (docs/panel-v4-real.md §4; su propia seccion desde docs/panel-v5.md): el modo de tu plan (lo que la pildora de arriba
 * dice), la lista de exchanges con su estado y el asistente de cada uno, y el conector con Claude.
 */
export function Conexiones() {
  return (
    <div className="space-y-8">
      <TarjetaModoPlan
        pie={
          <>
            Es el de lo que toca hoy en Invertir. Los bots no lo usan: cada uno lleva su modo y su exchange (en{" "}
            <Link href="/bots/" className="font-semibold text-marca underline underline-offset-4">
              Bots
            </Link>
            ). Para cambiarlo: Binance → «Para tu plan».
          </>
        }
      />
      <div className="space-y-3">
        <h3 className="flex items-center gap-2 text-base font-semibold text-tinta">
          <Bot aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
          Exchanges
        </h3>
        <ListaExchanges />
      </div>
    </div>
  );
}
