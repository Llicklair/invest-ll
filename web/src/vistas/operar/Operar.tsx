"use client";

import { useEffect, useId, useMemo, useState, useSyncExternalStore } from "react";

import type { CanalVivo, MonedaVivo } from "@/api/tipos";
import { ProveedorVivo, useVivo } from "@/api/vivo";
import { CambioPct } from "@/componentes/CifraGrande";
import { EstadoEnVivo, RotuloFicticio } from "@/componentes/EnVivo";
import { Pestanas } from "@/componentes/Pestanas";
import { Aviso, Esqueleto, clases } from "@/componentes/ui";
import { useGuardado } from "@/lib/almacen";
import { compacto, decimalesPrecio, esIntervalo, extremos, precioFijo, type Intervalo } from "@/lib/vivo";

import { Boleto, type PresetBoleto } from "./Boleto";
import { ListasCuenta, ResumenCuenta } from "./Cuenta";
import { GraficoVelas } from "./GraficoVelas";
import { Libro, UltimasOperaciones } from "./Libro";
import { SelectorMoneda } from "./SelectorMoneda";

const CANALES: readonly CanalVivo[] = ["monedas", "libro", "operaciones", "vela", "cuenta", "estado"];

const MOVIL = "(max-width: 1023.98px)";
function suscribirMovil(aviso: () => void): () => void {
  const mq = window.matchMedia(MOVIL);
  mq.addEventListener("change", aviso);
  return () => mq.removeEventListener("change", aviso);
}
/** Si se ve como movil (pestanas) o como escritorio (todo a la vez). En el HTML exportado, escritorio. */
function useEsMovil(): boolean {
  return useSyncExternalStore(
    suscribirMovil,
    () => window.matchMedia(MOVIL).matches,
    () => false,
  );
}

/**
 * Operar (docs/panel-v3-vivo.md, seccion 2): la pantalla de exchange de la cuenta de practica,
 * al estilo de Hyperliquid. En escritorio, grafico grande, libro al lado y boleto a la derecha,
 * con la cuenta debajo; en el movil, por pestanas (Grafico · Libro · Operar · Cuenta).
 */
export function Operar() {
  const [coin, setCoin] = useGuardado("local", "invest-ll.operar.coin", "BTC");
  const [guardado, setIntervalo] = useGuardado("local", "invest-ll.operar.intervalo", "1h");
  const intervalo: Intervalo = esIntervalo(guardado) ? guardado : "1h";
  return (
    <ProveedorVivo coin={coin} intervalo={intervalo} canales={CANALES}>
      <PantallaOperar coin={coin} intervalo={intervalo} onCoin={setCoin} onIntervalo={setIntervalo} />
    </ProveedorVivo>
  );
}

type PestanaMovil = "grafico" | "libro" | "operar" | "cuenta";

