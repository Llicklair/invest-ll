"use client";

import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import { SelectorActivos } from "@/componentes/SelectorActivos";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  Boton,
  CampoTexto,
  Cargando,
  Desplegable,
  ErrorApiVista,
  FilaMetricas,
  Metrica,
  Nota,
  Seccion,
  Segmentado,
  TextoPlano,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion, useConsulta, useRetardado } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { fraccion, numero } from "@/lib/formato";

import { AvisoCostes, useFriccion, useOpciones } from "./comun";
import { Informe } from "./Informe";

const cero = (t: string) => formatoImporte(t, { decimales: 0 });

function MedirAportaciones({ ids }: { ids: string[] }) {
  const friccion = useFriccion();
  const [aportacion, setAportacion] = useState("500");
  const [cada, setCada] = useState("21");
  const accion = useAccion(() => {
    if (!friccion) throw new Error("costes no válidos");
    return pedir(
      api.POST("/api/simular/cartera/aportaciones", {
        body: { activos: ids, aportacion: aportacion.trim(), cada: Number(cada), ...friccion },
      }),
    );
  });
  const r = accion.resultado;
  return (
    <div className="space-y-3">
      <div className="grid max-w-xl gap-3 sm:grid-cols-2">
        <CampoTexto etiqueta="Aportación" value={aportacion} onChange={(e) => setAportacion(e.target.value)} inputMode="decimal" />
        <CampoTexto
          etiqueta="Cada cuántos periodos"
          type="number"
          min={1}
          max={250}
          value={cada}
          onChange={(e) => setCada(e.target.value)}
          ayuda="21 sesiones ≈ un mes de bolsa"
        />
      </div>
      <Boton variante="primario" onClick={() => void accion.ejecutar()} disabled={accion.enCurso || !friccion}>
        {accion.enCurso ? "Simulando…" : "Simular las aportaciones"}
      </Boton>
      {accion.error ? <ErrorApiVista error={accion.error} /> : null}
      {r ? (
        <div className={accion.enCurso ? "space-y-3 opacity-60" : "space-y-3"}>
          <FilaMetricas>
            <Metrica etiqueta="Aportado" valor={cero(r.aportado)} />
            <Metrica etiqueta="Valor final" valor={cero(r.valor_final)} />
            <Metrica
              etiqueta="Ganancia"
              valor={formatoImporte(r.ganancia, { decimales: 0, conSigno: true })}
              detalle={`${fraccion(r.rentabilidad, 0)} sobre lo aportado`}
            />
            <Metrica etiqueta="Costes" valor={cero(r.costes)} />
          </FilaMetricas>
          {r.bate_a_todo_de_golpe ? (
            <Aviso tipo="hecho">Aportar poco a poco salió mejor que invertirlo todo de golpe.</Aviso>
          ) : (
            <Aviso tipo="info">
              Invertir los {cero(r.aportado)} de golpe al principio habría dado {cero(r.valor_todo_de_golpe)}. Aportar poco a
              poco no busca ganar más: busca que la fecha de entrada deje de decidir el resultado.
            </Aviso>
          )}
          <TextoPlano>{r.texto}</TextoPlano>
        </div>
      ) : null}
    </div>
  );
}

function MedirRotacion({ ids }: { ids: string[] }) {
  const friccion = useFriccion();
  const [lookback, setLookback] = useState("60");
  const [capital, setCapital] = useState("10000");
  const accion = useAccion(() => {
    if (!friccion) throw new Error("costes no válidos");
    return pedir(
      api.POST("/api/simular/cartera/rotacion", {
        body: { activos: ids, lookback: Number(lookback), capital: capital.trim(), ...friccion },
      }),
    );
  });
  return (
    <div className="space-y-3">
      <div className="grid max-w-xl gap-3 sm:grid-cols-2">
        <CampoTexto
          etiqueta="Periodos para medir el impulso"
          type="number"
          min={5}
          max={400}
          value={lookback}
          onChange={(e) => setLookback(e.target.value)}
        />
        <CampoTexto etiqueta="Capital inicial" value={capital} onChange={(e) => setCapital(e.target.value)} inputMode="decimal" />
      </div>
      <Boton variante="primario" onClick={() => void accion.ejecutar()} disabled={accion.enCurso || !friccion}>
        {accion.enCurso ? "Simulando…" : "Simular la rotación"}
      </Boton>
      {accion.error ? <ErrorApiVista error={accion.error} /> : null}
      {accion.resultado ? <Informe informe={accion.resultado} atenuado={accion.enCurso} /> : null}
    </div>
  );
}

