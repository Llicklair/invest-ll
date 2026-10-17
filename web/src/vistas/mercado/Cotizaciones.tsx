"use client";

import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { Cotizacion, Cotizaciones as FotoCotizaciones } from "@/api/tipos";
import { MarcoTabla, Td, TdVariacion, Th } from "@/componentes/tabla";
import { Aviso, Boton, Cargando, CampoTexto, ErrorApiVista, Nota, Seccion, clases } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion } from "@/lib/consulta";
import { momento, numero, porcentaje, precio } from "@/lib/formato";
import { nombreLlano } from "@/lib/nombres";

type Mercado = "equity" | "crypto";

// La ultima foto sobrevive a cambiar de pestana (como el session_state de Streamlit), pero nunca
// se refresca sola: un panel que se actualiza solo es una notificacion con otro nombre.
let fotoGuardada: FotoCotizaciones | null = null;

function normal(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function TablaViva({
  titulo,
  filas,
  total,
  elegido,
  onElegir,
}: {
  titulo: string;
  filas: Cotizacion[];
  total: number;
  elegido: string | null;
  onElegir: (activo: string) => void;
}) {
  return (
    // min-w-0: sin el, la tabla (que no parte lineas) ensanchaba la columna de la rejilla y con
    // ella la pagina entera (608 px en un movil de 390).
    <div className="min-w-0 space-y-1.5">
      <h3 className="text-[0.9375rem] font-semibold text-tinta">
        {titulo} <span className="font-normal text-tinta-suave">— {filas.length} de {total}, de más a menos negociados</span>
      </h3>
      {filas.length ? (
        <MarcoTabla etiqueta={`Cotizaciones de ${titulo.toLowerCase()}`} altoMaximo={360}>
          <thead>
            <tr>
              <Th>qué</Th>
              <Th numerica>precio</Th>
              <Th numerica>en 24 h</Th>
              <Th numerica>negociado en 24 h</Th>
              <Th>en el panel</Th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => {
              const activo = f.activo === elegido;
              const nombre = nombreLlano(f.activo);
              return (
                <tr
                  key={f.activo}
                  onClick={() => onElegir(f.activo)}
                  className={clases("cursor-pointer hover:bg-superficie-2", activo && "bg-superficie-2")}
                >
                  {/* El nombre se parte en dos lineas: si no, uno largo ("Tecnologicas de EE.UU.
                      (Nasdaq 100)") ensanchaba la columna y en el movil el precio quedaba fuera. */}
                  <Td className="min-w-[8.5rem] whitespace-normal">
                    <button
                      type="button"
                      aria-pressed={activo}
                      onClick={(e) => {
                        e.stopPropagation();
                        onElegir(f.activo);
                      }}
                      className="block max-w-[10rem] text-left font-medium text-tinta underline-offset-2 hover:underline"
                    >
                      {nombre}
                      {nombre !== f.activo ? <span className="block text-xs font-normal text-tinta-suave">{f.activo}</span> : null}
                    </button>
                  </Td>
                  <Td numerica>{precio(f.precio)}</Td>
                  <TdVariacion valor={f.var_24h} texto={porcentaje(f.var_24h, 2)} />
                  <Td numerica>{f.volumen_24h_m === null ? "—" : `${numero(f.volumen_24h_m, 1)} M`}</Td>
                  <Td className="text-tinta-suave">{f.descargado ? "sí" : "—"}</Td>
                </tr>
              );
            })}
          </tbody>
        </MarcoTabla>
      ) : null}
    </div>
  );
}

