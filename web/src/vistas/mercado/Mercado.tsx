"use client";

import { ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { FilaRendimiento, Tramo } from "@/api/tipos";
import { CambioPct } from "@/componentes/CifraGrande";
import { SeccionDatos } from "@/componentes/DatosAlDia";
import { GraficaLinea } from "@/componentes/graficas/Lineas";
import { Sparkline } from "@/componentes/graficas/Sparkline";
import { Hoja } from "@/componentes/Hoja";
import { Aviso, Cargando, Desplegable, ESTILO_ENTRADA, Encabezado, ErrorApiVista, Esqueleto, Segmentado, Tarjeta, clases } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useConsulta } from "@/lib/consulta";
import { fechaCorta, numero, precio, simboloMoneda } from "@/lib/formato";
import { enLaMoneda } from "@/lib/nombres";

import { Cotizaciones } from "./Cotizaciones";
import { PreciosPorActivo } from "./Datos";

const TRAMOS: readonly { valor: Tramo; texto: string }[] = [
  { valor: "3m", texto: "3 meses" },
  { valor: "1a", texto: "1 año" },
  { valor: "5a", texto: "5 años" },
  { valor: "todo", texto: "Todo" },
];

function HojaActivo({ fila, onCerrar }: { fila: FilaRendimiento | null; onCerrar: () => void }) {
  return (
    <Hoja
      abierta={fila !== null}
      onCerrar={onCerrar}
      titulo={fila?.nombre ?? ""}
      bajada={fila ? `${fila.que_es && fila.que_es !== fila.nombre ? `${fila.que_es} · ` : ""}precios ${enLaMoneda(fila.moneda)}` : undefined}
    >
      {fila ? <Grafica fila={fila} /> : null}
    </Hoja>
  );
}

