"use client";

import { api, pedir } from "@/api/cliente";
import type { OpcionesSimular } from "@/api/tipos";
import { Aviso, Codigo, TextoApi } from "@/componentes/ui";
import { useCostes } from "@/contexto/costes";
import { useEstado } from "@/contexto/estado";
import { useConsulta, type Consulta } from "@/lib/consulta";

/** Las opciones de Simular (frecuencias, sugeridos, estrategias y si hay pausa). */
export function useOpciones(): Consulta<OpcionesSimular> {
  const { versionDatos } = useEstado();
  return useConsulta(`opciones:${versionDatos}`, () => pedir(api.GET("/api/simular/opciones")));
}

/** Los costes de la cabecera, listos para la peticion; `null` si no son validos. */
export function useFriccion(): { comision: string; slippage: string } | null {
  const { comision, slippage, motivo } = useCostes();
  return motivo ? null : { comision, slippage };
}

export function AvisoCostes() {
  const { motivo } = useCostes();
  if (!motivo) return null;
  return (
    <Aviso tipo="critico">
      No se puede simular sin costes válidos: {motivo} Corrígelos en «Costes de toda simulación», arriba.
    </Aviso>
  );
}

export function AvisoPausa({ pausa }: { pausa: string }) {
  return (
    <Aviso tipo="aviso">
      <strong>Pausa activa:</strong> <TextoApi texto={pausa} />. No se proponen entradas nuevas; las posiciones abiertas no se tocan.
      Retírala en Cartera · Protección o con <Codigo>invest-ll-triggers resume</Codigo>.
    </Aviso>
  );
}