export function Cotizaciones({ onVerGrafica }: { onVerGrafica: (simbolo: string) => void }) {
  const { refrescarDatos } = useEstado();
  const [foto, setFoto] = useState<FotoCotizaciones | null>(() => fotoGuardada);
  const [filtro, setFiltro] = useState("");
  const [elegido, setElegido] = useState<{ activo: string; mercado: Mercado } | null>(null);

  const traer = useAccion(async () => {
    const r = await pedir(api.POST("/api/mercado/cotizaciones"));
    fotoGuardada = r;
    setFoto(r);
    return r;
  });

  const descargar = useAccion(async (simbolo: string, mercado: Mercado) => {
    const r = await pedir(api.POST("/api/mercado/descargar", { body: { symbol: simbolo, mercado } }));
    // Como el st.rerun() del panel viejo: las mesas, la comparacion y la cabecera se releen.
    if (r.ok) refrescarDatos();
    return r;
  });

  const q = normal(filtro.trim());
  const filtrar = (xs: Cotizacion[]) => (q ? xs.filter((x) => normal(`${nombreLlano(x.activo)} ${x.activo}`).includes(q)) : xs);

  const elegir = (activo: string, mercado: Mercado) => {
    setElegido({ activo, mercado });
    descargar.limpiar();
  };

  const cotizacionElegida =
    elegido && foto
      ? [...foto.bolsa, ...foto.cripto].find((c) => c.activo === elegido.activo) ?? null
      : null;
  const nombreElegido = elegido ? nombreLlano(elegido.activo) : "";

  return (
    <Seccion titulo="Cotizaciones" id="cotizaciones">
      <Nota>
        El precio de este momento de una lista de valores de bolsa y de todas las criptomonedas que en Binance se compran con
        dólares digitales (USDT). Se piden al pulsar y cada foto lleva su hora. Son para mirar: las cifras de las estrategias y de
        tu plan se calculan siempre con precios de cierre, no con estos.
      </Nota>
      <div className="flex flex-wrap items-center gap-3">
        <Boton variante="primario" onClick={() => void traer.ejecutar()} disabled={traer.enCurso}>
          {traer.enCurso ? "Pidiendo los precios…" : "Ver los precios de ahora"}
        </Boton>
        {traer.enCurso ? <Cargando texto="Pidiendo los precios a Binance y a Yahoo Finance…" /> : null}
      </div>
      {traer.error ? <ErrorApiVista error={traer.error} /> : null}

      {!foto ? (
        <Aviso tipo="info">Pulsa el botón para traer la primera foto del mercado.</Aviso>
      ) : (
        <div className="min-w-0 space-y-3">
          <p className="text-sm text-tinta">
            <strong>Foto del {momento(foto.at)}</strong>.{" "}
            <span className="text-tinta-suave">Vuelve a pulsar para refrescarla.</span>
          </p>
          {foto.errores.map((e) => (
            <Aviso key={e} tipo="aviso">
              {e}
            </Aviso>
          ))}
          <CampoTexto
            etiqueta="Buscar"
            placeholder="p. ej. bitcoin, Apple, BTC"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            className="max-w-xs"
          />
          <div className="grid gap-4 lg:grid-cols-2">
            <TablaViva
              titulo="Bolsa"
              filas={filtrar(foto.bolsa)}
              total={foto.bolsa.length}
              elegido={elegido?.activo ?? null}
              onElegir={(a) => elegir(a, "equity")}
            />
            <TablaViva
              titulo="Cripto"
              filas={filtrar(foto.cripto)}
              total={foto.cripto.length}
              elegido={elegido?.activo ?? null}
              onElegir={(a) => elegir(a, "crypto")}
            />
          </div>

          {!elegido ? (
            <Nota>Pincha una fila para guardar en el panel su historia de precios y ver su gráfica.</Nota>
          ) : cotizacionElegida?.descargado && !descargar.resultado ? (
            <Aviso tipo="info">
              {nombreElegido} ya está en el panel, con su historia de precios.{" "}
              <button
                type="button"
                className="font-semibold underline underline-offset-2"
                onClick={() => onVerGrafica(elegido.activo)}
              >
                Ver su gráfica
              </button>
            </Aviso>
          ) : (
            <div className="space-y-2 rounded-tarjeta border border-linea bg-superficie p-4">
              <p className="text-[0.9375rem] text-tinta">
                <strong className="font-semibold">{nombreElegido}</strong>
                {nombreElegido !== elegido.activo ? <span className="text-tinta-suave"> ({elegido.activo})</span> : null}: el panel
                todavía no tiene su historia de precios.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Boton
                  onClick={() => void descargar.ejecutar(elegido.activo, elegido.mercado)}
                  disabled={descargar.enCurso}
                >
                  Descargar su historia de precios
                </Boton>
                {descargar.enCurso ? <Cargando texto={`Descargando los precios de ${nombreElegido} desde 2015…`} /> : null}
              </div>
              {descargar.error ? <ErrorApiVista error={descargar.error} prefijo={`No se pudo descargar ${nombreElegido}:`} /> : null}
              {descargar.resultado ? (
                descargar.resultado.ok ? (
                  <Aviso tipo="hecho" vivo>
                    {nombreElegido} ya está en el panel: aparece arriba, en la lista.{" "}
                    <span className="opacity-90">{descargar.resultado.detalle}</span>{" "}
                    <button
                      type="button"
                      className="font-semibold underline underline-offset-2"
                      onClick={() => onVerGrafica(descargar.resultado?.symbol ?? elegido.activo)}
                    >
                      Ver su gráfica
                    </button>
                  </Aviso>
                ) : (
                  <Aviso tipo="critico" vivo>
                    No se pudo descargar {nombreElegido}: <span className="whitespace-pre-wrap">{descargar.resultado.detalle}</span>
                  </Aviso>
                )
              ) : null}
            </div>
          )}
        </div>
      )}
    </Seccion>
  );
}
