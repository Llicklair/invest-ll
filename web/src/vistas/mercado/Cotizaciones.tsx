"use client";

import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { Cotizacion, Cotizaciones as FotoCotizaciones } from "@/api/tipos";
import { MarcoTabla, Td, TdVariacion, Th } from "@/componentes/tabla";
import { Aviso, Boton, Cargando, CampoTexto, ErrorApiVista, Nota, Seccion, clases } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion } from "@/lib/consulta";
import { horaUtc, numero, porcentaje, precio } from "@/lib/formato";

type Mercado = "equity" | "crypto";

// La ultima foto sobrevive a cambiar de pestana (como el session_state de Streamlit), pero nunca
// se refresca sola: un panel que se actualiza solo es una notificacion con otro nombre.
let fotoGuardada: FotoCotizaciones | null = null;

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
    <div className="space-y-1.5">
      <h3 className="text-sm font-semibold text-tinta">
        {titulo} <span className="font-normal text-tinta-2">— {filas.length} de {total} (ordenados por volumen)</span>
      </h3>
      {filas.length ? (
        <MarcoTabla etiqueta={`Cotizaciones de ${titulo.toLowerCase()}`} altoMaximo={360}>
          <thead>
            <tr>
              <Th>activo</Th>
              <Th numerica>precio</Th>
              <Th numerica>24h %</Th>
              <Th numerica>volumen 24h (M)</Th>
              <Th>histórico</Th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => {
              const activo = f.activo === elegido;
              return (
                <tr
                  key={f.activo}
                  onClick={() => onElegir(f.activo)}
                  className={clases("cursor-pointer hover:bg-superficie-2", activo && "bg-superficie-3")}
                >
                  <Td>
                    <button
                      type="button"
                      aria-pressed={activo}
                      onClick={(e) => {
                        e.stopPropagation();
                        onElegir(f.activo);
                      }}
                      className="font-medium text-tinta underline-offset-2 hover:underline"
                    >
                      {f.activo}
                    </button>
                  </Td>
                  <Td numerica>{precio(f.precio)}</Td>
                  <TdVariacion valor={f.var_24h} texto={porcentaje(f.var_24h, 2)} />
                  <Td numerica>{numero(f.volumen_24h_m, 1)}</Td>
                  <Td className="text-tinta-2">{f.descargado ? "descargado" : "—"}</Td>
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

  const f = filtro.trim().toUpperCase();
  const filtrar = (xs: Cotizacion[]) => (f ? xs.filter((x) => x.activo.toUpperCase().includes(f)) : xs);

  const elegir = (activo: string, mercado: Mercado) => {
    setElegido({ activo, mercado });
    descargar.limpiar();
  };

  const cotizacionElegida =
    elegido && foto
      ? [...foto.bolsa, ...foto.cripto].find((c) => c.activo === elegido.activo) ?? null
      : null;

  return (
    <Seccion titulo="Cotizaciones" id="cotizaciones">
      <Nota>
        Bolsa: los valores del catálogo (ampliable en fetch/catalog.py) · Cripto: TODOS los pares USDT al contado de
        Binance. Se piden al pulsar; cada foto lleva su hora. Nada de esto entra en un backtest: el histórico
        reproducible sigue viniendo de invest-ll-fetch, con su procedencia.
      </Nota>
      <div className="flex flex-wrap items-center gap-3">
        <Boton variante="primario" onClick={() => void traer.ejecutar()} disabled={traer.enCurso}>
          {traer.enCurso ? "Pidiendo cotizaciones…" : "Traer cotizaciones (bolsa + cripto)"}
        </Boton>
        {traer.enCurso ? <Cargando texto="Pidiendo a Binance todos los pares USDT y los valores de bolsa a yfinance…" /> : null}
      </div>
      {traer.error ? <ErrorApiVista error={traer.error} /> : null}

      {!foto ? (
        <Aviso tipo="info">Pulsa el botón para traer la primera foto del mercado.</Aviso>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-tinta">
            <strong>Foto de las {horaUtc(foto.at)} UTC</strong> del {foto.at.slice(0, 10)}.{" "}
            <span className="text-tinta-2">Vuelve a pulsar para refrescarla.</span>
          </p>
          {foto.errores.map((e) => (
            <Aviso key={e} tipo="critico">
              {e}
            </Aviso>
          ))}
          <CampoTexto
            etiqueta="Filtrar por símbolo"
            placeholder="p. ej. BTC, AAPL, .MC"
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
            <Nota>Pincha una fila para poder descargar su histórico completo.</Nota>
          ) : cotizacionElegida?.descargado && !descargar.resultado ? (
            <Aviso tipo="info">
              {elegido.activo} ya tiene histórico descargado: lo tienes abajo, con su gráfica.{" "}
              <button
                type="button"
                className="font-semibold underline underline-offset-2"
                onClick={() => onVerGrafica(elegido.activo)}
              >
                Ver su gráfica
              </button>
            </Aviso>
          ) : (
            <div className="space-y-2 rounded-md border border-borde bg-superficie p-3">
              <p className="text-sm">
                Seleccionado: <strong>{elegido.activo}</strong> (sin histórico descargado)
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Boton
                  onClick={() => void descargar.ejecutar(elegido.activo, elegido.mercado)}
                  disabled={descargar.enCurso}
                >
                  Descargar histórico completo de {elegido.activo}
                </Boton>
                {descargar.enCurso ? <Cargando texto={`Descargando ${elegido.activo} desde 2015…`} /> : null}
              </div>
              {descargar.error ? <ErrorApiVista error={descargar.error} prefijo={`No se pudo descargar ${elegido.activo}:`} /> : null}
              {descargar.resultado ? (
                descargar.resultado.ok ? (
                  <Aviso tipo="hecho" vivo>
                    {descargar.resultado.symbol} descargado: ya aparece en las mesas de rendimiento.{" "}
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
                    No se pudo descargar {descargar.resultado.symbol}:{" "}
                    <span className="whitespace-pre-wrap">{descargar.resultado.detalle}</span>
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
