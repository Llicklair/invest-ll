"use client";

import { Compass, PlugZap, Wallet } from "lucide-react";
import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { Accion } from "@/api/tipos";
import { EstadoVacio, NadaQueHacer } from "@/componentes/EstadoVacio";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { TarjetaAccion } from "@/componentes/TarjetaAccion";
import {
  Aviso,
  BotonEnlace,
  Desplegable,
  Encabezado,
  ErrorApiVista,
  Esqueleto,
  Seccion,
  Tarjeta,
  TextoApi,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useModo } from "@/contexto/modo";
import { useConsulta } from "@/lib/consulta";
import { formatoCantidad } from "@/lib/decimal";
import { momento } from "@/lib/formato";

import { HojaConfirmar } from "./HojaConfirmar";
import { HojaYaComprado } from "./HojaYaComprado";
import { OrdenManual } from "./OrdenManual";

function TarjetaConexion() {
  const { modo, conexion, error } = useModo();
  const { versionDatos } = useEstado();
  const conectado = modo === "pruebas" || modo === "real";
  const saldo = useConsulta(conectado ? `saldo:${versionDatos}:${modo}` : null, () => pedir(api.GET("/api/saldo")));
  return (
    <Tarjeta className="space-y-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-marca-suave text-marca" aria-hidden="true">
            <PlugZap className="h-5 w-5" strokeWidth={1.75} />
          </span>
          <div>
            <p className="font-semibold text-tinta">Conexión con Binance</p>
            <p className="text-sm text-tinta-suave">
              {modo === "simulacion"
                ? "Sin conectar: el panel no envía nada."
                : modo === "pruebas"
                  ? "Red de pruebas: órdenes de verdad con dinero ficticio."
                  : modo === "real"
                    ? "Dinero real: cada orden se confirma tecleando la cantidad."
                    : error
                      ? "No se sabe en qué modo está: no se ofrece enviar nada."
                      : "Leyendo el modo…"}
              {conexion?.modo_origen === "entorno" ? " Lo fija el entorno." : ""}
            </p>
          </div>
        </div>
      </div>
      {conectado ? (
        saldo.error ? (
          <ErrorApiVista error={saldo.error} prefijo="No se pudo leer el saldo:" reintentar={saldo.recargar} />
        ) : saldo.datos ? (
          <div>
            <p className="text-sm text-tinta-suave">
              Tu saldo en Binance{modo === "pruebas" ? " (ficticio)" : ""}, leído el {momento(saldo.datos.at)}:
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {saldo.datos.saldo.map((s) => (
                <li key={s.moneda} className="cifras rounded-full bg-superficie-2 px-3 py-1.5 text-[0.9375rem] text-tinta">
                  {formatoCantidad(s.cantidad)} {s.moneda}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <Esqueleto className="h-10" />
        )
      ) : null}
      <BotonEnlace href="/ajustes/#conexion" variante="secundario" tamano="compacto">
        {modo === "simulacion" ? "Conectar Binance" : "Cambiar"}
      </BotonEnlace>
    </Tarjeta>
  );
}

/**
 * Invertir: hazlo (docs/panel-v2.md, 4.3). Que toca hoy, agrupado por donde se hace; confirmar
 * una orden de Binance; anotar una compra del broker; la orden a mano plegada; la conexion.
 */
export function Invertir() {
  const { versionDatos, refrescarDatos } = useEstado();
  const { modo } = useModo();
  const [version, setVersion] = useState(0);
  const hoy = useConsulta(`hoy:${versionDatos}:${version}:${modo ?? "?"}`, () => pedir(api.GET("/api/plan/hoy")));
  const [confirmar, setConfirmar] = useState<Accion | null>(null);
  const [hecho, setHecho] = useState<Accion | null>(null);
  const h = hoy.datos;
  const binance = h?.acciones.filter((a) => a.donde === "binance") ?? [];
  const broker = h?.acciones.filter((a) => a.donde === "broker") ?? [];
  const recargar = () => {
    setVersion((v) => v + 1);
    refrescarDatos();
  };

  return (
    <div>
      <Encabezado titulo="Invertir" bajada="Lo que toca hacer hoy según tu plan, y nada más." />

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-10">
          {hoy.error ? <ErrorApiVista error={hoy.error} prefijo="No se pudo calcular qué toca:" reintentar={hoy.recargar} /> : null}
          {!h && hoy.cargando ? (
            <div className="space-y-4" aria-busy="true">
              <Esqueleto className="h-8 w-48" />
              <Esqueleto className="h-48" />
              <Esqueleto className="h-48" />
            </div>
          ) : null}

          {h ? (
            <div className={hoy.cargando ? "space-y-10 opacity-70 transition-opacity" : "space-y-10"}>
              <section aria-labelledby="hoy-titulo" className="space-y-4">
                <h2 id="hoy-titulo" className="titular text-2xl font-semibold text-tinta">
                  Qué toca hoy
                </h2>
                {h.avisos.map((a) => (
                  <Aviso key={a} tipo="aviso">
                    <TextoApi texto={a} />
                  </Aviso>
                ))}
                {h.sin_plan ? (
                  <EstadoVacio
                    icono={Compass}
                    tono="neutro"
                    titulo="Todavía no tienes un plan"
                    accion={
                      <BotonEnlace href="/estrategias/" variante="primario">
                        Hacer mi plan
                      </BotonEnlace>
                    }
                  >
                    {h.resumen}
                  </EstadoVacio>
                ) : h.acciones.length === 0 ? (
                  <NadaQueHacer resumen={h.resumen} />
                ) : (
                  <p className="text-[0.9375rem] text-tinta-suave">{h.resumen}</p>
                )}
              </section>

              {binance.length ? (
                <Seccion
                  titulo="En Binance"
                  bajada={
                    modo === "simulacion"
                      ? "Lo haría el panel por ti, confirmando tú cada orden. Para eso hay que conectar Binance."
                      : "Lo hace el panel: revisas cada orden y la confirmas tecleando la cantidad."
                  }
                >
                  <div className="space-y-4">
                    {binance.map((a) => (
                      <TarjetaAccion key={a.id} accion={a} modo={modo} onConfirmar={setConfirmar} onHecho={setHecho} />
                    ))}
                  </div>
                </Seccion>
              ) : null}

              {broker.length ? (
                <Seccion
                  titulo="En tu bróker"
                  bajada="Tu lista de la compra. Lo compras tú donde tengas tus fondos y luego lo anotas aquí."
                >
                  <div className="space-y-4">
                    {broker.map((a) => (
                      <TarjetaAccion key={a.id} accion={a} modo={modo} onConfirmar={setConfirmar} onHecho={setHecho} />
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-x-4">
                    <QueEsEsto clave="broker" />
                    <QueEsEsto clave="ucits" />
                  </div>
                </Seccion>
              ) : null}
            </div>
          ) : null}

          <Desplegable resumen="Avanzado: una orden a mano">
            <OrdenManual alEnviar={recargar} />
          </Desplegable>
        </div>

        <aside className="min-w-0 space-y-6">
          <TarjetaConexion />
          <Tarjeta className="p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <Wallet aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
              <p className="font-semibold text-tinta">Lo que ya tienes</p>
            </div>
            <p className="mt-2 text-[0.9375rem] text-tinta-suave">
              Todo lo que compras aquí o anotas pasa a tu cartera, con su fecha y su precio.
            </p>
            <BotonEnlace href="/cartera/" variante="fantasma" tamano="compacto" className="mt-2 -ml-3">
              Ver mi cartera
            </BotonEnlace>
          </Tarjeta>
        </aside>
      </div>

      <HojaConfirmar accion={confirmar} modo={modo} onCerrar={() => setConfirmar(null)} onTerminado={recargar} />
      <HojaYaComprado accion={hecho} onCerrar={() => setHecho(null)} onTerminado={recargar} />
    </div>
  );
}
