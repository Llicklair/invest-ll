"use client";

import { Hand, PauseCircle, ShieldCheck, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import {
  Aviso,
  BloqueComandos,
  Boton,
  CampoTexto,
  Cargando,
  Deslizador,
  ErrorApiVista,
  Nota,
  Seccion,
  Selector,
  Tarjeta,
  TextoApi,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion, useConsulta } from "@/lib/consulta";
import { fraccionComoPorcentaje, formatoCantidad } from "@/lib/decimal";
import { euros, fechaCorta, momento } from "@/lib/formato";
import { nombreLlano } from "@/lib/nombres";

const REGLAS: Record<string, { corto: string; frase: (pct: number) => string }> = {
  "loss-from-entry": {
    corto: "Si pierdo desde que compré",
    frase: (pct) => `Avísame con una propuesta de venta si pierdo más de un ${pct} % desde que compré`,
  },
  "drop-from-peak": {
    corto: "Si cae desde su máximo",
    frase: (pct) => `Avísame con una propuesta de venta si cae más de un ${pct} % desde su máximo`,
  },
};

export interface ActivoConNombre {
  simbolo: string;
  nombre: string;
}

function Comprobar({ armados, nombreDe }: { armados: number; nombreDe: (simbolo: string) => string }) {
  const comprobar = useAccion(() => pedir(api.GET("/api/triggers/comprobar")));
  const r = comprobar.resultado;
  return (
    <div className="space-y-4">
      <Boton variante="secundario" tamano="compacto" onClick={() => void comprobar.ejecutar()} disabled={comprobar.enCurso || armados === 0}>
        {comprobar.enCurso ? "Mirando…" : "Mirar ahora si salta alguno"}
      </Boton>
      {comprobar.error ? <ErrorApiVista error={comprobar.error} /> : null}
      {r ? (
        <div className="space-y-3" role="status">
          {r.disparados.length === 0 ? (
            <p className="text-[0.9375rem] text-tinta">Ninguno ha saltado con los datos de ahora. No se ha enviado nada.</p>
          ) : null}
          {r.disparados.map((d) => (
            <Tarjeta key={d.trigger_id} className="space-y-3 border-pruebas/50 p-5">
              <p className="text-[0.9375rem] text-tinta">
                <strong className="font-semibold">{nombreDe(d.symbol)}</strong> ha caído un{" "}
                <strong className="cifras">{fraccionComoPorcentaje(d.medido.replace("-", ""), 1) ?? d.medido}</strong> (tu freno
                estaba en {fraccionComoPorcentaje(d.umbral, 0) ?? d.umbral}). Te proponemos vender{" "}
                <strong className="cifras">{formatoCantidad(d.cantidad_propuesta)}</strong> al precio del cierre del{" "}
                {fechaCorta(d.precio_fecha)} ({euros(d.precio)}).
              </p>
              <p className="text-sm font-semibold text-tinta-suave">Es una propuesta: no se ha vendido nada. Decidirlo es cosa tuya.</p>
              <BloqueComandos lineas={[d.comando]} />
            </Tarjeta>
          ))}
          {r.sin_evaluar.length ? (
            <Aviso tipo="aviso" titulo="No se pudieron mirar (no poder mirar no es «todo en orden»)">
              <ul className="mt-1 list-disc pl-5">
                {r.sin_evaluar.map((s) => (
                  <li key={s}>
                    <TextoApi texto={s} />
                  </li>
                ))}
              </ul>
            </Aviso>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Proteccion (antes, Vigilar): los frenos, que PROPONEN una venta cuando algo cae mas de lo que
 * aceptas, y la pausa de compras. Nada de esto vende ni compra solo.
 */
export function Proteccion({ activos }: { activos: readonly ActivoConNombre[] }) {
  const simbolos = activos.map((a) => a.simbolo);
  const nombreDe = (s: string) => activos.find((a) => a.simbolo === s)?.nombre ?? nombreLlano(s);
  const { refrescarDatos, versionDatos } = useEstado();
  const [version, setVersion] = useState(0);
  const recargar = () => {
    setVersion((v) => v + 1);
    refrescarDatos();
  };
  const consulta = useConsulta(`triggers:${version}:${versionDatos}`, () => pedir(api.GET("/api/triggers")));
  const t = consulta.datos;

  const [simbolo, setSimbolo] = useState("");
  const [regla, setRegla] = useState("loss-from-entry");
  const [umbral, setUmbral] = useState(15);
  const [motivo, setMotivo] = useState("");

  const quitar = useAccion(async (id: string) => {
    await pedirSinCuerpo(api.DELETE("/api/triggers/{trigger_id}", { params: { path: { trigger_id: id } } }));
    recargar();
    return id;
  });
  const poner = useAccion(async () => {
    const r = await pedir(
      api.POST("/api/triggers", { body: { simbolo: (simbolo || simbolos[0] || "").trim().toUpperCase(), regla, umbral_pct: umbral } }),
    );
    recargar();
    return r;
  });
  const pausar = useAccion(async () => {
    await pedirSinCuerpo(api.POST("/api/pausa", { body: { motivo: motivo.trim() } }));
    setMotivo("");
    recargar();
    return true;
  });
  const reanudar = useAccion(async () => {
    await pedirSinCuerpo(api.DELETE("/api/pausa"));
    recargar();
    return true;
  });

  const enviarFreno = (e: FormEvent) => {
    e.preventDefault();
    void poner.ejecutar();
  };
  const enviarPausa = (e: FormEvent) => {
    e.preventDefault();
    void pausar.ejecutar();
  };
  const reglas = t?.reglas.length ? t.reglas : Object.keys(REGLAS);

  return (
    <Seccion
      titulo="Protección"
      id="proteccion"
      bajada="Frenos que te proponen vender si algo cae más de lo que aceptas, y una pausa para dejar de comprar. Ninguno vende ni compra solo."
    >
      {consulta.error ? <ErrorApiVista error={consulta.error} reintentar={consulta.recargar} /> : null}
      {!t && consulta.cargando ? <Cargando /> : null}
      {t ? (
        <div className="grid items-start gap-4 lg:grid-cols-2">
          <Tarjeta className="space-y-5 p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <ShieldCheck aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
              <h3 className="text-lg font-semibold text-tinta">Frenos</h3>
            </div>
            {t.triggers.length ? (
              <ul className="divide-y divide-linea">
                {t.triggers.map((x) => {
                  const pct = Math.round(Number(x.umbral) * 100);
                  return (
                    <li key={x.trigger_id} className="flex items-start justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-tinta">{nombreDe(x.symbol)}</p>
                        <p className="text-[0.9375rem] text-tinta">{REGLAS[x.regla]?.frase(pct) ?? x.descripcion}.</p>
                        <p className="mt-0.5 text-sm text-tinta-suave">Puesto el {momento(x.armado)}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void quitar.ejecutar(x.trigger_id)}
                        disabled={quitar.enCurso}
                        aria-label={`Quitar el freno de ${nombreDe(x.symbol)}`}
                        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-tinta-suave hover:bg-superficie-2 hover:text-real-tinta"
                      >
                        <Trash2 aria-hidden="true" className="h-4 w-4" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-[0.9375rem] text-tinta-suave">
                {simbolos.length
                  ? "No tienes ningún freno puesto."
                  : "Cuando tengas algo comprado, aquí podrás ponerle un freno: un aviso con una propuesta de venta si cae más de lo que aceptas."}
              </p>
            )}
            {quitar.error ? <ErrorApiVista error={quitar.error} prefijo="No se quitó:" /> : null}
            {t.triggers.length ? <Comprobar armados={t.triggers.length} nombreDe={nombreDe} /> : null}

            {simbolos.length || t.triggers.length ? (
            <form onSubmit={enviarFreno} className="space-y-4 border-t border-linea pt-5">
              <p className="font-semibold text-tinta">Poner un freno</p>
              <div className="grid gap-4">
                {simbolos.length ? (
                  <Selector etiqueta="A qué" value={simbolo || simbolos[0]} onChange={(e) => setSimbolo(e.target.value)}>
                    {simbolos.map((s) => (
                      <option key={s} value={s}>
                        {nombreDe(s)}
                      </option>
                    ))}
                  </Selector>
                ) : (
                  <CampoTexto etiqueta="A qué" ayuda="Como aparece en tu bróker o en Binance (p. ej., GLD para el oro)." value={simbolo} onChange={(e) => setSimbolo(e.target.value)} required />
                )}
                <Selector etiqueta="Cuándo" value={regla} onChange={(e) => setRegla(e.target.value)}>
                  {reglas.map((r) => (
                    <option key={r} value={r}>
                      {REGLAS[r]?.corto ?? r}
                    </option>
                  ))}
                </Selector>
              </div>
              <Deslizador etiqueta="Cuánto" valor={umbral} min={5} max={60} paso={5} formato={(v) => `${v} %`} onCambio={setUmbral} />
              <p className="rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">{REGLAS[regla]?.frase(umbral) ?? regla}.</p>
              <Boton type="submit" variante="secundario" disabled={poner.enCurso}>
                Poner el freno
              </Boton>
              {poner.error ? <ErrorApiVista error={poner.error} prefijo="No se puso:" /> : null}
              {poner.resultado ? (
                // La frase de la pantalla, no la `descripcion` de la terminal ("SPY: proponer la venta
                // si pierde mas del 15% desde tu entrada (coste medio con comisiones)").
                <Aviso tipo="hecho" vivo titulo={`Freno puesto en ${nombreDe(poner.resultado.symbol)}`}>
                  {REGLAS[poner.resultado.regla]?.frase(Math.round(Number(poner.resultado.umbral) * 100)) ?? (
                    <TextoApi texto={poner.resultado.descripcion} />
                  )}
                  .
                </Aviso>
              ) : null}
            </form>
            ) : null}
          </Tarjeta>

          <Tarjeta className="space-y-5 p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <PauseCircle aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
              <h3 className="text-lg font-semibold text-tinta">Pausa de compras</h3>
            </div>
            {t.pausa ? (
              <>
                <Aviso tipo="aviso" titulo="Las compras están en pausa">
                  <TextoApi texto={t.pausa} />. No se proponen compras nuevas; lo que tienes no se toca.
                </Aviso>
                <Boton variante="secundario" onClick={() => void reanudar.ejecutar()} disabled={reanudar.enCurso}>
                  Quitar la pausa
                </Boton>
                {reanudar.error ? <ErrorApiVista error={reanudar.error} prefijo="No se quitó:" /> : null}
              </>
            ) : (
              <form onSubmit={enviarPausa} className="space-y-4">
                <p className="text-[0.9375rem] text-tinta-suave">
                  Para cuando quieras pararte a pensar: mientras dure, no te propondremos comprar nada. Lo que ya tienes no se
                  toca.
                </p>
                <CampoTexto
                  etiqueta="Por qué paras"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  required
                  ayuda="Es lo que leerás cuando quieras quitarla."
                />
                <Boton type="submit" variante="secundario" disabled={pausar.enCurso || !motivo.trim()}>
                  <Hand aria-hidden="true" className="h-4 w-4" />
                  Pausar las compras
                </Boton>
                {pausar.error ? <ErrorApiVista error={pausar.error} prefijo="No se pausó:" /> : null}
              </form>
            )}
            <Nota>Una pausa es para ti: el panel no la pone solo ni te avisa para que la quites.</Nota>
          </Tarjeta>
        </div>
      ) : null}
    </Seccion>
  );
}