/** Aportaciones periodicas a una cartera: primero, si de verdad esta diversificada. */
export function Aportaciones() {
  const { estado } = useEstado();
  const opciones = useOpciones();
  const [elegidos, setElegidos] = useState<string[] | null>(null);
  const [medir, setMedir] = useState<"aportaciones" | "rotacion">("aportaciones");

  // La preseleccion la calcula la API (activos que se solapan en el tiempo): escoger los primeros
  // de la lista podia juntar un historico que acaba en 2010 con otro que empieza en 2017.
  const ids = elegidos ?? opciones.datos?.sugeridos ?? [];
  const idsRetardados = useRetardado(ids.join("|"), 400);
  const analisis = useConsulta(idsRetardados.split("|").filter(Boolean).length >= 2 ? `analisis:${idsRetardados}` : null, () =>
    pedir(api.POST("/api/simular/cartera/analisis", { body: { activos: idsRetardados.split("|") } })),
  );
  const a = analisis.datos;

  if (opciones.error) return <ErrorApiVista error={opciones.error} />;
  if (!opciones.datos && elegidos === null) return <Cargando />;

  return (
    <div className="space-y-4">
      <Seccion titulo="Aportaciones periódicas a una cartera" id="aportaciones">
        <SelectorActivos
          etiqueta="Activos"
          activos={estado?.activos ?? []}
          seleccion={ids}
          onCambio={setElegidos}
          usarEtiqueta
        />
        {ids.length < 2 ? (
          <Aviso tipo="info">Elige al menos dos activos: una cartera de uno no es una cartera.</Aviso>
        ) : (
          <>
            {analisis.error ? <ErrorApiVista error={analisis.error} prefijo="No se pudo formar el universo:" /> : null}
            {!a && analisis.cargando ? <Cargando texto="Midiendo la diversificación…" /> : null}
            {a && !analisis.error ? (
              <div className={analisis.cargando ? "space-y-3 opacity-60" : "space-y-3"}>
                <Nota>
                  {a.fechas_comunes.toLocaleString("es-ES")} fechas comunes ({a.desde} a {a.hasta})
                </Nota>
                <FilaMetricas columnas={3}>
                  <Metrica etiqueta="Activos" valor={a.activos} />
                  <Metrica etiqueta="Activos efectivos" valor={numero(a.activos_efectivos, 1)} />
                  <Metrica etiqueta="Correlación media" valor={numero(a.correlacion_media, 2)} />
                </FilaMetricas>
                {!a.diversificada ? (
                  <Aviso tipo="aviso">
                    {a.aviso ??
                      `Tus ${a.activos} activos equivalen a ${numero(a.activos_efectivos, 1)} independientes. Con una correlación media de ${numero(a.correlacion_media, 2)} se mueven casi a la vez: tener varios no te protege de una caída general.`}
                  </Aviso>
                ) : null}
                <Desplegable resumen="Correlación por pares">
                  <MarcoTabla etiqueta="Correlación por pares">
                    <thead>
                      <tr>
                        <Th>par</Th>
                        <Th numerica>correlación</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {a.pares.map((p) => (
                        <tr key={p.par}>
                          <Td>{p.par}</Td>
                          <Td numerica>{numero(p.correlacion, 2)}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </MarcoTabla>
                </Desplegable>
              </div>
            ) : null}
          </>
        )}
      </Seccion>

      {ids.length >= 2 ? (
        <Seccion titulo="Qué quieres medir" nivel={3} id="medir">
          <Segmentado
            etiqueta="Qué quieres medir"
            ocultarEtiqueta
            opciones={[
              { valor: "aportaciones", texto: "Aportaciones periódicas" },
              { valor: "rotacion", texto: "Rotación entre activos" },
            ]}
            valor={medir}
            onCambio={setMedir}
          />
          <AvisoCostes />
          {medir === "aportaciones" ? <MedirAportaciones ids={ids} /> : <MedirRotacion ids={ids} />}
        </Seccion>
      ) : null}
    </div>
  );
}
