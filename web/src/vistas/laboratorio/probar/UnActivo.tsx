"use client";

import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { EstrategiaUnActivo, PeticionUnActivo } from "@/api/tipos";
import { Boton, CampoTexto, Deslizador, ErrorApiVista, Seccion, Selector } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion } from "@/lib/consulta";

import { AvisoCostes, useFriccion, useOpciones } from "./comun";
import { Informe } from "./Informe";

const ESTRATEGIAS: Record<EstrategiaUnActivo, string> = {
  "cruce-medias": "Cruce de medias",
  "precio-vs-media": "Precio vs media",
  "ruptura-maximos": "Ruptura de máximos",
};

function esEstrategiaUnActivo(v: string): v is EstrategiaUnActivo {
  return v in ESTRATEGIAS;
}

function Entero({
  etiqueta,
  valor,
  min,
  max,
  onCambio,
}: {
  etiqueta: string;
  valor: string;
  min: number;
  max: number;
  onCambio: (v: string) => void;
}) {
  return <CampoTexto etiqueta={etiqueta} type="number" min={min} max={max} step={1} value={valor} onChange={(e) => onCambio(e.target.value)} />;
}

export function UnActivo() {
  const { estado } = useEstado();
  const opciones = useOpciones();
  const friccion = useFriccion();
  const activos = estado?.activos ?? [];
  const [activo, setActivo] = useState<string | null>(null);
  const [estrategia, setEstrategiaUnActivo] = useState<EstrategiaUnActivo>("cruce-medias");
  const [fraccion, setFraccion] = useState(1);
  const [corta, setCorta] = useState("10");
  const [larga, setLarga] = useState("30");
  const [periodos, setPeriodos] = useState("50");
  const [margen, setMargen] = useState(0);
  const [lookback, setLookback] = useState("20");
  const [capital, setCapital] = useState("10000");

  const id = activo ?? activos[0]?.id ?? "";
  // Solo las estrategias que la API dice tener (si dice alguna); el orden es el del panel viejo.
  const disponibles = (Object.keys(ESTRATEGIAS) as EstrategiaUnActivo[]).filter(
    (e) => !opciones.datos || opciones.datos.estrategias.length === 0 || opciones.datos.estrategias.includes(e),
  );

  const evaluar = useAccion(() => {
    if (!friccion) throw new Error("costes no válidos");
    // El contrato pide todos los parametros (los que no usa la estrategia elegida se ignoran).
    const cuerpo: PeticionUnActivo = {
      activo: id,
      estrategia,
      fraccion: fraccion.toFixed(1),
      capital: capital.trim(),
      ...friccion,
      corta: Number(corta),
      larga: Number(larga),
      periodos: Number(periodos),
      margen,
      lookback: Number(lookback),
    };
    return pedir(api.POST("/api/simular/activo", { body: cuerpo }));
  });

  return (
    <div className="space-y-4">
      <Seccion titulo="Una estrategia sobre un activo" id="un-activo">
        <Selector etiqueta="Activo" value={id} onChange={(e) => setActivo(e.target.value)} className="max-w-md">
          {activos.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label} - {a.provider}
            </option>
          ))}
        </Selector>
        <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
          <Selector
            etiqueta="Estrategia"
            value={estrategia}
            onChange={(e) => {
              if (esEstrategiaUnActivo(e.target.value)) setEstrategiaUnActivo(e.target.value);
            }}
          >
            {disponibles.map((e) => (
              <option key={e} value={e}>
                {ESTRATEGIAS[e]}
              </option>
            ))}
          </Selector>
          <Deslizador
            etiqueta="Fracción del capital por entrada"
            valor={fraccion}
            min={0.1}
            max={1}
            paso={0.1}
            formato={(v) => v.toFixed(1)}
            onCambio={(v) => setFraccion(Math.round(v * 10) / 10)}
          />
          {estrategia === "cruce-medias" ? (
            <>
              <Entero etiqueta="Media corta" valor={corta} min={2} max={200} onCambio={setCorta} />
              <Entero etiqueta="Media larga" valor={larga} min={3} max={400} onCambio={setLarga} />
            </>
          ) : null}
          {estrategia === "precio-vs-media" ? (
            <>
              <Entero etiqueta="Periodos" valor={periodos} min={2} max={400} onCambio={setPeriodos} />
              <Deslizador
                etiqueta="Margen de salida"
                valor={margen}
                min={0}
                max={0.1}
                paso={0.01}
                formato={(v) => v.toFixed(2)}
                onCambio={(v) => setMargen(Math.round(v * 100) / 100)}
              />
            </>
          ) : null}
          {estrategia === "ruptura-maximos" ? (
            <Entero etiqueta="Periodos de ruptura" valor={lookback} min={2} max={400} onCambio={setLookback} />
          ) : null}
          <CampoTexto etiqueta="Capital inicial" value={capital} onChange={(e) => setCapital(e.target.value)} inputMode="decimal" />
        </div>
        <AvisoCostes />
        <Boton variante="primario" onClick={() => void evaluar.ejecutar()} disabled={evaluar.enCurso || !friccion || !id}>
          {evaluar.enCurso ? "Evaluando…" : "Evaluar la estrategia"}
        </Boton>
        {evaluar.error ? <ErrorApiVista error={evaluar.error} prefijo="No se pudo evaluar:" /> : null}
      </Seccion>
      {evaluar.resultado ? <Informe informe={evaluar.resultado} atenuado={evaluar.enCurso} /> : null}
    </div>
  );
}
