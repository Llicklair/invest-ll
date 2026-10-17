"use client";

import { useState } from "react";

import { api, conPlazo, pedir } from "@/api/cliente";
import { Pestanas } from "@/componentes/Pestanas";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import { Aviso, CargandoLento, Chip, Encabezado, ErrorApiVista, Nota, Seccion, TextoApi } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAncla } from "@/lib/ancla";
import { useConsulta } from "@/lib/consulta";
import { duracion, fecha, fraccion, numero } from "@/lib/formato";

import { Alertas } from "./Alertas";
import { Investigacion } from "./Investigacion";
import { MercadoAFondo } from "./MercadoAFondo";
import { Probar } from "./probar/Probar";
import { Seguimiento } from "./Seguimiento";

const PESTANAS = [
  { clave: "probar", texto: "Probar estrategias" },
  { clave: "catalogo", texto: "Catálogo completo" },
  { clave: "investigacion", texto: "Investigación" },
  { clave: "estimado", texto: "Estimado vs real" },
  { clave: "alertas", texto: "Alertas de datos" },
  { clave: "mercado", texto: "Mercado a fondo" },
] as const;
type Pestana = (typeof PESTANAS)[number]["clave"];

function esPestana(v: string): v is Pestana {
  return PESTANAS.some((p) => p.clave === v);
}

/**
 * Todas las estrategias, tambien las de laboratorio y la retirada, con sus cifras sobre el pasado
 * en la jerga de quien sabe (aqui si se puede).
 */
function CatalogoCompleto() {
  const { versionDatos } = useEstado();
  const consulta = useConsulta(`catalogo:${versionDatos}`, () => pedir(api.GET("/api/estrategias", conPlazo())));
  const c = consulta.datos;
  return (
    <Seccion
      titulo="Catálogo completo"
      bajada="Las del camino principal, las de laboratorio y las retiradas, con sus cifras desde 10.000 al principio de los datos."
    >
      {consulta.error ? <ErrorApiVista error={consulta.error} reintentar={consulta.recargar} /> : null}
      {!c && consulta.cargando ? (
        <CargandoLento texto="Cargando…" lento="Calculando las estrategias con los datos descargados… la primera vez tarda unos segundos." />
      ) : null}
      {c ? (
        <>
          <MarcoTabla etiqueta="Catálogo completo de estrategias">
            <thead>
              <tr>
                <Th>estrategia</Th>
                <Th>mercado</Th>
                <Th numerica>riesgo</Th>
                <Th>desde</Th>
                <Th numerica>valor final</Th>
                <Th numerica>CAGR</Th>
                <Th numerica>máx. drawdown</Th>
                <Th>fecha del drawdown</Th>
                <Th numerica>peor racha</Th>
                <Th numerica>exposición</Th>
                <Th numerica>operaciones/año</Th>
                <Th>evidencia</Th>
              </tr>
            </thead>
            <tbody>
              {c.estrategias.map((e) => (
                <tr key={e.clave}>
                  <Td className="font-medium">
                    <span className="flex items-center gap-2">
                      {e.nombre}
                      {e.retirada ? <Chip tono="baja">retirada</Chip> : e.laboratorio ? <Chip>laboratorio</Chip> : null}
                    </span>
                  </Td>
                  <Td>{e.mercado}</Td>
                  <Td numerica>{e.riesgo}</Td>
                  <Td>{e.historico ? fecha(e.historico.desde) : "—"}</Td>
                  <Td numerica>{e.historico ? numero(e.historico.valor_final, 0) : "—"}</Td>
                  <Td numerica>{e.historico ? fraccion(e.historico.crecimiento_anual, 1) : "—"}</Td>
                  <Td numerica>{e.historico ? fraccion(e.historico.peor_caida, 1) : "—"}</Td>
                  <Td>{e.historico ? fecha(e.historico.peor_caida_fecha) : "—"}</Td>
                  <Td numerica>{e.historico ? duracion(e.historico.peor_racha_anios) : "—"}</Td>
                  <Td numerica>{e.historico ? fraccion(e.historico.tiempo_invertido, 0, false) : "—"}</Td>
                  <Td numerica>{e.historico ? numero(e.historico.operaciones_al_anio, 1) : "—"}</Td>
                  <Td className="text-tinta-suave">{e.evidencia.texto}</Td>
                </tr>
              ))}
            </tbody>
          </MarcoTabla>
          {c.estrategias
            .filter((e) => e.retirada || !e.disponible)
            .map((e) => (
              <Aviso key={e.clave} tipo={e.retirada ? "aviso" : "info"} titulo={e.nombre}>
                {e.retirada ? e.avisos[0] : e.motivo}
              </Aviso>
            ))}
          <Nota>{c.nota}</Nota>
        </>
      ) : null}
    </Seccion>
  );
}

function Reserva() {
  const { estado } = useEstado();
  if (!estado?.reserva) return null;
  return (
    <Aviso tipo="info" className="mb-6">
      <TextoApi texto={estado.reserva} />
    </Aviso>
  );
}

/**
 * Laboratorio: todo lo del panel anterior, para quien sabe (docs/panel-v2.md, 4.5). Aqui la jerga
 * esta permitida; lo que no cambia es que nada de esto mueve dinero.
 */
export function Laboratorio() {
  const [ancla, fijarAncla] = useAncla();
  const [inicial] = useState<Pestana>("probar");
  const actual: Pestana = esPestana(ancla) ? ancla : inicial;
  return (
    <div>
      <Encabezado
        antetitulo="Más"
        titulo="Laboratorio"
        bajada="Para quien sabe de inversiones: probar estrategias con tus parámetros, la investigación en curso y las alertas de datos. Nada de esto mueve dinero."
      />
      <Reserva />
      <Pestanas etiqueta="Secciones del laboratorio" pestanas={PESTANAS} actual={actual} onCambio={fijarAncla} idPanel="panel-laboratorio" />
      <div id="panel-laboratorio" role="tabpanel" aria-labelledby={`pestana-${actual}`} className="pt-8" tabIndex={0}>
        {actual === "probar" ? <Probar /> : null}
        {actual === "catalogo" ? <CatalogoCompleto /> : null}
        {actual === "investigacion" ? <Investigacion /> : null}
        {actual === "estimado" ? <Seguimiento /> : null}
        {actual === "alertas" ? <Alertas /> : null}
        {actual === "mercado" ? <MercadoAFondoConGrafica /> : null}
      </div>
    </div>
  );
}

function MercadoAFondoConGrafica() {
  const [elegido, setElegido] = useState<string | null>(null);
  return <MercadoAFondo elegido={elegido} onElegir={setElegido} />;
}
