"use client";

import { useMemo } from "react";

import type { Informe as InformeBacktest } from "@/api/tipos";
import { GraficaLinea } from "@/componentes/graficas/Lineas";
import { MarcoTabla, TablaContrato, Td, Th } from "@/componentes/tabla";
import { Aviso, Desplegable, FilaMetricas, Metrica, Seccion } from "@/componentes/ui";
import { compararDecimal, formatoImporte } from "@/lib/decimal";
import { fecha, fraccion, numero } from "@/lib/formato";

const cero = (texto: string | null | undefined) => formatoImporte(texto, { decimales: 0 });
const conSigno = (texto: string | null | undefined) => formatoImporte(texto, { decimales: 0, conSigno: true });

/**
 * La conclusion que decide si la estrategia merece la pena. Siempre a la vista: si no hay
 * referencia, se dice que no la hay en vez de callarlo.
 */
function FrenteAComprarYMantener({ informe }: { informe: InformeBacktest }) {
  const cym = informe.comprar_y_mantener;
  if (cym === null) {
    return (
      <Aviso tipo="aviso">
        Esta simulación no trae referencia de comprar y mantener: no se puede decir si mereció la pena frente a no hacer
        nada. Léela con esa duda.
      </Aviso>
    );
  }
  if (cym.no_hizo_nada) {
    return (
      <Aviso tipo="info">
        Comprar y mantener no llegó a operar en este tramo, así que no hay con qué comparar el resultado.
      </Aviso>
    );
  }

  const tabla = (
    <MarcoTabla etiqueta="Frente a comprar y mantener">
      <thead>
        <tr>
          <Th>
            <span className="sr-only">qué</span>
          </Th>
          <Th numerica>resultado neto</Th>
          <Th numerica>drawdown máximo</Th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <Td className="font-medium">esta estrategia</Td>
          <Td numerica>{conSigno(informe.resultado_neto)}</Td>
          <Td numerica>{cero(informe.drawdown_maximo)}</Td>
        </tr>
        <tr>
          <Td className="font-medium">comprar y mantener</Td>
          <Td numerica>{conSigno(cym.resultado)}</Td>
          <Td numerica>{cero(cym.drawdown)}</Td>
        </tr>
        <tr>
          <Td className="font-medium">diferencia</Td>
          <Td numerica className="font-semibold">
            {conSigno(informe.diferencia)}
          </Td>
          <Td />
        </tr>
      </tbody>
    </MarcoTabla>
  );

  if (informe.bate_al_mercado === true) {
    return (
      <div className="space-y-2">
        <Aviso tipo="hecho">
          Bate a comprar y mantener por <strong>{conSigno(informe.diferencia)}</strong> ({cero(informe.resultado_neto)}{" "}
          frente a {cero(cym.resultado)}).
        </Aviso>
        {tabla}
      </div>
    );
  }
  if (informe.bate_al_mercado === false) {
    let sufrioMenos = false;
    try {
      sufrioMenos = compararDecimal(informe.drawdown_maximo, cym.drawdown) > 0;
    } catch {
      sufrioMenos = false;
    }
    return (
      <div className="space-y-2">
        <Aviso tipo="critico">
          <strong>NO bate a comprar y mantener:</strong> {cero(informe.resultado_neto)} frente a {cero(cym.resultado)} (
          {conSigno(informe.diferencia)}). Todo el riesgo asumido y las comisiones pagadas quedaron por debajo de no hacer
          nada.
        </Aviso>
        {sufrioMenos ? (
          <Aviso tipo="info">
            Aunque su caída máxima fue menor: {cero(informe.drawdown_maximo)} frente a {cero(cym.drawdown)}. Ganó menos,
            pero sufrió menos.
          </Aviso>
        ) : null}
        {tabla}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <Aviso tipo="aviso">La API no dice si bate a comprar y mantener: compara tú las cifras.</Aviso>
      {tabla}
    </div>
  );
}

/**
 * Un backtest en el mismo orden de lectura que el informe de texto. Un panel es mas persuasivo que
 * un texto --las graficas convencen-- y por eso aqui es mas importante, no menos, que el win rate
 * vaya el ultimo y que la comparacion contra no hacer nada este siempre a la vista.
 */
export function Informe({ informe, atenuado = false }: { informe: InformeBacktest; atenuado?: boolean }) {
  const puntos = useMemo(() => informe.curva.map((p) => ({ t: Date.parse(p.fecha), v: p.valor })), [informe.curva]);
  const c = informe.consistencia;
  const primero = informe.curva[0];
  const ultimo = informe.curva[informe.curva.length - 1];

  return (
    <div className={atenuado ? "space-y-4 opacity-60" : "space-y-4"}>
      {!informe.concluyente ? (
        <Aviso tipo="aviso">
          <strong>NO CONCLUYENTE:</strong> {informe.motivo_no_concluyente ?? "la API no da el motivo."}
        </Aviso>
      ) : null}

      <FilaMetricas>
        <Metrica etiqueta="Resultado neto" valor={conSigno(informe.resultado_neto)} />
        <Metrica etiqueta="Drawdown máximo" valor={cero(informe.drawdown_maximo)} />
        <Metrica etiqueta="Operaciones" valor={informe.operaciones.toLocaleString("es-ES")} />
        <Metrica etiqueta="Costes" valor={cero(informe.costes)} />
      </FilaMetricas>

      <FrenteAComprarYMantener informe={informe} />

      {puntos.length ? (
        <GraficaLinea
          titulo="Curva de patrimonio"
          puntos={puntos}
          nombreSerie="Patrimonio"
          cabeceraValor="patrimonio"
          formatoValor={(v) => numero(v, 0)}
          pie={
            primero && ultimo ? (
              <>
                Del {fecha(primero.fecha)} al {fecha(ultimo.fecha)}, con los costes de arriba. Simulación sobre el pasado,
                no una previsión.
              </>
            ) : null
          }
        />
      ) : null}

      {c && c.periodos > 0 ? (
        <Seccion titulo="Regularidad del camino" nivel={3} id="regularidad">
          <FilaMetricas>
            <Metrica etiqueta="Meses en verde" valor={`${c.positivos}/${c.periodos}`} />
            <Metrica etiqueta="Proporción" valor={fraccion(c.proporcion, 0, false)} />
            <Metrica etiqueta="Peor mes" valor={conSigno(c.peor_periodo)} />
            <Metrica etiqueta="Racha en rojo" valor={`${c.racha_en_rojo} meses`} />
          </FilaMetricas>
          {c.aviso ? <Aviso tipo="aviso">{c.aviso}</Aviso> : null}
        </Seccion>
      ) : null}

      <Desplegable resumen="Métricas completas">
        <TablaContrato tabla={informe.metricas} etiqueta="Métricas completas" />
      </Desplegable>
      <Desplegable resumen={`Registro de operaciones (${informe.operaciones})`}>
        <TablaContrato tabla={informe.registro} etiqueta="Registro de operaciones" altoMaximo={420} />
      </Desplegable>
    </div>
  );
}
