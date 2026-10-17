"use client";

import Link from "next/link";
import { useState } from "react";

import { api, ErrorApi, pedir } from "@/api/cliente";
import type { Propuesta as PropuestaApi } from "@/api/tipos";
import { SelectorActivos } from "@/componentes/SelectorActivos";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  BloqueComandos,
  Boton,
  CampoTexto,
  Cargando,
  Desplegable,
  ErrorApiVista,
  Nota,
  Seccion,
  Selector,
  TextoPlano,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion } from "@/lib/consulta";
import { formatoCantidad, formatoImporte } from "@/lib/decimal";
import { fecha } from "@/lib/formato";

import { AvisoCostes, AvisoPausa, useFriccion, useOpciones } from "./comun";

const NOMBRES_FRECUENCIA: Record<string, string> = {
  monthly: "cada mes (monthly)",
  quarterly: "cada trimestre (quarterly)",
  weekly: "cada semana (weekly)",
};

/**
 * Simula y, si quieres, REGISTRA la decision en tu ledger con un boton. Registrar es
 * contabilidad: anota las compras en Mi cartera al ultimo cierre descargado. No compra nada.
 */
export function Propuesta() {
  const { estado } = useEstado();
  const opciones = useOpciones();
  const friccion = useFriccion();
  const [elegidos, setElegidos] = useState<string[] | null>(null);
  const [importe, setImporte] = useState("500");
  const [frecuencia, setFrecuencia] = useState("");
  const [falta, setFalta] = useState<string | null>(null);
  const [propuesta, setPropuesta] = useState<PropuestaApi | null>(null);
  const [errorPausa, setErrorPausa] = useState<ErrorApi | null>(null);

  const [pausaAlRegistrar, setPausaAlRegistrar] = useState<ErrorApi | null>(null);
  // La propuesta no se guarda en el servidor: se le reenvian las `compras` tal cual llegaron.
  const registrar = useAccion(async (p: PropuestaApi) => {
    setPausaAlRegistrar(null);
    try {
      const r = await pedir(api.POST("/api/simular/propuesta/registrar", { body: { compras: p.compras } }));
      if (r.registradas > 0) setPropuesta(null);
      return r;
    } catch (e) {
      // 409: se ha pausado entre proponer y registrar. No se anota nada.
      if (e instanceof ErrorApi && e.estado === 409) {
        setPausaAlRegistrar(e);
        return null;
      }
      throw e;
    }
  });
  const limpiarRegistro = registrar.limpiar;

  const proponer = useAccion(async () => {
    if (!friccion) throw new Error("costes no válidos");
    try {
      const r = await pedir(
        api.POST("/api/simular/propuesta", {
          body: { activos: elegidos ?? opciones.datos?.sugeridos ?? [], importe: importe.trim(), frecuencia, ...friccion },
        }),
      );
      setPropuesta(r);
      setErrorPausa(null);
      limpiarRegistro();
      return r;
    } catch (e) {
      // 409: hay pausa de entradas. No es un fallo del programa: se dice y no se propone.
      if (e instanceof ErrorApi && e.estado === 409) {
        setErrorPausa(e);
        setPropuesta(null);
        return null;
      }
      throw e;
    }
  });

  if (opciones.error) return <ErrorApiVista error={opciones.error} />;
  if (!opciones.datos) return <Cargando />;
  const pausa = opciones.datos.pausa ?? estado?.pausa ?? null;
  if (pausa) return <AvisoPausa pausa={pausa} />;

  const ids = elegidos ?? opciones.datos.sugeridos;
  const activos = estado?.activos ?? [];

  return (
    <div className="space-y-4">
      <Seccion titulo="Propuesta simple" id="propuesta">
        <SelectorActivos
          etiqueta="Activos candidatos"
          activos={activos}
          seleccion={ids}
          onCambio={setElegidos}
          usarEtiqueta
        />
        <div className="grid max-w-xl gap-3 sm:grid-cols-2">
          <CampoTexto
            etiqueta="Cuánto aportas cada vez"
            value={importe}
            onChange={(e) => setImporte(e.target.value)}
            inputMode="decimal"
          />
          <Selector etiqueta="Cada cuánto" value={frecuencia} onChange={(e) => setFrecuencia(e.target.value)}>
            <option value="">elige…</option>
            {opciones.datos.frecuencias.map((f) => (
              <option key={f} value={f}>
                {NOMBRES_FRECUENCIA[f] ?? f}
              </option>
            ))}
          </Selector>
        </div>
        <AvisoCostes />
        <Boton
          variante="primario"
          disabled={proponer.enCurso || !friccion}
          onClick={() => {
            if (!ids.length || !frecuencia) {
              setFalta("Elige al menos un activo y una frecuencia.");
              return;
            }
            setFalta(null);
            void proponer.ejecutar();
          }}
        >
          {proponer.enCurso ? "Simulando…" : "Proponer cartera (simulación, no mueve dinero)"}
        </Boton>
        {falta ? <Aviso tipo="critico">{falta}</Aviso> : null}
        {proponer.error ? <ErrorApiVista error={proponer.error} prefijo="No se pudo proponer:" /> : null}
        {errorPausa ? (
          <Aviso tipo="aviso">
            <span className="whitespace-pre-wrap">{errorPausa.detalle}</span>
          </Aviso>
        ) : null}
      </Seccion>

      {registrar.resultado ? (
        <div className="space-y-2">
          {registrar.resultado.problemas.map((p) => (
            <Aviso key={p} tipo="critico">
              {p}
            </Aviso>
          ))}
          {registrar.resultado.registradas > 0 ? (
            <Aviso tipo="hecho" vivo>
              Registradas {registrar.resultado.registradas} compra(s) en tu registro: ya están en{" "}
              <Link href="/plan/cartera/" className="font-semibold underline underline-offset-2">
                Cartera
              </Link>
              . Es contabilidad tuya, al último cierre descargado — NO se ha comprado nada en ningún mercado. Para dinero
              real: invest-ll-execute.
            </Aviso>
          ) : null}
        </div>
      ) : null}

      {propuesta ? (
        <div className={proponer.enCurso ? "space-y-4 opacity-60" : "space-y-4"}>
          <TextoPlano>{propuesta.texto}</TextoPlano>
          <Nota>Esto es una simulación sobre el pasado, no una recomendación ni una previsión.</Nota>

          <Seccion titulo="Llevarla a tu cartera" nivel={3} id="llevar">
            <MarcoTabla etiqueta="Compras de la propuesta">
              <thead>
                <tr>
                  <Th>activo</Th>
                  <Th numerica>importe</Th>
                  <Th numerica>cantidad</Th>
                  <Th numerica>precio de referencia</Th>
                  <Th>cierre del</Th>
                </tr>
              </thead>
              <tbody>
                {propuesta.compras.map((c) => (
                  <tr key={c.symbol}>
                    <Td className="font-medium">{c.symbol}</Td>
                    <Td numerica>{formatoImporte(c.importe)}</Td>
                    <Td numerica>{c.cantidad === null ? "sin precio" : formatoCantidad(c.cantidad)}</Td>
                    <Td numerica>{formatoImporte(c.precio)}</Td>
                    <Td>{fecha(c.fecha)}</Td>
                  </tr>
                ))}
              </tbody>
            </MarcoTabla>
            <Boton onClick={() => void registrar.ejecutar(propuesta)} disabled={registrar.enCurso}>
              {registrar.enCurso ? "Registrando…" : "Registrar estas compras en Cartera"}
            </Boton>
            {registrar.error ? <ErrorApiVista error={registrar.error} prefijo="No se registró:" /> : null}
            {pausaAlRegistrar ? (
              <Aviso tipo="aviso" vivo>
                <strong>No se ha registrado nada:</strong>{" "}
                <span className="whitespace-pre-wrap">{pausaAlRegistrar.detalle}</span>
              </Aviso>
            ) : null}
            <Nota>
              Registrar anota la decisión en tu ledger; no envía ninguna orden. Enviar de verdad exige confirmar cada orden
              por separado, en{" "}
              <Link href="/plan/invertir/" className="text-marca underline underline-offset-2">
                Invertir → Avanzado
              </Link>{" "}
              o con invest-ll-execute.
            </Nota>
            <Desplegable resumen="Los comandos equivalentes (para ejecutar de verdad, fuera del panel)">
              <BloqueComandos lineas={propuesta.comandos} />
            </Desplegable>
          </Seccion>
        </div>
      ) : null}
    </div>
  );
}
