"use client";

import { useState, type FormEvent } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  BloqueComandos,
  Boton,
  CampoTexto,
  Cargando,
  Codigo,
  Deslizador,
  ErrorApiVista,
  Nota,
  Seccion,
  Selector,
  Separador,
  TextoApi,
  TextoPlano,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion, useConsulta, useRetardado } from "@/lib/consulta";
import { fraccionComoPorcentaje, formatoCantidad, formatoImporte } from "@/lib/decimal";
import { fecha, momento } from "@/lib/formato";

const NOMBRES_REGLA: Record<string, string> = {
  "loss-from-entry": "pérdida desde tu entrada (loss-from-entry)",
  "drop-from-peak": "caída desde el máximo (drop-from-peak)",
};

/**
 * Se mira; no persigue. Esta pestana no notifica, y no hay alertas de subidas: una que dijera
 * "GLD subio un 20%" no informa de nada que necesites, existe para que abras la aplicacion.
 */
function Alertas() {
  const { versionDatos } = useEstado();
  const [dias, setDias] = useState("7");
  const [caida, setCaida] = useState(15);
  const diasValidos = Math.min(365, Math.max(1, Math.round(Number(dias)) || 7));
  const clave = useRetardado(`${diasValidos}:${caida}`, 400);
  const consulta = useConsulta(`alertas:${clave}:${versionDatos}`, () => {
    const [d = "7", c = "15"] = clave.split(":");
    return pedir(api.GET("/api/vigilar/alertas", { params: { query: { dias: Number(d), caida_pct: Number(c) } } }));
  });
  const a = consulta.datos;

  return (
    <Seccion titulo="Alertas" id="alertas">
      <Nota>Solo saltan por riesgo, nunca porque algo haya subido. Informan de un estado; ninguna dice qué hacer.</Nota>
      <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
        <CampoTexto
          etiqueta="Avisar si un histórico lleva sin actualizarse más de (días)"
          type="number"
          min={1}
          max={365}
          value={dias}
          onChange={(e) => setDias(e.target.value)}
        />
        <Deslizador
          etiqueta="Avisar si un activo cae desde su máximo más de"
          valor={caida}
          min={5}
          max={60}
          paso={5}
          formato={(v) => `${v}%`}
          onCambio={setCaida}
        />
      </div>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!a && consulta.cargando ? <Cargando texto="Mirando los históricos…" /> : null}
      {a ? (
        <div className={consulta.cargando ? "space-y-2 opacity-60" : "space-y-2"}>
          {a.alertas.length === 0 ? (
            // Ni "todo correcto" ni iconos de exito: lo que se ha mirado y lo que no, tal cual.
            <div className="rounded-md border border-borde bg-superficie px-3 py-2.5">
              <p className="text-sm whitespace-pre-wrap text-tinta">
                {a.nada_que_contar ?? "La API no ha devuelto ninguna alerta ni ha dicho qué ha mirado."}
              </p>
            </div>
          ) : (
            a.alertas.map((al, i) => (
              <Aviso key={`${al.symbol ?? "general"}-${i}`} tipo={al.nivel === "revisar" ? "aviso" : "info"}>
                {al.symbol ? <strong>{al.symbol} — </strong> : null}
                <TextoApi texto={al.mensaje} />
                <span className="ml-2 text-xs opacity-80">({al.nivel})</span>
              </Aviso>
            ))
          )}
        </div>
      ) : null}
      <Nota>
        Para las alertas que dependen de lo que tengas de verdad (pérdida desde tu entrada, desviación del plan) hace falta
        declarar posiciones:
      </Nota>
      <TextoPlano>uv run invest-ll-alerts data/market/yfinance/GLD/DAY_1.csv --holding GLD:10:180</TextoPlano>
    </Seccion>
  );
}

