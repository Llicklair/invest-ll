"use client";

import { ArrowLeft, Bot, CircleAlert, FlaskConical, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import type { DetalleEstrategia, ResultadoPrueba } from "@/api/tipos";
import { CampoImporte } from "@/componentes/CampoImporte";
import { EstadoVacio } from "@/componentes/EstadoVacio";
import { Hoja } from "@/componentes/Hoja";
import { Aviso, Boton, BotonEnlace, CampoTexto, CargandoLento, Desplegable, ErrorApiVista, Esqueleto, Seccion, Selector, Tarjeta, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { fraccion, hoyLocal, momento } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";
import { nombreExchange } from "@/lib/nombres";
import { nombreIntervalo } from "@/lib/vivo";
import { CurvaBot } from "@/vistas/bots/CurvaBot";

import { ChipAutor, ChipEstadoEstrategia, CifrasPrueba, DatosPrueba, periodoPrueba } from "./comun";
import { EditorEstrategia } from "./Editor";

/** "2025-10-17" de hace `dias` dias, en la zona de quien mira (para los campos de fecha). */
function haceDias(dias: number): string {
  const d = new Date(Date.now() - dias * 86_400_000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Probar sobre el pasado: exchange, capital y fechas (POST /api/medida/{id}/probar). */
function Probar({ estrategia, onProbada }: { estrategia: DetalleEstrategia; onProbada: (r: ResultadoPrueba) => void }) {
  const disponibles = useConsulta("conexiones:disponibles", () => pedir(api.GET("/api/conexiones/disponibles")));
  const [exchange, setExchange] = useState(estrategia.ultima_prueba?.exchange ?? "binance");
  const [capital, setCapital] = useState("1.000");
  const [desde, setDesde] = useState(haceDias(365));
  const [hasta, setHasta] = useState(hoyLocal());
  const capitalLimpio = leerImporte(capital);
  const errorCapital = capital.trim() === "" ? "Pon con cuánto capital probarla." : capitalLimpio === null || Number(capitalLimpio) <= 0 ? "Escribe una cantidad: 1.000 o 2500,50." : null;
  const errorFechas = desde && hasta && desde >= hasta ? "La fecha de inicio tiene que ser anterior a la de fin." : null;
  const probar = useAccion(async () => {
    if (capitalLimpio === null) return null;
    const r = await pedir(
      api.POST("/api/medida/{estrategia_id}/probar", {
        params: { path: { estrategia_id: estrategia.id } },
        body: { exchange, capital: capitalLimpio, desde: `${desde}T00:00:00Z`, hasta: `${hasta}T00:00:00Z` },
      }),
    );
    onProbada(r);
    return r;
  });
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!errorCapital && !errorFechas) void probar.ejecutar();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Selector etiqueta="Con las velas de" value={exchange} onChange={(e) => setExchange(e.target.value)} ayuda="Cada exchange tiene sus precios y sus comisiones.">
          {(disponibles.datos ?? [{ id: exchange, nombre: nombreExchange(exchange) }]).map((d) => (
            <option key={d.id} value={d.id}>
              {d.nombre}
            </option>
          ))}
        </Selector>
        <CampoImporte etiqueta="Con cuánto capital" moneda="USDC" valor={capital} onCambio={setCapital} error={capital.trim() ? errorCapital : null} atajos={["500", "1000", "5000"]} />
        <CampoTexto etiqueta="Desde" type="date" value={desde} max={hasta} onChange={(e) => setDesde(e.target.value)} />
        <CampoTexto etiqueta="Hasta" type="date" value={hasta} max={hoyLocal()} onChange={(e) => setHasta(e.target.value)} error={errorFechas} />
      </div>
      <p className="text-sm text-tinta-suave">
        Con comisiones y deslizamiento, frente a mantener el mismo capital. Cada prueba de una versión nueva cuenta: probar muchas y quedarse con la mejor se parece a hacer trampa.
      </p>
      {probar.error ? <ErrorApiVista error={probar.error} prefijo="No se pudo probar:" /> : null}
      {probar.enCurso ? <CargandoLento texto="Probándola sobre el pasado…" lento="Sigue probando: con velas cortas y muchos meses tarda un poco…" /> : null}
      <Boton type="submit" disabled={probar.enCurso || errorCapital !== null || errorFechas !== null}>
        <FlaskConical aria-hidden="true" className="h-4 w-4" />
        {probar.enCurso ? "Probando…" : "Probar sobre el pasado"}
      </Boton>
    </form>
  );
}

function Resultado({ p, nombre }: { p: ResultadoPrueba; nombre: string }) {
  const [todas, setTodas] = useState(false);
  const vistas = todas ? p.lista_operaciones : p.lista_operaciones.slice(0, 10);
  return (
    <div className="space-y-4">
      <p className="text-[0.9375rem] text-tinta-suave">{periodoPrueba(p)}.</p>
      <CifrasPrueba p={p} tamano="grande" />
      <CurvaBot
        curva={p.curva}
        mantener={p.curva_mantener}
        capital={Number(p.capital)}
        nombre={nombre}
        serie="La estrategia"
        titulo="Lo que habría valido, frente a solo mantener"
        pie="Con comisiones y deslizamiento. «Mantener»: el mismo capital, comprando sus monedas al principio y sin hacer nada más. La línea fina es lo que puso."
        porDias
      />
      <DatosPrueba p={p} />
      {p.avisos.length ? (
        <Aviso tipo="info" titulo="Para leer bien estas cifras" className="text-sm">
          <ul className="list-disc space-y-0.5 pl-4">
            {p.avisos.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Aviso>
      ) : null}
      {p.lista_operaciones.length ? (
        <Desplegable resumen={`Lo que habría hecho: ${p.operaciones} operaciones, con su porqué`}>
          <ol className="divide-y divide-linea">
            {vistas.map((o, i) => (
              <li key={`${o.at}-${i}`} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5 sm:flex-nowrap">
                <span
                  className={clases(
                    "mt-0.5 inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-[0.8125rem] font-semibold",
                    o.lado === "compra" ? "bg-sube-suave text-sube-texto" : "bg-baja-suave text-baja-texto",
                  )}
                >
                  {o.lado === "compra" ? "Compra" : "Venta"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[0.9375rem] leading-relaxed text-tinta">{o.motivo}</p>
                  <p className="cifras text-sm text-tinta-suave">
                    {momento(o.at)} · {formatoImporte(o.importe)} USDC · comisión {formatoImporte(o.comision, { decimales: 2 })} USDC
                  </p>
                </div>
              </li>
            ))}
          </ol>
          {p.lista_operaciones.length > 10 ? (
            <Boton tamano="compacto" variante="fantasma" onClick={() => setTodas((t) => !t)} aria-expanded={todas}>
              {todas ? "Ver solo las últimas" : `Ver las ${p.lista_operaciones.length}`}
            </Boton>
          ) : null}
        </Desplegable>
      ) : null}
    </div>
  );
}

/**
 * La ficha de una estrategia a medida (docs/panel-v4-real.md §2 y §4): que hace (explicacion y
 * reglas en llano), como le habria ido sobre el pasado frente a mantener (con la peor caida al mismo
 * tamano), el aviso de sobreajuste bien a la vista, probar otra vez, sus versiones, desplegarla como
 * bot y, plegado, el editor del JSON para quien quiera tocarla a mano.
 */
export function FichaEstrategia() {
  const params = useSearchParams();
  const id = params.get("id") ?? "";
  const router = useRouter();
  const [version, setVersion] = useState(0);
  const detalle = useConsulta(id ? `medida:${id}:${version}` : null, () => pedir(api.GET("/api/medida/{estrategia_id}", { params: { path: { estrategia_id: id } } })));
  const bots = useConsulta("bots:nombres", () => pedir(api.GET("/api/bots")));
  const nombreBot = (b: string) => bots.datos?.bots.find((x) => x.id === b)?.nombre ?? b;
  const [guardada, setGuardada] = useState<number | null>(null);
  const [borrar, setBorrar] = useState(false);
  const borrado = useAccion(async () => {
    await pedirSinCuerpo(api.DELETE("/api/medida/{estrategia_id}", { params: { path: { estrategia_id: id } } }));
    router.push("/estrategias/medida/");
    return true;
  });

  const volver = (
    <Link href="/estrategias/medida/" className="inline-flex min-h-11 items-center gap-1.5 text-[0.9375rem] font-medium text-marca hover:underline">
      <ArrowLeft aria-hidden="true" className="h-4 w-4" /> A medida
    </Link>
  );

  if (!id) {
    return (
      <EstadoVacio icono={CircleAlert} tono="neutro" titulo="¿Qué estrategia quieres ver?">
        Falta la estrategia en la dirección. <Link href="/estrategias/medida/" className="font-medium text-marca underline">Vuelve a la biblioteca</Link>.
      </EstadoVacio>
    );
  }
  const e = detalle.datos;
  if (!e) {
    return (
      <div className="space-y-6">
        {volver}
        {detalle.error ? <ErrorApiVista error={detalle.error} reintentar={detalle.recargar} /> : <CargandoLento texto="Cargando la estrategia…" lento="Sigue cargando la estrategia…" />}
        {!detalle.error ? <Esqueleto className="h-96" /> : null}
      </div>
    );
  }
  const p = e.ultima_prueba ?? e.pruebas[0] ?? null;
  const recargar = () => setVersion((v) => v + 1);

  return (
    <div className={clases("space-y-12", detalle.cargando && "opacity-90")}>
      <div className="space-y-5">
        {volver}
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-3xl">
            <p className="text-sm font-medium text-tinta-suave">
              Estrategia a medida · {e.monedas.join(", ")} · velas de {nombreIntervalo(e.intervalo)}
            </p>
            <h1 className="titular mt-1 text-[2rem] leading-tight font-semibold text-tinta lg:text-[2.5rem]">{e.nombre}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <ChipEstadoEstrategia estado={e.estado} />
              <ChipAutor autor={e.autor} />
              <span className="text-sm text-tinta-suave">
                Versión {e.version} · cambiada el {momento(e.actualizada)}
              </span>
            </div>
          </div>
          <BotonEnlace href={`/bots/nuevo/?estrategia=${encodeURIComponent(e.id)}`} variante="primario">
            <Bot aria-hidden="true" className="h-5 w-5" />
            Desplegar como bot
          </BotonEnlace>
        </header>
        {params.get("nueva") === "1" && !p ? (
          <Aviso tipo="hecho" vivo>
            Guardada como borrador. Pruébala sobre el pasado (abajo) antes de desplegarla.
          </Aviso>
        ) : null}
        {guardada !== null ? (
          <Aviso tipo="hecho" vivo>
            Guardada la versión {guardada}. Las pruebas de abajo eran de la versión anterior: vuelve a probarla.
          </Aviso>
        ) : null}
        {p?.aviso_sobreajuste ? (
          <Aviso tipo="aviso" titulo={`Cuidado: ${p.versiones_probadas} versiones probadas sobre el mismo pasado`}>
            {p.aviso_sobreajuste}
          </Aviso>
        ) : null}
      </div>

      <Seccion titulo="Qué hace" id="que-hace">
        <Tarjeta className="space-y-4 p-5 sm:p-6">
          <p className="text-[1.0625rem] leading-relaxed text-tinta">{e.explicacion}</p>
          <div>
            <p className="font-semibold text-tinta">Sus reglas, en llano</p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[0.9375rem] leading-relaxed text-tinta marker:text-tinta-suave">
              {e.reglas_en_llano.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
          <p className="text-sm text-tinta-suave">
            Es un formato cerrado que el motor interpreta: no es código, y no puede hacer nada fuera de él.
          </p>
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Sobre el pasado, frente a solo mantener" id="pasado" bajada={p ? "Si hubieras empezado entonces. El pasado no es una promesa." : undefined}>
        {p ? (
          <Resultado p={p} nombre={e.nombre} />
        ) : (
          <EstadoVacio icono={FlaskConical} tono="neutro" titulo="Aún no la has probado">
            Pruébala sobre el pasado antes de desplegarla: verás cuánto habría ganado, cuánto llegó a caer y si lo hizo mejor que solo mantener.
          </EstadoVacio>
        )}
      </Seccion>

      <Seccion titulo="Probarla otra vez" id="probar" bajada="Con otro exchange, otro capital u otras fechas: así se ve cuánto depende de la suerte del periodo.">
        <Tarjeta className="p-5 sm:p-6">
          <Probar estrategia={e} onProbada={recargar} />
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Versiones" id="versiones" bajada={`${e.versiones.length} ${e.versiones.length === 1 ? "versión" : "versiones"}; ${p?.versiones_probadas ?? 0} probadas sobre el pasado.`}>
        <ol className="divide-y divide-linea rounded-tarjeta border border-linea bg-superficie">
          {e.versiones.map((v) => (
            <li key={v.version} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3">
              <span className="titular w-24 shrink-0 font-semibold text-tinta">Versión {v.version}</span>
              <span className="min-w-0 flex-1 text-[0.9375rem] text-tinta">{v.nota}</span>
              <span className="cifras text-sm text-tinta-suave">
                {momento(v.at)} · <span className="font-mono">{v.huella.slice(0, 8)}</span>
              </span>
            </li>
          ))}
        </ol>
        {e.pruebas.length > 1 ? (
          <Desplegable resumen={`Las ${e.pruebas.length} pruebas hechas, la más reciente primero`}>
            <ul className="divide-y divide-linea">
              {e.pruebas.map((x, i) => (
                <li key={i} className="py-2.5 text-[0.9375rem]">
                  <p className="text-tinta">{periodoPrueba(x)}</p>
                  <p className="cifras text-sm text-tinta-suave">
                    Resultado {fraccion(x.ganancia_pct, 1)} (mantener {fraccion(x.mantener_pct, 1)}) · en el peor momento {fraccion(x.peor_caida, 1)} (mantener{" "}
                    {fraccion(x.mantener_peor_caida, 1)}) · {x.operaciones} operaciones
                  </p>
                </li>
              ))}
            </ul>
          </Desplegable>
        ) : null}
      </Seccion>

      <Seccion titulo="Sus bots" id="bots">
        {e.bots.length ? (
          <ul className="flex flex-wrap gap-2">
            {e.bots.map((b) => (
              <li key={b}>
                <BotonEnlace href={`/bots/ficha/?id=${encodeURIComponent(b)}`} tamano="compacto">
                  <Bot aria-hidden="true" className="h-4 w-4" /> {nombreBot(b)}
                </BotonEnlace>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[0.9375rem] text-tinta-suave">Ningún bot la usa. Despliégala en ficticio para verla en vivo; se recomiendan 7 días antes de usar dinero real.</p>
        )}
      </Seccion>

      <Desplegable resumen="Editar a mano (avanzado): la estrategia en su formato JSON">
        <EditorEstrategia
          key={`${e.id}-${e.version}`}
          inicial={JSON.stringify(e.definicion, null, 2)}
          id={e.id}
          version={e.version}
          onGuardada={(d) => {
            setGuardada(d.version);
            recargar();
          }}
        />
      </Desplegable>

      <div className="border-t border-linea pt-6">
        <Boton variante="peligro" tamano="compacto" onClick={() => setBorrar(true)}>
          <Trash2 aria-hidden="true" className="h-4 w-4" /> Borrar la estrategia
        </Boton>
      </div>
      <Hoja
        abierta={borrar}
        onCerrar={() => {
          borrado.limpiar();
          setBorrar(false);
        }}
        cerrable={!borrado.enCurso}
        titulo={`¿Borrar «${e.nombre}»?`}
        bajada="Se borran sus versiones y sus pruebas. No se puede deshacer. Si algún bot la usa, no se puede borrar."
        pie={
          <div className="flex flex-wrap gap-3">
            <Boton variante="real" disabled={borrado.enCurso} onClick={() => void borrado.ejecutar()}>
              {borrado.enCurso ? "Borrando…" : "Sí, borrarla"}
            </Boton>
            <Boton onClick={() => setBorrar(false)} disabled={borrado.enCurso}>
              Cancelar
            </Boton>
          </div>
        }
      >
        {borrado.error ? <ErrorApiVista error={borrado.error} /> : <p className="text-[0.9375rem] text-tinta">Tiene {e.versiones.length} versiones y {e.pruebas.length} pruebas.</p>}
      </Hoja>
    </div>
  );
}