function Grafica({ fila }: { fila: FilaRendimiento }) {
  const { versionDatos } = useEstado();
  const [tramo, setTramo] = useState<Tramo>("1a");
  const consulta = useConsulta(`serie:${fila.activo}:${tramo}:${versionDatos}`, () =>
    pedir(api.GET("/api/mercado/serie", { params: { query: { symbol: fila.activo, tramo } } })),
  );
  const serie = consulta.datos;
  const puntos = useMemo(() => (serie ? serie.puntos.map((p) => ({ t: Date.parse(p.fecha), v: p.valor })) : []), [serie]);
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-3">
        {[
          ["Último precio", `${precio(fila.ultimo)} ${simboloMoneda(fila.moneda)} · ${fechaCorta(fila.datos_hasta)}`],
          ["En un mes", fila.var_1m],
          ["En un año", fila.var_1a],
          ["Desde su máximo", fila.desde_maximo],
        ].map(([t, v]) => (
          <div key={String(t)} className="rounded-xl bg-superficie-2 px-4 py-3">
            <dt className="text-sm text-tinta-suave">{t}</dt>
            <dd className="mt-0.5 text-lg font-semibold text-tinta">
              {typeof v === "number" || v === null ? (
                <CambioPct pct={v as number | null} neutro={t === "Desde su máximo"} />
              ) : (
                <span className="cifras">{v}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <Segmentado etiqueta="Periodo" opciones={TRAMOS} valor={tramo} onCambio={setTramo} />
      {consulta.error ? <ErrorApiVista error={consulta.error} reintentar={consulta.recargar} /> : null}
      {serie && !consulta.desfasados ? (
        <GraficaLinea
          puntos={puntos}
          nombreSerie={`${fila.nombre} (precio de cierre, ${simboloMoneda(fila.moneda)})`}
          cabeceraValor="cierre"
          alto={260}
          atenuada={consulta.cargando}
          pie={<>Hasta el {fechaCorta(serie.hasta)}. Datos históricos descargados, no precios en vivo.</>}
        />
      ) : consulta.cargando ? (
        <Cargando texto="Cargando el histórico…" />
      ) : null}
    </div>
  );
}

function Fila({ f, onElegir }: { f: FilaRendimiento; onElegir: () => void }) {
  const nombre = f.nombre;
  return (
    <li>
      <button
        type="button"
        onClick={onElegir}
        className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-5 py-4 text-left hover:bg-superficie-2 sm:grid-cols-[minmax(0,1.6fr)_7rem_6rem_6rem_7rem_1.25rem] sm:px-6"
      >
        <span className="min-w-0">
          {/* El nombre llano entero (en el movil, en dos lineas): cortado no se sabia que bonos eran. */}
          <span className="block font-semibold text-tinta">{nombre}</span>
          <span className="cifras block truncate text-sm text-tinta-suave">
            {precio(f.ultimo)} {simboloMoneda(f.moneda)} · {fechaCorta(f.datos_hasta)}
          </span>
        </span>
        <span className="hidden sm:block" aria-hidden="true">
          <Sparkline valores={f.sparkline} ancho={104} alto={28} />
        </span>
        <span className="text-right">
          <span className="block text-xs text-tinta-suave sm:hidden">un mes</span>
          <CambioPct pct={f.var_1m} />
        </span>
        <span className="hidden text-right sm:block">
          <CambioPct pct={f.var_1a} />
        </span>
        <span className="hidden text-right sm:block">
          <CambioPct pct={f.desde_maximo} neutro />
        </span>
        <ChevronRight aria-hidden="true" className="hidden h-5 w-5 text-tinta-suave sm:block" />
      </button>
    </li>
  );
}

function Lista({ titulo, filas, onElegir }: { titulo: string; filas: FilaRendimiento[]; onElegir: (f: FilaRendimiento) => void }) {
  if (!filas.length) return null;
  return (
    <section aria-label={titulo} className="space-y-3">
      <h2 className="titular text-xl font-semibold text-tinta">{titulo}</h2>
      <Tarjeta className="overflow-hidden">
        <div
          className="hidden grid-cols-[minmax(0,1.6fr)_7rem_6rem_6rem_7rem_1.25rem] gap-x-4 border-b border-linea px-6 py-2.5 text-sm text-tinta-suave sm:grid"
          aria-hidden="true"
        >
          <span>Qué</span>
          <span>3 meses</span>
          <span className="text-right">Un mes</span>
          <span className="text-right">Un año</span>
          <span className="text-right">Desde su máximo</span>
          <span />
        </div>
        <ul className="divide-y divide-linea">
          {filas.map((f) => (
            <Fila key={f.activo} f={f} onElegir={() => onElegir(f)} />
          ))}
        </ul>
      </Tarjeta>
    </section>
  );
}

/**
 * Mercado (docs/panel-v2.md, 4.5): como van las cosas, con nombres llanos y su fecha. Sin
 * "ganadores del dia" ni nada que empuje a operar. Pinchar abre la grafica en una hoja.
 */
export function Mercado() {
  const { versionDatos } = useEstado();
  const consulta = useConsulta(`rendimiento:${versionDatos}`, () => pedir(api.GET("/api/mercado/rendimiento")));
  const [busca, setBusca] = useState("");
  const [elegida, setElegida] = useState<FilaRendimiento | null>(null);
  const d = consulta.datos;
  const q = busca.trim().toLowerCase();
  const filtrar = (xs: FilaRendimiento[]) =>
    q ? xs.filter((x) => `${x.nombre} ${x.activo} ${x.que_es}`.toLowerCase().includes(q)) : xs;

  const verGrafica = (simbolo: string) => {
    const f = d ? [...d.bolsa, ...d.cripto].find((x) => x.activo === simbolo) : undefined;
    if (f) setElegida(f);
  };

  return (
    <div>
      <Encabezado
        titulo="Mercados"
        bajada="Cómo han ido el oro, la bolsa o el bitcoin. No es una señal de nada: es lo que ha pasado, con su fecha."
      />
      <div className="relative mb-8 max-w-md">
        <label htmlFor="buscar" className="sr-only">
          Buscar
        </label>
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-4 h-5 w-5 -translate-y-1/2 text-tinta-suave" />
        <input
          id="buscar"
          type="search"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar: oro, bitcoin, bolsa…"
          className={clases(ESTILO_ENTRADA, "pl-12")}
        />
      </div>

      {consulta.error ? <ErrorApiVista error={consulta.error} reintentar={consulta.recargar} /> : null}
      {!d && consulta.cargando ? (
        <div className="space-y-4" aria-busy="true">
          <Esqueleto className="h-72" />
          <Esqueleto className="h-48" />
        </div>
      ) : null}
      {d ? (
        <div className={clases("space-y-8", consulta.cargando && "opacity-70")}>
          {d.bolsa.length + d.cripto.length === 0 ? <Aviso tipo="info">No hay datos descargados todavía.</Aviso> : null}
          {q && filtrar(d.bolsa).length + filtrar(d.cripto).length === 0 ? (
            <p className="text-[0.9375rem] text-tinta-suave">Nada coincide con «{busca}».</p>
          ) : null}
          <Lista titulo="Bolsa, bonos y oro" filas={filtrar(d.bolsa)} onElegir={setElegida} />
          <Lista titulo="Criptomonedas" filas={filtrar(d.cripto)} onElegir={setElegida} />
          <p className="text-sm text-tinta-suave">
            «Desde su máximo» es lo que más importa: algo que subió un {numero(40, 0)} % este año pero sigue un 30 % por debajo de su
            pico se está recuperando de una caída, no yendo bien.
          </p>
        </div>
      ) : null}

      <div className="mt-12 space-y-4">
        <Desplegable resumen="Cotizaciones al momento (una foto con su hora)">
          <Cotizaciones onVerGrafica={verGrafica} />
        </Desplegable>
        <Desplegable resumen="De cuándo son los precios, y actualizarlos">
          <SeccionDatos />
          <PreciosPorActivo />
        </Desplegable>
      </div>

      <HojaActivo fila={elegida} onCerrar={() => setElegida(null)} />
    </div>
  );
}
