"use client";

import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import { Aviso, Cargando, CampoTexto, Deslizador, ErrorApiVista, Nota, Seccion, TextoApi, TextoPlano } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useConsulta, useRetardado } from "@/lib/consulta";

/**
 * Se mira; no persigue. Esta pestana no notifica, y no hay alertas de subidas: una que dijera
 * "GLD subio un 20%" no informa de nada que necesites, existe para que abras la aplicacion.
 */
export function Alertas() {
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
            <div className="rounded-xl border border-linea bg-superficie px-4 py-3">
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

