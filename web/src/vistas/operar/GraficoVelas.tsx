"use client";

import type {
  CandlestickData,
  HistogramData,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  Time,
  UTCTimestamp,
} from "lightweight-charts";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { api, pedir } from "@/api/cliente";
import type { VelaVivo } from "@/api/tipos";
import { useAlmacenVivo } from "@/api/vivo";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { Segmentado, clases } from "@/componentes/ui";
import { useConsulta } from "@/lib/consulta";
import { INTERVALOS, cantidadMoneda, compacto, nombreIntervalo, precioFijo, type Intervalo } from "@/lib/vivo";

type Lw = typeof import("lightweight-charts");

interface Barra {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface Grafico {
  lw: Lw;
  chart: IChartApi;
  velas: ISeriesApi<"Candlestick">;
  volumen: ISeriesApi<"Histogram">;
  /** Segundos de la ultima vela pintada: lightweight-charts no acepta actualizar una anterior. */
  ultimo: number;
  barras: Barra[];
}

interface Colores {
  fondo: string;
  texto: string;
  rejilla: string;
  eje: string;
  sube: string;
  baja: string;
  cruz: string;
  fuente: string;
}

function leerColores(el: HTMLElement): Colores {
  const s = getComputedStyle(el);
  const v = (n: string, porDefecto: string) => s.getPropertyValue(n).trim() || porDefecto;
  return {
    fondo: v("--superficie", "#ffffff"),
    texto: v("--tinta-suave", "#625e56"),
    rejilla: v("--rejilla", "#ece8e0"),
    eje: v("--eje", "#d3cdc1"),
    sube: v("--sube", "#2f7d5b"),
    baja: v("--baja", "#b5543a"),
    cruz: v("--linea-control", "#8c8679"),
    fuente: getComputedStyle(document.body).fontFamily || "system-ui, sans-serif",
  };
}

/** Un color en hexadecimal con transparencia (el volumen va lavado, no en bloque). */
function conAlfa(hex: string, alfa: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m?.[1]) return hex;
  const n = Number.parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
}

const segundos = (iso: string): number => Math.floor(Date.parse(iso) / 1000);

function aBarra(v: VelaVivo): Barra {
  return { t: segundos(v.inicio), o: v.apertura, h: v.maximo, l: v.minimo, c: v.cierre, v: v.volumen };
}

const FECHA_HORA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const FECHA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });
const HORA = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });
const MES = new Intl.DateTimeFormat("es-ES", { month: "short" });
const sinPunto = (t: string) => t.replace(/\.(?=\s|$)/g, "");

function aFecha(time: Time): Date {
  return typeof time === "number" ? new Date(time * 1000) : new Date(String(time));
}

/**
 * Las velas de una moneda, en vivo (lightweight-charts de TradingView, Apache-2.0: el logotipo de
 * atribucion se deja dentro de la grafica, como pide su licencia).
 *
 * Colores (skill dataviz): sube y baja son los tokens del sistema, con 3:1 o mas sobre la
 * superficie en claro y en oscuro. Bajo daltonismo esa pareja se acerca (dE 6), asi que la forma
 * lo dice tambien: la vela que sube va HUECA y la que baja, RELLENA, y la leyenda lo explica.
 * El volumen, lavado al 35 % abajo. La rejilla y los ejes, filetes recesivos. Leyenda con las
 * cifras de la vela bajo el cursor (o la ultima), resumen para lectores de pantalla y tabla.
 */
