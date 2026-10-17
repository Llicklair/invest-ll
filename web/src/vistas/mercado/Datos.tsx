"use client";

import { api, pedir } from "@/api/cliente";
import { MarcoTabla, Td, TdVariacion, Th } from "@/componentes/tabla";
import { Aviso, Cargando, ErrorApiVista, Nota } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useConsulta } from "@/lib/consulta";
import { fecha, fraccion, precio } from "@/lib/formato";
import { nombreLlano } from "@/lib/nombres";

/**
 * El ultimo cierre que tiene el panel de cada activo, con su nombre llano. Para traer precios
 * nuevos esta "Actualizar ahora" (componentes/DatosAlDia.tsx): aqui solo se mira.
 */
export function PreciosPorActivo() {
  const { versionDatos } = useEstado();
  const consulta = useConsulta(`datos:${versionDatos}`, () => pedir(api.GET("/api/mercado/datos")));
  const datos = consulta.datos;
  const viejos = datos ? datos.desfasados.map((s) => nombreLlano(s)) : [];

  return (
    <div className="space-y-3">
      <Nota>El último precio de cierre que tiene el panel de cada cosa, y de qué día es.</Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} reintentar={consulta.recargar} /> : null}
      {!datos && consulta.cargando ? <Cargando /> : null}
      {datos && datos.filas.length === 0 ? <Aviso tipo="info">Todavía no hay precios guardados.</Aviso> : null}
      {datos && datos.filas.length ? (
        <MarcoTabla etiqueta="Último precio de cada activo" altoMaximo={420}>
          <thead>
            <tr>
              <Th>qué</Th>
              <Th numerica>último cierre</Th>
              <Th numerica>ese día</Th>
              <Th>de cuándo</Th>
            </tr>
          </thead>
          <tbody className={consulta.cargando ? "opacity-60" : undefined}>
            {datos.filas.map((f) => (
              <tr key={f.activo}>
                <Td className="font-medium">{nombreLlano(f.activo)}</Td>
                <Td numerica>{precio(f.ultimo_cierre)}</Td>
                <TdVariacion valor={f.variacion} texto={fraccion(f.variacion, 2)} />
                <Td>
                  {fecha(f.fecha)}
                  {datos.desfasados.includes(f.activo) ? <span className="ml-1.5 text-xs font-semibold text-tinta">(no es reciente)</span> : null}
                </Td>
              </tr>
            ))}
          </tbody>
        </MarcoTabla>
      ) : null}
      {viejos.length ? (
        <Aviso tipo="aviso">
          {/* La lista va al final: los nombres pueden acabar en punto ("EE.UU.") y saldria "EE.UU..". */}
          No hay precios recientes de estos, así que lo que ves de ellos no es actual: <strong>{viejos.join(", ")}</strong>
        </Aviso>
      ) : null}
    </div>
  );
}
