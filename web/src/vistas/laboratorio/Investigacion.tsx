"use client";

import { useState } from "react";

import { api, MODO_EJEMPLO, pedir, urlApi } from "@/api/cliente";
import type { Investigacion as DatosInvestigacion } from "@/api/tipos";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  Cargando,
  CampoTexto,
  Codigo,
  ErrorApiVista,
  FilaMetricas,
  Metrica,
  Nota,
  Seccion,
  TextoApi,
} from "@/componentes/ui";
import { useConsulta, useRetardado } from "@/lib/consulta";
import { fecha, fraccion, momento, numero } from "@/lib/formato";

/** Peso de cada moneda: barra fina de una sola serie (magnitud, sin leyenda). */
function BarraPeso({ peso }: { peso: number }) {
  const ancho = Math.max(0, Math.min(1, peso)) * 100;
  return (
    <div className="h-2.5 w-28 rounded-sm bg-superficie-2" aria-hidden="true">
      <div className="h-2.5 rounded-r-[4px] bg-[var(--serie-1)]" style={{ width: `${ancho}%` }} />
    </div>
  );
}

function Objetivo({ datos, capital, setCapital }: { datos: DatosInvestigacion; capital: string; setCapital: (v: string) => void }) {
  return (
    <div className="space-y-3">
      <CampoTexto
        etiqueta="Tamaño de la cuenta (USDT)"
        type="number"
        min={0}
        step={100}
        value={capital}
        onChange={(e) => setCapital(e.target.value)}
        className="max-w-xs"
      />
      <p className="text-sm">
        <strong>Objetivo tras el cierre del {fecha(datos.ultimo_dato)}.</strong> Esto no es una previsión de que vayan a
        subir.
      </p>
      <MarcoTabla etiqueta="Pesos objetivo de la cartera prerregistrada">
        <thead>
          <tr>
            <Th>Moneda</Th>
            <Th numerica>Peso</Th>
            <Th>
              <span className="sr-only">Peso en barra</span>
            </Th>
            <Th numerica>USDT</Th>
          </tr>
        </thead>
        <tbody>
          {datos.objetivo.map((p) => (
            <tr key={p.moneda}>
              <Td className={p.moneda === "liquidez" ? "text-tinta-suave italic" : "font-medium"}>{p.moneda}</Td>
              <Td numerica>{fraccion(p.peso, 1, false)}</Td>
              <Td>
                <BarraPeso peso={p.peso} />
              </Td>
              <Td numerica>{numero(p.usdt, 2)}</Td>
            </tr>
          ))}
        </tbody>
      </MarcoTabla>
      <Nota>El panel no envía nada. Ejecutar estas cantidades sigue siendo cosa tuya.</Nota>
    </div>
  );
}

function Estudio({ datos }: { datos: DatosInvestigacion }) {
  // En el modo de ejemplo no hay API a la que apuntar el iframe: se pide el HTML al simulador.
  const ejemplo = useConsulta(MODO_EJEMPLO && datos.estudio ? "estudio-ejemplo" : null, () =>
    pedir(api.GET("/api/investigacion/estudio", { parseAs: "text" })),
  );
  if (!datos.estudio) {
    return (
      <Aviso tipo="info">
        Ningún estudio todavía. <Codigo>uv run invest-ll-quant study</Codigo> genera el informe completo.
      </Aviso>
    );
  }
  return (
    <div className="space-y-2">
      <Nota>
        <Codigo>{datos.estudio.ruta}</Codigo> · generado {momento(datos.estudio.generado)}
      </Nota>
      {ejemplo.error ? <ErrorApiVista error={ejemplo.error} /> : null}
      <iframe
        title="Último estudio"
        className="h-[1400px] w-full rounded-md border border-linea bg-white"
        sandbox="allow-scripts"
        {...(MODO_EJEMPLO ? { srcDoc: ejemplo.datos ?? "" } : { src: urlApi("/api/investigacion/estudio") })}
      />
    </div>
  );
}

export function Investigacion() {
  const [capital, setCapital] = useState("1000");
  const capitalValido = Math.max(0, Number(capital) || 0);
  const clave = useRetardado(String(capitalValido), 400);
  const consulta = useConsulta(`investigacion:${clave}`, () =>
    pedir(api.GET("/api/investigacion", { params: { query: { capital: Number(clave) } } })),
  );
  const d = consulta.datos;

  return (
    <div className="space-y-6">
      <Seccion titulo="Cartera prerregistrada" id="prerregistrada">
        <Nota>
          Momentum diversificado sobre las 20 monedas más líquidas de cada día, con las que luego murieron incluidas. Peso
          por riesgo, máximo 35% por moneda, objetivo de volatilidad del 60%, decisión semanal en 7 tramos. Fijada antes de
          ver resultados. Ver docs/quant-research.md.
        </Nota>
        {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
        {!d && consulta.cargando ? <Cargando texto="Cargando el universo de Binance…" /> : null}
        {d && !d.disponible ? (
          <Aviso tipo="info">
            <TextoApi texto={d.motivo ?? "La investigación no está disponible."} />
          </Aviso>
        ) : null}
        {d && d.disponible ? (
          <div className={consulta.cargando ? "space-y-3 opacity-60" : "space-y-3"}>
            {d.dias_desfase !== null && d.dias_desfase > 2 ? (
              <Aviso tipo="aviso">
                Los datos acaban el {fecha(d.ultimo_dato)} (hace {d.dias_desfase} días). Actualiza con{" "}
                <Codigo>invest-ll-quant download</Codigo>.
              </Aviso>
            ) : null}
            <Objetivo datos={d} capital={capital} setCapital={setCapital} />
          </div>
        ) : null}
      </Seccion>

      {d && d.disponible ? (
        <Seccion titulo="Prueba hacia delante" id="adelante">
          <div className="space-y-4">
            {d.prueba_adelante.map((p) => (
              <div key={p.clave} className="space-y-2">
                <h3 className="text-[0.9375rem] font-semibold">{p.etiqueta}</h3>
                {p.nota ? (
                  <Aviso tipo="info">
                    <TextoApi texto={p.nota} />
                  </Aviso>
                ) : (
                  <>
                    <FilaMetricas columnas={3}>
                      <Metrica etiqueta="Cartera (desde 10.000)" valor={numero(p.valor_final, 0)} />
                      <Metrica etiqueta="Mantener BTC" valor={numero(p.mantener_btc, 0)} />
                      <Metrica etiqueta="Peor caída" valor={fraccion(p.peor_caida, 1, false)} />
                    </FilaMetricas>
                    <Nota>
                      Desde {fecha(p.desde)}, {p.registros} registros, con las mismas comisiones que el backtest.
                    </Nota>
                  </>
                )}
              </div>
            ))}
          </div>
        </Seccion>
      ) : null}

      {d ? (
        <Seccion titulo="Último estudio" id="estudio">
          <Estudio datos={d} />
        </Seccion>
      ) : null}
    </div>
  );
}