function ComprobarTriggers({ armados }: { armados: number }) {
  const comprobar = useAccion(() => pedir(api.GET("/api/triggers/comprobar")));
  const r = comprobar.resultado;
  return (
    <div className="space-y-3">
      <Boton onClick={() => void comprobar.ejecutar()} disabled={comprobar.enCurso || armados === 0}>
        {comprobar.enCurso ? "Comprobando…" : "Comprobar los triggers con la cartera real"}
      </Boton>
      {comprobar.error ? <ErrorApiVista error={comprobar.error} /> : null}
      {r ? (
        <div className="space-y-3" role="status">
          <Nota>
            {r.armados} trigger(s) armado(s) · {r.disparados.length} con la venta propuesta · {r.sin_evaluar.length} sin
            poder evaluar.
          </Nota>
          {r.disparados.map((d) => (
            <div key={d.trigger_id} className="space-y-2 rounded-md border border-borde bg-superficie p-3">
              <p className="text-sm">
                <Codigo>{d.trigger_id}</Codigo> <strong>{d.symbol}</strong>: medido{" "}
                <strong className="cifras">{fraccionComoPorcentaje(d.medido, 1) ?? d.medido}</strong> frente a un umbral
                de {fraccionComoPorcentaje(d.umbral, 1) ?? d.umbral}. Propone vender{" "}
                <strong className="cifras">{formatoCantidad(d.cantidad_propuesta)}</strong> al cierre de{" "}
                {formatoImporte(d.precio)} del {fecha(d.precio_fecha)}.
              </p>
              <BloqueComandos lineas={[d.comando]} />
              <p className="text-xs font-semibold text-tinta-2">
                Es texto para leer: nada se ha enviado. Ejecutarlo y confirmarlo sigue siendo cosa tuya.
              </p>
            </div>
          ))}
          {r.sin_evaluar.length ? (
            <Aviso tipo="aviso">
              <p className="font-semibold">No se pudieron evaluar (no poder mirar NO es «todo en orden»):</p>
              <ul className="mt-1 list-disc pl-5">
                {r.sin_evaluar.map((s) => (
                  <li key={s}>
                    <TextoApi texto={s} />
                  </li>
                ))}
              </ul>
            </Aviso>
          ) : null}
          {r.disparados.length === 0 ? (
            <Nota>Ningún trigger ha cruzado su umbral con los datos de ahora. Nada se ha enviado.</Nota>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Triggers() {
  const { refrescarDatos, versionDatos } = useEstado();
  const [version, setVersion] = useState(0);
  const recargar = () => {
    setVersion((v) => v + 1);
    refrescarDatos();
  };
  const consulta = useConsulta(`triggers:${version}:${versionDatos}`, () => pedir(api.GET("/api/triggers")));
  const t = consulta.datos;

  const [simbolo, setSimbolo] = useState("");
  const [regla, setRegla] = useState("");
  const [umbral, setUmbral] = useState(15);
  const [motivo, setMotivo] = useState("");

  const desarmar = useAccion(async (id: string) => {
    await pedirSinCuerpo(api.DELETE("/api/triggers/{trigger_id}", { params: { path: { trigger_id: id } } }));
    recargar();
    return id;
  });
  const armar = useAccion(async () => {
    const r = await pedir(
      api.POST("/api/triggers", {
        body: { simbolo: simbolo.trim().toUpperCase(), regla: regla || t?.reglas[0] || "", umbral_pct: umbral },
      }),
    );
    setSimbolo("");
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

  const enviarArmar = (e: FormEvent) => {
    e.preventDefault();
    void armar.ejecutar();
  };
  const enviarPausa = (e: FormEvent) => {
    e.preventDefault();
    void pausar.ejecutar();
  };

  return (
    <Seccion titulo="Triggers de retirada" id="triggers">
      <Nota>
        Cuando se cruzan, PROPONEN la venta exacta (con <Codigo>invest-ll-triggers check</Codigo> o el botón de abajo);
        ejecutarla y confirmarla sigue siendo cosa tuya.
      </Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!t && consulta.cargando ? <Cargando /> : null}
      {t ? (
        <div className={consulta.cargando ? "space-y-4 opacity-60" : "space-y-4"}>
          {t.pausa ? (
            <Aviso tipo="aviso">
              <strong>Pausa activa (no se proponen entradas nuevas):</strong> <TextoApi texto={t.pausa} />
            </Aviso>
          ) : null}

          {t.triggers.length ? (
            <MarcoTabla etiqueta="Triggers armados">
              <thead>
                <tr>
                  <Th>id</Th>
                  <Th>qué hace</Th>
                  <Th>armado</Th>
                  <Th>
                    <span className="sr-only">acción</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {t.triggers.map((x) => (
                  <tr key={x.trigger_id}>
                    <Td className="font-mono text-xs">{x.trigger_id}</Td>
                    <Td className="whitespace-normal">{x.descripcion}</Td>
                    <Td className="text-tinta-2">{momento(x.armado)}</Td>
                    <Td numerica>
                      <Boton
                        className="min-h-7 px-2 py-0.5 text-xs"
                        onClick={() => void desarmar.ejecutar(x.trigger_id)}
                        disabled={desarmar.enCurso}
                        aria-label={`Desarmar ${x.trigger_id} (${x.symbol})`}
                      >
                        Desarmar
                      </Boton>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </MarcoTabla>
          ) : (
            <Nota>Ninguno armado.</Nota>
          )}
          {desarmar.error ? <ErrorApiVista error={desarmar.error} prefijo="No se desarmó:" /> : null}

          <ComprobarTriggers armados={t.triggers.length} />

          <form onSubmit={enviarArmar} className="space-y-3 rounded-md border border-borde bg-superficie p-3">
            <h3 className="text-sm font-semibold">Armar un trigger</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <CampoTexto etiqueta="Activo" placeholder="GLD" value={simbolo} onChange={(e) => setSimbolo(e.target.value)} required />
              <Selector etiqueta="Regla" value={regla || t.reglas[0] || ""} onChange={(e) => setRegla(e.target.value)}>
                {t.reglas.map((r) => (
                  <option key={r} value={r}>
                    {NOMBRES_REGLA[r] ?? r}
                  </option>
                ))}
              </Selector>
              <Deslizador etiqueta="Umbral" valor={umbral} min={5} max={60} paso={5} formato={(v) => `${v}%`} onCambio={setUmbral} />
            </div>
            <Boton type="submit" disabled={armar.enCurso}>
              Armar trigger
            </Boton>
            {armar.error ? <ErrorApiVista error={armar.error} prefijo="No se armó:" /> : null}
            {armar.resultado ? (
              <Aviso tipo="info" vivo>
                Armado <Codigo>{armar.resultado.trigger_id}</Codigo>: {armar.resultado.descripcion}
              </Aviso>
            ) : null}
          </form>

          <div className="grid gap-4 md:grid-cols-2">
            <form onSubmit={enviarPausa} className="space-y-3 rounded-md border border-borde bg-superficie p-3">
              <h3 className="text-sm font-semibold">Pausar entradas nuevas</h3>
              <CampoTexto
                etiqueta="Motivo de la pausa (obligatorio)"
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                required
                ayuda="Es lo que leerás cuando quieras retirarla. Las posiciones abiertas no se tocan."
              />
              <Boton type="submit" disabled={pausar.enCurso || !motivo.trim()}>
                Pausar entradas nuevas
              </Boton>
              {pausar.error ? <ErrorApiVista error={pausar.error} prefijo="No se pausó:" /> : null}
            </form>
            <div className="space-y-3 rounded-md border border-borde bg-superficie p-3">
              <h3 className="text-sm font-semibold">Retirar la pausa</h3>
              <Nota>{t.pausa ? `Ahora hay una: ${t.pausa}` : "Ahora no hay ninguna pausa activa."}</Nota>
              <Boton onClick={() => void reanudar.ejecutar()} disabled={reanudar.enCurso}>
                Retirar la pausa
              </Boton>
              {reanudar.error ? <ErrorApiVista error={reanudar.error} prefijo="No se retiró:" /> : null}
            </div>
          </div>
        </div>
      ) : null}
    </Seccion>
  );
}

export function Vigilar() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-tinta">Vigilar</h1>
      <Alertas />
      <Separador />
      <Triggers />
    </div>
  );
}