export function GraficoVelas({
  coin,
  nombre,
  intervalo,
  onIntervalo,
  decimales,
  decimalesCantidad,
  className,
}: {
  coin: string;
  nombre: string;
  intervalo: Intervalo;
  onIntervalo: (i: Intervalo) => void;
  decimales: number;
  decimalesCantidad: number;
  className?: string;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const grafico = useRef<Grafico | null>(null);
  const [listo, setListo] = useState(false);
  const almacen = useAlmacenVivo();
  const historico = useConsulta(`velas:${coin}:${intervalo}`, () => pedir(api.GET("/api/vivo/velas", { params: { query: { coin, intervalo, limite: 300 } } })));
  const datos = historico.datos && historico.datos.coin === coin && historico.datos.intervalo === intervalo ? historico.datos : null;

  // La leyenda: la vela bajo el cursor o, si no hay cursor, la ultima. Se repinta como mucho
  // cada 200 ms aunque las velas lleguen mas a menudo.
  const [leyenda, setLeyenda] = useState<{ barra: Barra; enCurso: boolean } | null>(null);
  const sobre = useRef(false);
  const pendiente = useRef<{ barra: Barra; enCurso: boolean } | null>(null);
  const temporizador = useRef<number | null>(null);
  const programarLeyenda = useCallback((l: { barra: Barra; enCurso: boolean }) => {
    pendiente.current = l;
    if (temporizador.current !== null) return;
    temporizador.current = window.setTimeout(() => {
      temporizador.current = null;
      setLeyenda(pendiente.current);
    }, 200);
  }, []);

  const formatoRef = useRef({ decimales, decimalesCantidad });
  useEffect(() => {
    formatoRef.current = { decimales, decimalesCantidad };
  });

  // 1) La grafica se crea una vez (la libreria toca el DOM: solo en el navegador).
  useEffect(() => {
    let vivo = true;
    let limpiar = () => {};
    void import("lightweight-charts").then((lw) => {
      const el = contenedor.current;
      if (!vivo || !el) return;
      const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const c = leerColores(el);
      const chart = lw.createChart(el, {
        autoSize: true,
        layout: {
          background: { type: lw.ColorType.Solid, color: c.fondo },
          textColor: c.texto,
          fontFamily: c.fuente,
          fontSize: 12,
          attributionLogo: true,
        },
        grid: { vertLines: { color: c.rejilla }, horzLines: { color: c.rejilla } },
        rightPriceScale: { borderColor: c.eje, scaleMargins: { top: 0.08, bottom: 0.22 } },
        timeScale: {
          borderColor: c.eje,
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 4,
          tickMarkFormatter: (time: Time, tipo: number) => {
            const d = aFecha(time);
            // TickMarkType: 0 año, 1 mes, 2 dia, 3 hora, 4 hora con segundos.
            if (tipo === 0) return String(d.getFullYear());
            if (tipo === 1) return sinPunto(MES.format(d));
            if (tipo === 2) return sinPunto(FECHA.format(d));
            return HORA.format(d);
          },
        },
        crosshair: {
          mode: lw.CrosshairMode.Normal,
          vertLine: { color: c.cruz, width: 1, style: lw.LineStyle.Solid, labelBackgroundColor: c.texto },
          horzLine: { color: c.cruz, width: 1, style: lw.LineStyle.Solid, labelBackgroundColor: c.texto },
        },
        localization: {
          locale: "es-ES",
          priceFormatter: (p: number) => precioFijo(p, formatoRef.current.decimales),
          timeFormatter: (time: Time) => sinPunto(FECHA_HORA.format(aFecha(time))),
        },
        // En el movil, arrastrar en vertical mueve la pagina, no la grafica.
        handleScroll: { vertTouchDrag: false },
        kineticScroll: { touch: !reducido, mouse: false },
      });
      const velas = chart.addSeries(lw.CandlestickSeries, {
        upColor: "rgba(0, 0, 0, 0)",
        borderUpColor: c.sube,
        wickUpColor: c.sube,
        downColor: c.baja,
        borderDownColor: c.baja,
        wickDownColor: c.baja,
        priceLineColor: c.cruz,
        priceLineStyle: lw.LineStyle.Solid,
        priceLineWidth: 1,
      });
      const volumen = chart.addSeries(lw.HistogramSeries, {
        priceScaleId: "",
        priceFormat: { type: "volume" },
        lastValueVisible: false,
        priceLineVisible: false,
      });
      volumen.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      const g: Grafico = { lw, chart, velas, volumen, ultimo: 0, barras: [] };
      grafico.current = g;

      const reaplicar = () => {
        const n = leerColores(el);
        chart.applyOptions({
          layout: { background: { type: lw.ColorType.Solid, color: n.fondo }, textColor: n.texto },
          grid: { vertLines: { color: n.rejilla }, horzLines: { color: n.rejilla } },
          rightPriceScale: { borderColor: n.eje },
          timeScale: { borderColor: n.eje },
          crosshair: { vertLine: { color: n.cruz, labelBackgroundColor: n.texto }, horzLine: { color: n.cruz, labelBackgroundColor: n.texto } },
        });
        velas.applyOptions({ borderUpColor: n.sube, wickUpColor: n.sube, downColor: n.baja, borderDownColor: n.baja, wickDownColor: n.baja, priceLineColor: n.cruz });
        volumen.setData(g.barras.map((b) => barraVolumen(b, n)));
      };
      const tema = new MutationObserver(reaplicar);
      tema.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      const oscuro = window.matchMedia("(prefers-color-scheme: dark)");
      oscuro.addEventListener("change", reaplicar);

      const alMover = (p: MouseEventParams<Time>) => {
        const t = typeof p.time === "number" ? p.time : null;
        // Se busca desde el final: el cursor suele estar en lo reciente.
        let b: Barra | undefined;
        for (let i = g.barras.length - 1; t !== null && i >= 0; i--) {
          const x = g.barras[i];
          if (x && x.t === t) {
            b = x;
            break;
          }
        }
        if (!b) {
          sobre.current = false;
          const ultima = g.barras[g.barras.length - 1];
          if (ultima) programarLeyenda({ barra: ultima, enCurso: true });
          return;
        }
        sobre.current = true;
        programarLeyenda({ barra: b, enCurso: b.t === g.ultimo });
      };
      chart.subscribeCrosshairMove(alMover);
      setListo(true);
      limpiar = () => {
        tema.disconnect();
        oscuro.removeEventListener("change", reaplicar);
        chart.unsubscribeCrosshairMove(alMover);
        chart.remove();
        grafico.current = null;
      };
    });
    return () => {
      vivo = false;
      limpiar();
      if (temporizador.current !== null) window.clearTimeout(temporizador.current);
    };
  }, [programarLeyenda]);

  // 2) El formato de los precios, segun la moneda.
  useEffect(() => {
    const g = grafico.current;
    if (!listo || !g) return;
    g.velas.applyOptions({ priceFormat: { type: "price", precision: decimales, minMove: 10 ** -decimales } });
  }, [listo, decimales]);

  // 3) El historico: al llegar, se pinta entero y se ve el final.
  useEffect(() => {
    const g = grafico.current;
    if (!listo || !g || !contenedor.current) return;
    if (!datos) {
      g.velas.setData([]);
      g.volumen.setData([]);
      g.barras = [];
      g.ultimo = 0;
      return;
    }
    const c = leerColores(contenedor.current);
    g.barras = datos.velas.map(aBarra);
    g.velas.setData(g.barras.map(barraVela));
    g.volumen.setData(g.barras.map((b) => barraVolumen(b, c)));
    g.ultimo = g.barras[g.barras.length - 1]?.t ?? 0;
    const n = g.barras.length;
    g.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 110), to: n + 3 });
    const ultima = g.barras[n - 1];
    if (ultima) programarLeyenda({ barra: ultima, enCurso: true });
  }, [listo, datos, programarLeyenda]);

  // 4) La vela en curso, en vivo: directamente a la grafica, sin pasar por React.
  useEffect(() => {
    return almacen.suscribirVela((v) => {
      const g = grafico.current;
      const el = contenedor.current;
      if (!g || !el || !g.barras.length || v.coin !== coin || v.intervalo !== intervalo) return;
      const b = aBarra(v);
      if (b.t < g.ultimo) return;
      const ultima = g.barras[g.barras.length - 1];
      if (ultima && ultima.t === b.t) g.barras[g.barras.length - 1] = b;
      else g.barras.push(b);
      if (g.barras.length > 2000) g.barras.splice(0, g.barras.length - 1500);
      g.ultimo = b.t;
      g.velas.update(barraVela(b));
      g.volumen.update(barraVolumen(b, leerColoresCache(el)));
      if (!sobre.current) programarLeyenda({ barra: b, enCurso: !v.cerrada });
    });
  }, [almacen, coin, intervalo, programarLeyenda]);

  const ultimaBarra = leyenda?.barra ?? null;
  const resumen = datos
    ? `Velas de ${nombreIntervalo(intervalo)} de ${nombre}: ${datos.velas.length} velas.${ultimaBarra ? ` La ${leyenda?.enCurso ? "vela en curso" : "vela señalada"} abrió a ${precioFijo(ultimaBarra.o, decimales)}, máximo ${precioFijo(ultimaBarra.h, decimales)}, mínimo ${precioFijo(ultimaBarra.l, decimales)} y ${leyenda?.enCurso ? "va por" : "cerró a"} ${precioFijo(ultimaBarra.c, decimales)} USDC.` : ""}`
    : `Cargando las velas de ${nombre}.`;

  return (
    <section aria-labelledby="titulo-velas" className={clases("flex min-w-0 flex-col rounded-tarjeta border border-linea bg-superficie shadow-suave", className)}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-linea px-3 py-2 sm:px-4">
        <h2 id="titulo-velas" className="text-[0.9375rem] font-semibold text-tinta">
          Precio de {nombre} <span className="font-normal text-tinta-suave">· velas de {nombreIntervalo(intervalo)}</span>
        </h2>
        <Segmentado
          etiqueta="Cada vela es"
          ocultarEtiqueta
          opciones={INTERVALOS.map((i) => ({ valor: i.clave, texto: i.texto }))}
          valor={intervalo}
          onCambio={onIntervalo}
          className="[&_label]:min-h-11 [&_label]:px-2.5 [&_label]:text-sm"
        />
      </div>
      <Leyenda leyenda={leyenda} decimales={decimales} decimalesCantidad={decimalesCantidad} coin={coin} />
      <div className="relative min-h-0 flex-1 xl:min-h-[clamp(320px,44vh,520px)]">
        <div
          ref={contenedor}
          role="img"
          aria-label={resumen}
          className={clases("h-[clamp(320px,48vh,560px)] w-full transition-opacity xl:absolute xl:inset-0 xl:h-auto", historico.cargando && !datos ? "opacity-40" : undefined)}
        />
        {historico.error && !datos ? (
          <p className="absolute inset-x-4 top-4 rounded-xl bg-real-suave px-4 py-3 text-sm text-real-tinta" role="alert">
            No se pudieron cargar las velas: {historico.error.detalle}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-linea px-3 py-1.5 text-xs text-tinta-suave sm:px-4">
        <span className="inline-flex items-center gap-1.5">
          <svg width="10" height="14" viewBox="0 0 10 14" aria-hidden="true">
            <line x1="5" y1="0" x2="5" y2="14" stroke="var(--sube)" strokeWidth="1.5" />
            <rect x="1" y="3" width="8" height="8" fill="var(--superficie)" stroke="var(--sube)" strokeWidth="1.5" />
          </svg>
          Hueca: acabó más arriba
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="10" height="14" viewBox="0 0 10 14" aria-hidden="true">
            <line x1="5" y1="0" x2="5" y2="14" stroke="var(--baja)" strokeWidth="1.5" />
            <rect x="1" y="3" width="8" height="8" fill="var(--baja)" stroke="var(--baja)" strokeWidth="1.5" />
          </svg>
          Rellena: acabó más abajo
        </span>
        <QueEsEsto clave="vela" className="[&>button]:min-h-8 [&>button]:text-xs" />
        <span className="ml-auto">
          Gráfico:{" "}
          <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-tinta">
            TradingView Lightweight Charts™
          </a>
        </span>
      </div>
      <TablaVelas grafico={grafico} decimales={decimales} decimalesCantidad={decimalesCantidad} />
    </section>
  );
}

let cacheColores: { el: HTMLElement; t: number; c: Colores } | null = null;
/** Los colores, leidos como mucho una vez por segundo (getComputedStyle en cada vela sobra). */
function leerColoresCache(el: HTMLElement): Colores {
  const ahora = Date.now();
  if (!cacheColores || cacheColores.el !== el || ahora - cacheColores.t > 1000) cacheColores = { el, t: ahora, c: leerColores(el) };
  return cacheColores.c;
}

function barraVela(b: Barra): CandlestickData<UTCTimestamp> {
  return { time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c };
}

function barraVolumen(b: Barra, c: Colores): HistogramData<UTCTimestamp> {
  return { time: b.t as UTCTimestamp, value: b.v, color: conAlfa(b.c >= b.o ? c.sube : c.baja, 0.35) };
}

function Leyenda({
  leyenda,
  decimales,
  decimalesCantidad,
  coin,
}: {
  leyenda: { barra: Barra; enCurso: boolean } | null;
  decimales: number;
  decimalesCantidad: number;
  coin: string;
}) {
  const b = leyenda?.barra;
  const sube = b ? b.c >= b.o : true;
  const cambio = b && b.o ? (b.c / b.o - 1) * 100 : null;
  const dato = (etiqueta: string, valor: string) => (
    <span className="whitespace-nowrap">
      <span className="text-tinta-suave">{etiqueta} </span>
      <span className="cifras font-medium text-tinta">{valor}</span>
    </span>
  );
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-1.5 text-xs sm:px-4" aria-hidden="true">
      <span className="font-medium text-tinta-suave">{b ? (leyenda?.enCurso ? "Vela en curso" : sinPunto(FECHA_HORA.format(new Date(b.t * 1000)))) : "—"}</span>
      {b ? (
        <>
          {dato("Abrió", precioFijo(b.o, decimales))}
          {dato("Máx.", precioFijo(b.h, decimales))}
          {dato("Mín.", precioFijo(b.l, decimales))}
          {dato(leyenda?.enCurso ? "Ahora" : "Cerró", precioFijo(b.c, decimales))}
          {cambio !== null ? (
            <span className={clases("cifras font-semibold", sube ? "text-sube-texto" : "text-baja-texto")}>
              {cambio > 0 ? "+" : cambio < 0 ? "−" : ""}
              {Math.abs(cambio).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %
            </span>
          ) : null}
          {b.v ? dato("Vol.", `${b.v >= 1000 ? compacto(b.v) : cantidadMoneda(b.v, Math.min(decimalesCantidad, 4))} ${coin}`) : null}
        </>
      ) : null}
    </div>
  );
}

/** La gemela en tabla (skill dataviz): las ultimas 30 velas, solo al abrirla. */
function TablaVelas({ grafico, decimales, decimalesCantidad }: { grafico: RefObject<Grafico | null>; decimales: number; decimalesCantidad: number }) {
  const [filas, setFilas] = useState<Barra[] | null>(null);
  return (
    <details
      className="border-t border-linea px-3 sm:px-4"
      onToggle={(e) => setFilas(e.currentTarget.open ? [...(grafico.current?.barras ?? [])].slice(-30).reverse() : null)}
    >
      <summary className="inline-flex min-h-11 cursor-pointer items-center text-sm font-medium text-marca underline underline-offset-4">Ver las últimas velas en tabla</summary>
      {filas ? (
        <div className="relative mb-3 max-h-72 overflow-auto rounded-xl border border-linea">
          <table className="tabla-densa cifras w-full text-xs">
            <caption className="sr-only">Últimas {filas.length} velas, la más reciente primero (foto de cuando abriste la tabla)</caption>
            <thead>
              <tr className="text-left text-tinta-suave">
                <th scope="col" className="px-2 py-1">Empieza</th>
                <th scope="col" className="px-2 py-1 text-right">Abrió</th>
                <th scope="col" className="px-2 py-1 text-right">Máximo</th>
                <th scope="col" className="px-2 py-1 text-right">Mínimo</th>
                <th scope="col" className="px-2 py-1 text-right">Cerró</th>
                <th scope="col" className="px-2 py-1 text-right">Volumen</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((b) => (
                <tr key={b.t} className="border-t border-linea">
                  <td className="px-2 py-0.5">{sinPunto(FECHA_HORA.format(new Date(b.t * 1000)))}</td>
                  <td className="px-2 py-0.5 text-right">{precioFijo(b.o, decimales)}</td>
                  <td className="px-2 py-0.5 text-right">{precioFijo(b.h, decimales)}</td>
                  <td className="px-2 py-0.5 text-right">{precioFijo(b.l, decimales)}</td>
                  <td className="px-2 py-0.5 text-right">{precioFijo(b.c, decimales)}</td>
                  <td className="px-2 py-0.5 text-right">{cantidadMoneda(b.v, Math.min(decimalesCantidad, 4))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </details>
  );
}
