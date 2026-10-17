"use client";

import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";
import { MarcoTabla, Td, TdVariacion, Th } from "@/componentes/tabla";
import { Aviso, Boton, Cargando, ErrorApiVista, Nota, Seccion } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion, useConsulta } from "@/lib/consulta";
import { fecha, fraccion, numero } from "@/lib/formato";

/** Segundos desde `inicio` mientras `activo`; para que una operacion larga no parezca colgada. */
function useSegundos(inicio: number | null): number {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    if (inicio === null) return;
    const t = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [inicio]);
  return inicio === null ? 0 : Math.max(0, Math.round((ahora - inicio) / 1000));
}

export function DatosDescargados() {
  const { versionDatos, refrescarDatos } = useEstado();
  const consulta = useConsulta(`datos:${versionDatos}`, () => pedir(api.GET("/api/mercado/datos")));
  const [inicio, setInicio] = useState<number | null>(null);
  const segundos = useSegundos(inicio);

  const actualizar = useAccion(async () => {
    try {
      const r = await pedir(api.POST("/api/mercado/actualizar"));
      refrescarDatos();
      return r;
    } finally {
      setInicio(null);
    }
  });

  const datos = consulta.datos;
  const resultado = actualizar.resultado;
  const fallos = resultado ? resultado.resultados.filter((r) => !r.ok) : [];

  return (
    <Seccion titulo="Datos descargados" id="datos">
      <Nota>
        Último cierre de cada histórico descargado. Para actualizarlo hay que volver a descargar con invest-ll-fetch: el
        motor no toca la red por diseño.
      </Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!datos && consulta.cargando ? <Cargando /> : null}
      {datos && datos.filas.length === 0 ? <Aviso tipo="info">No hay históricos que mostrar.</Aviso> : null}
      {datos && datos.filas.length ? (
        <MarcoTabla etiqueta="Datos descargados">
          <thead>
            <tr>
              <Th>activo</Th>
              <Th numerica>último cierre</Th>
              <Th numerica>variación</Th>
              <Th>fecha</Th>
              <Th numerica>velas</Th>
              <Th>descargado</Th>
            </tr>
          </thead>
          <tbody className={consulta.cargando ? "opacity-60" : undefined}>
            {datos.filas.map((f) => (
              <tr key={f.activo}>
                <Td className="font-medium">{f.activo}</Td>
                <Td numerica>{numero(f.ultimo_cierre, 2)}</Td>
                <TdVariacion valor={f.variacion} texto={fraccion(f.variacion, 2)} />
                <Td>
                  {fecha(f.fecha)}
                  {datos.desfasados.includes(f.activo) ? <span className="ml-1.5 text-xs font-semibold text-tinta">(desfasado)</span> : null}
                </Td>
                <Td numerica>{f.velas.toLocaleString("es-ES")}</Td>
                <Td className="text-tinta-2">{f.descargado ? fecha(f.descargado) : "sin procedencia"}</Td>
              </tr>
            ))}
          </tbody>
        </MarcoTabla>
      ) : null}
      {datos && datos.desfasados.length ? (
        <Aviso tipo="aviso">
          Estos históricos no llegan a datos recientes: <strong>{datos.desfasados.join(", ")}</strong>. Los datos que
          ves de ellos no son actuales.
        </Aviso>
      ) : null}

      <div className="space-y-2 pt-2">
        <Boton
          onClick={() => {
            setInicio(Date.now());
            void actualizar.ejecutar();
          }}
          disabled={actualizar.enCurso}
        >
          Actualizar todos los históricos (descarga de internet, tarda un rato)
        </Boton>
        {actualizar.enCurso ? (
          <div className="space-y-1.5 rounded-md border border-borde bg-superficie p-3" role="status" aria-live="polite">
            <p className="text-sm font-medium">Descargando… lleva {segundos} s.</p>
            <progress className="h-1.5 w-full max-w-md accent-[var(--acento)]" aria-label="Descarga en curso" />
            <p className="text-xs text-tinta-2">
              La API re-descarga cada histórico con los parámetros de su procedencia y devuelve el resultado de cada
              activo al terminar. No cierres la pestaña.
            </p>
          </div>
        ) : null}
        {actualizar.error ? <ErrorApiVista error={actualizar.error} prefijo="La actualización falló:" /> : null}
        {resultado ? (
          <div className="space-y-2" role="status">
            <Aviso tipo={fallos.length ? "critico" : "hecho"}>
              <strong>
                Terminado: {resultado.resultados.length - fallos.length} bien, {fallos.length} con fallo
              </strong>
              {resultado.saltados.length ? `, ${resultado.saltados.length} saltado(s)` : ""}.
            </Aviso>
            <MarcoTabla etiqueta="Resultado de la actualización por activo">
              <thead>
                <tr>
                  <Th>activo</Th>
                  <Th>resultado</Th>
                  <Th>detalle</Th>
                </tr>
              </thead>
              <tbody>
                {resultado.resultados.map((r) => (
                  <tr key={r.symbol}>
                    <Td className="font-medium">{r.symbol}</Td>
                    <Td className={r.ok ? "text-tinta" : "font-semibold text-critico-tinta"}>{r.ok ? "bien" : "fallo"}</Td>
                    <Td className="whitespace-normal text-tinta-2">{r.detalle}</Td>
                  </tr>
                ))}
                {resultado.saltados.map((s) => (
                  <tr key={`saltado-${s}`}>
                    <Td className="font-medium">{s}</Td>
                    <Td>saltado</Td>
                    <Td className="whitespace-normal text-tinta-2">
                      sin metadatos de procedencia: no se adivinan los parámetros de descarga
                    </Td>
                  </tr>
                ))}
              </tbody>
            </MarcoTabla>
          </div>
        ) : null}
      </div>
    </Seccion>
  );
}