function PantallaOperar({
  coin,
  intervalo,
  onCoin,
  onIntervalo,
}: {
  coin: string;
  intervalo: Intervalo;
  onCoin: (c: string) => void;
  onIntervalo: (i: Intervalo) => void;
}) {
  const monedas = useVivo("monedas");
  const lista = useMemo(() => monedas?.monedas ?? [], [monedas]);
  const porCoin = useMemo(() => new Map(lista.map((m) => [m.coin, m] as const)), [lista]);
  const moneda = porCoin.get(coin);
  const esMovil = useEsMovil();
  const [pestana, setPestana] = useState<PestanaMovil>("grafico");
  const [lado, setLado] = useState<"libro" | "operaciones">("libro");
  const [preset, setPreset] = useState<{ n: number; inicial?: PresetBoleto }>({ n: 0 });
  const idPanel = useId();
  const idLibro = useId();

  // Una moneda guardada que ya no existe: la primera de la lista.
  useEffect(() => {
    const primera = lista[0];
    if (primera && !porCoin.has(coin)) onCoin(primera.coin);
  }, [lista, porCoin, coin, onCoin]);

  const ver = (p: PestanaMovil | PestanaMovil[]) => (Array.isArray(p) ? p.includes(pestana) : p === pestana) || !esMovil;
  const oculto = (p: PestanaMovil | PestanaMovil[]) => (ver(p) ? undefined : "hidden");

  const vender = (c: string) => {
    onCoin(c);
    setPreset((x) => ({ n: x.n + 1, inicial: { lado: "venta", porcentaje: 1 } }));
    if (esMovil) setPestana("operar");
  };

  const dec = moneda?.decimales_cantidad ?? 4;
  const decP = moneda ? decimalesPrecio(moneda.precio, moneda.decimales_cantidad) : 2;

  return (
    <div className="space-y-3">
      <Cabecera lista={lista} coin={coin} moneda={moneda} onCoin={onCoin} decP={decP} />
      {monedas && !monedas.estado.conectado && monedas.estado.aviso ? (
        <Aviso tipo="aviso" titulo="No llegan precios de Hyperliquid">
          {monedas.estado.aviso}
        </Aviso>
      ) : null}

      {esMovil ? (
        <Pestanas
          etiqueta="Partes de la pantalla"
          idPanel={idPanel}
          actual={pestana}
          onCambio={setPestana}
          pestanas={[
            { clave: "grafico", texto: "Gráfico" },
            { clave: "libro", texto: "Libro" },
            { clave: "operar", texto: "Operar" },
            { clave: "cuenta", texto: "Cuenta" },
          ]}
        />
      ) : null}

      <div
        id={idPanel}
        role={esMovil ? "tabpanel" : undefined}
        aria-labelledby={esMovil ? `pestana-${pestana}` : undefined}
        className={clases(
          "grid gap-3",
          "lg:grid-cols-[minmax(0,1fr)_340px] lg:[grid-template-areas:'grafico_grafico''libro_boleto''cuenta_cuenta']",
          "xl:grid-cols-[minmax(0,1fr)_292px_324px] xl:[grid-template-areas:'grafico_libro_boleto''cuenta_cuenta_boleto']",
        )}
      >
        <div className={clases("min-w-0 lg:[grid-area:grafico]", oculto("grafico"))}>
          {moneda ? (
            <GraficoVelas
              coin={coin}
              nombre={moneda.nombre}
              intervalo={intervalo}
              onIntervalo={onIntervalo}
              decimales={decP}
              decimalesCantidad={dec}
              className="h-full"
            />
          ) : (
            <Esqueleto className="h-[clamp(320px,48vh,560px)]" />
          )}
        </div>

        <section
          aria-label={`Libro y operaciones de ${moneda?.nombre ?? coin}`}
          className={clases("min-w-0 overflow-hidden rounded-tarjeta border border-linea bg-superficie shadow-suave lg:[grid-area:libro]", oculto("libro"))}
        >
          {esMovil ? (
            <>
              <h2 className="border-b border-linea px-3 py-2 text-[0.9375rem] font-semibold text-tinta">Libro de órdenes</h2>
              <Libro coin={coin} decimales={decP} decimalesCantidad={dec} filas={10} />
              <h2 className="border-y border-linea px-3 py-2 text-[0.9375rem] font-semibold text-tinta">Últimas operaciones</h2>
              <UltimasOperaciones coin={coin} decimales={decP} decimalesCantidad={dec} filas={16} />
            </>
          ) : (
            <>
              <div className="px-1">
                <Pestanas
                  etiqueta="Libro u operaciones"
                  idPanel={idLibro}
                  actual={lado}
                  onCambio={setLado}
                  pestanas={[
                    { clave: "libro", texto: "Libro" },
                    { clave: "operaciones", texto: "Operaciones" },
                  ]}
                />
              </div>
              <div id={idLibro} role="tabpanel" aria-labelledby={`pestana-${lado}`}>
                {lado === "libro" ? (
                  <Libro coin={coin} decimales={decP} decimalesCantidad={dec} filas={10} />
                ) : (
                  <UltimasOperaciones coin={coin} decimales={decP} decimalesCantidad={dec} filas={24} />
                )}
              </div>
            </>
          )}
        </section>

        <div className={clases("flex min-w-0 flex-col gap-3 lg:[grid-area:boleto]", oculto(["operar", "cuenta"]))}>
          <div className={oculto("operar")}>
            {moneda ? <Boleto key={`${coin}-${preset.n}`} moneda={moneda} inicial={preset.inicial} /> : <Esqueleto className="h-[30rem]" />}
          </div>
          <ResumenCuenta />
        </div>

        <ListasCuenta monedas={porCoin} onVender={vender} compacta={esMovil} className={clases("lg:[grid-area:cuenta]", oculto("cuenta"))} />
      </div>
    </div>
  );
}

function Cabecera({
  lista,
  coin,
  moneda,
  onCoin,
  decP,
}: {
  lista: readonly MonedaVivo[];
  coin: string;
  moneda: MonedaVivo | undefined;
  onCoin: (c: string) => void;
  decP: number;
}) {
  // El precio de la cabecera es el medio del libro (llega 5 veces por segundo); si aun no hay
  // libro, el de la lista de monedas (cada segundo).
  const libro = useVivo("libro");
  const { medio } = extremos(libro && libro.coin === coin ? libro : null);
  const precio = medio ?? moneda?.precio ?? null;
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <h1 className="titular text-[1.625rem] leading-none font-semibold text-tinta">Operar</h1>
      <SelectorMoneda monedas={lista} coin={coin} onElegir={onCoin} />
      <dl className="flex flex-wrap items-end gap-x-5 gap-y-1">
        <div>
          <dt className="sr-only">Precio de {moneda?.nombre ?? coin}</dt>
          <dd className="cifras text-[1.5rem] leading-none font-semibold tracking-tight text-tinta">
            {precioFijo(precio, decP)} <span className="text-sm font-normal text-tinta-suave">USDC</span>
          </dd>
        </div>
        <div className="text-sm">
          <dt className="text-xs text-tinta-suave">24 h</dt>
          <dd>
            <CambioPct pct={moneda?.var_24h ?? null} />
          </dd>
        </div>
        <div className="text-sm max-sm:hidden">
          <dt className="text-xs text-tinta-suave">Volumen 24 h</dt>
          <dd className="cifras font-medium text-tinta">{compacto(moneda?.volumen_24h)} USDC</dd>
        </div>
      </dl>
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 xl:ml-auto">
        <RotuloFicticio />
        <EstadoEnVivo />
      </div>
    </header>
  );
}
