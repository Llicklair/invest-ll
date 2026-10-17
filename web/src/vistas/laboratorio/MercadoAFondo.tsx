"use client";

import { useMemo, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { Tramo } from "@/api/tipos";
import { MAX_SERIES } from "@/componentes/graficas/comun";
import { GraficaComparada, GraficaLinea, type SerieComparada } from "@/componentes/graficas/Lineas";
import { SelectorActivos } from "@/componentes/SelectorActivos";
import { Aviso, Boton, Cargando, ErrorApiVista, Nota, Seccion, Segmentado } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useConsulta } from "@/lib/consulta";
import { numero } from "@/lib/formato";

import { Mesa } from "./Mesa";

const TRAMOS: readonly { valor: Tramo; texto: string }[] = [
  { valor: "3m", texto: "3 meses" },
  { valor: "1a", texto: "1 año" },
  { valor: "5a", texto: "5 años" },
  { valor: "todo", texto: "Todo" },
];

function GraficaActivo({ simbolo, onCerrar }: { simbolo: string; onCerrar: () => void }) {
  const { versionDatos } = useEstado();
  const [tramo, setTramo] = useState<Tramo>("1a");
  const consulta = useConsulta(`serie:${simbolo}:${tramo}:${versionDatos}`, () =>
    pedir(api.GET("/api/mercado/serie", { params: { query: { symbol: simbolo, tramo } } })),
  );
  const serie = consulta.datos;
  const puntos = useMemo(
    () => (serie ? serie.puntos.map((p) => ({ t: Date.parse(p.fecha), v: p.valor })) : []),
    [serie],
  );

  return (
    <Seccion
      titulo={`Gráfica: ${simbolo}`}
      nivel={3}
      id="grafica-activo"
      accion={
        <Boton onClick={onCerrar} className="min-h-7 px-2 py-0.5 text-xs">
          Cerrar gráfica
        </Boton>
      }
    >
      <Segmentado etiqueta="Tramo" opciones={TRAMOS} valor={tramo} onCambio={setTramo} />
      {consulta.error ? <ErrorApiVista error={consulta.error} prefijo={`No se pudo cargar ${simbolo}:`} /> : null}
      {serie && !consulta.desfasados ? (
        <GraficaLinea
          puntos={puntos}
          nombreSerie={`${serie.symbol} (cierre)`}
          cabeceraValor="cierre"
          atenuada={consulta.cargando}
          pie={
            <>
              {serie.sesiones.toLocaleString("es-ES")} sesiones, hasta el <strong>{serie.hasta}</strong>. Datos
              históricos descargados, no precios en vivo.
            </>
          }
        />
      ) : consulta.cargando ? (
        <Cargando texto={`Cargando el histórico de ${simbolo}…`} />
      ) : null}
    </Seccion>
  );
}

const VENTANAS = [
  { valor: "todo", texto: "Todo el histórico" },
  { valor: "1 mes", texto: "1 mes" },
  { valor: "3 meses", texto: "3 meses" },
  { valor: "1 año", texto: "1 año" },
  { valor: "5 años", texto: "5 años" },
] as const;
type Ventana = (typeof VENTANAS)[number]["valor"];

/** Huecos de color fijados a cada activo elegido: quitar uno no repinta a los demas. */
function asignarHuecos(ids: readonly string[], previos: Readonly<Record<string, number>>): Record<string, number> {
  const resultado: Record<string, number> = {};
  const usados = new Set<number>();
  for (const id of ids) {
    const h = previos[id];
    if (h !== undefined && !usados.has(h)) {
      resultado[id] = h;
      usados.add(h);
    }
  }
  for (const id of ids) {
    if (resultado[id] !== undefined) continue;
    let h = 0;
    while (usados.has(h)) h++;
    resultado[id] = h;
    usados.add(h);
  }
  return resultado;
}

function Comparacion() {
  const { estado, versionDatos } = useEstado();
  const activos = useMemo(() => estado?.activos ?? [], [estado]);
  const [ventana, setVentana] = useState<Ventana>("todo");
  const [elegidos, setElegidos] = useState<string[] | null>(null);
  const [huecos, setHuecos] = useState<Record<string, number>>({});

  // Por defecto, los cinco primeros (como el panel viejo), hasta que el operador toque algo.
  const ids = elegidos ?? activos.slice(0, Math.min(5, activos.length)).map((a) => a.id);
  const huecosVigentes = asignarHuecos(ids, huecos);

  const consulta = useConsulta(ids.length ? `comparacion:${ids.join("|")}:${ventana}:${versionDatos}` : null, () =>
    pedir(
      api.GET("/api/mercado/comparacion", {
        params: { query: { activos: ids, ...(ventana === "todo" ? {} : { ventana }) } },
      }),
    ),
  );

  const series = useMemo<SerieComparada[]>(() => {
    const datos = consulta.datos;
    if (!datos) return [];
    const porActivo = new Map<string, { t: number; v: number }[]>();
    for (const p of datos.puntos) {
      const lista = porActivo.get(p.activo) ?? [];
      lista.push({ t: Date.parse(p.fecha), v: p.valor });
      porActivo.set(p.activo, lista);
    }
    // La API identifica cada punto por simbolo; se casa con el id elegido para fijar su color.
    return [...porActivo.entries()].map(([simbolo, puntos]) => {
      const id = ids.find((x) => activos.find((a) => a.id === x)?.symbol === simbolo);
      return {
        nombre: simbolo,
        hueco: id !== undefined ? (huecosVigentes[id] ?? 0) : 0,
        puntos: puntos.sort((a, b) => a.t - b.t),
      };
    });
  }, [consulta.datos, ids, activos, huecosVigentes]);

  const cambiar = (nuevos: string[]) => {
    setHuecos(asignarHuecos(nuevos, huecosVigentes));
    setElegidos(nuevos);
  };

  return (
    <Seccion titulo="Comparación en base 100" id="comparacion">
      <div className="space-y-3">
        <Segmentado etiqueta="Tramo" opciones={VENTANAS} valor={ventana} onCambio={setVentana} />
        <SelectorActivos
          etiqueta="Activos a comparar"
          activos={activos}
          seleccion={ids}
          onCambio={cambiar}
          maximo={MAX_SERIES}
          motivoMaximo="Más de ocho líneas ya no se distinguen por color: quita alguno para añadir otro."
        />
      </div>
      {!ids.length ? (
        <Aviso tipo="info">Elige al menos un activo.</Aviso>
      ) : (
        <>
          {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
          {series.length ? (
            <GraficaComparada
              series={series}
              atenuada={consulta.cargando}
              formatoValor={(v) => numero(v, 1)}
              pie="Todos empiezan en 100 al inicio del tramo. Sin normalizar, Bitcoin a 90.000 aplastaría visualmente al resto aunque el oro lo hubiera batido."
            />
          ) : consulta.cargando ? (
            <Cargando texto="Calculando la comparación…" />
          ) : null}
        </>
      )}
    </Seccion>
  );
}

/**
 * Como va cada cosa, sin recomendar nada. Deliberadamente aburrida: sin "miedo y codicia" ni
 * "temporada de altcoins", que existen para que operes mas.
 */
export function Panorama({
  elegido,
  onElegir,
}: {
  elegido: string | null;
  onElegir: (simbolo: string | null) => void;
}) {
  const { versionDatos } = useEstado();
  const consulta = useConsulta(`rendimiento:${versionDatos}`, () => pedir(api.GET("/api/mercado/rendimiento")));
  const datos = consulta.datos;

  return (
    <div className="space-y-8">
      <Seccion titulo="Rendimiento por periodo" id="rendimiento">
        <Nota>
          Rendimiento sobre el HISTÓRICO descargado (las cotizaciones al momento están arriba). Aquí solo aparece lo
          que tiene serie completa: gráficas, backtests y alertas salen de estos datos.
        </Nota>
        {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
        {!datos && consulta.cargando ? <Cargando texto="Leyendo los históricos…" /> : null}
        {datos && datos.bolsa.length + datos.cripto.length === 0 ? (
          <Aviso tipo="info">No hay históricos que mostrar.</Aviso>
        ) : null}
        {datos ? (
          <div className={consulta.cargando ? "space-y-4 opacity-60" : "space-y-4"}>
            {datos.bolsa.length ? (
              <Mesa titulo="Bolsa" filas={datos.bolsa} elegido={elegido} onElegir={onElegir} />
            ) : null}
            {datos.cripto.length ? (
              <Mesa titulo="Cripto" filas={datos.cripto} elegido={elegido} onElegir={onElegir} />
            ) : null}
          </div>
        ) : null}
        <Nota>
          <strong className="text-tinta">La columna que más importa es «desde máximo»</strong>: un activo que subió un
          40% este año pero sigue un 30% por debajo de su pico no está yendo bien, se está recuperando de una caída que
          alguien sufrió. Un hueco (—) significa que no hay histórico suficiente para esa ventana, no que rindiera un
          0%. Pincha una cabecera para ordenar, y una fila para ver su gráfica.
        </Nota>
      </Seccion>

      {elegido ? <GraficaActivo key={elegido} simbolo={elegido} onCerrar={() => onElegir(null)} /> : null}

      <Comparacion />
    </div>
  );
}
