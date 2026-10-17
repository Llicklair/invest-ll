"use client";

import { ArrowLeft, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useMemo, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { MonedaVivo, NuevoBot, ParametroBot, PlantillaBot } from "@/api/tipos";
import { Asistente } from "@/componentes/Asistente";
import { CambioPct } from "@/componentes/CifraGrande";
import { CampoImporte } from "@/componentes/CampoImporte";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { Aviso, Boton, CargandoLento, Encabezado, ErrorApiVista, Segmentado, Tarjeta, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { leerImporte } from "@/lib/importe";
import { decimalesPrecio, nombreIntervalo, normalizar, precioFijo } from "@/lib/vivo";

import { ChipEvidenciaBot, NotaBots } from "./comun";

const PASOS = ["Plantilla", "Monedas", "Capital", "Ajustes", "Nombre"] as const;

/** Lo que vale un parametro tecleado; `null` si esta bien, el motivo si no. */
function errorParametro(p: ParametroBot, valor: string): string | null {
  if (p.tipo === "opcion" || p.tipo === "intervalo") return p.opciones && !p.opciones.includes(valor) ? `Elige una de las opciones.` : null;
  const limpio = leerImporte(valor);
  if (limpio === null) return "Escribe un número.";
  const n = Number(limpio);
  if (p.tipo === "entero" && !Number.isInteger(n)) return "Tiene que ser un número entero.";
  if (p.minimo !== null && n < Number(p.minimo)) return `Como poco, ${formatoImporte(p.minimo, { decimales: p.tipo === "entero" ? 0 : 2 }).replace(/,00$/, "")}.`;
  if (p.maximo !== null && n > Number(p.maximo)) return `Como mucho, ${formatoImporte(p.maximo, { decimales: p.tipo === "entero" ? 0 : 2 }).replace(/,00$/, "")}.`;
  return null;
}

function textoValor(p: ParametroBot, v: string): string {
  if (p.tipo === "intervalo") return nombreIntervalo(v);
  return v.replace(".", ",");
}

/**
 * Desplegar un bot (docs/panel-v3-vivo.md, seccion 3): plantilla -> monedas -> capital ficticio
 * -> parametros (con su valor por defecto y su explicacion) -> nombre -> Desplegar.
 */
export function Desplegar() {
  const router = useRouter();
  const plantillas = useConsulta("bots:plantillas", () => pedir(api.GET("/api/bots/plantillas")));
  const monedas = useConsulta("vivo:monedas", () => pedir(api.GET("/api/vivo/monedas")));
  const [paso, setPaso] = useState(0);
  const [alcanzado, setAlcanzado] = useState(0);
  const [clave, setClave] = useState<string | null>(null);
  const [elegidas, setElegidas] = useState<string[]>([]);
  const [capital, setCapital] = useState("1.000");
  const [parametros, setParametros] = useState<Record<string, string>>({});
  const [nombre, setNombre] = useState("");
  const [nombreTocado, setNombreTocado] = useState(false);

  const plantilla = plantillas.datos?.plantillas.find((p) => p.clave === clave) ?? null;
  const capitalLimpio = leerImporte(capital);
  const errorCapital = capital.trim() === "" ? "Pon cuánto capital ficticio le das." : capitalLimpio === null ? "Escribe una cantidad: 1.000 o 2500,50." : Number(capitalLimpio) < 10 ? "Pon al menos 10 USDC: con menos no llega ni para las comisiones." : null;
  const valorParam = (p: ParametroBot) => parametros[p.clave] ?? p.defecto;
  const erroresParam = plantilla ? plantilla.parametros.map((p) => errorParametro(p, valorParam(p))) : [];
  const nombrePropuesto = plantilla ? `${plantilla.nombre} · ${elegidas.join(" y ")}` : "";
  const nombreFinal = nombreTocado ? nombre : nombrePropuesto;

  const desplegar = useAccion(async (cuerpo: NuevoBot) => {
    const bot = await pedir(api.POST("/api/bots", { body: cuerpo }));
    router.push(`/bots/ficha/?id=${encodeURIComponent(bot.id)}&nuevo=1`);
    return bot;
  });

  const valido = [clave !== null, elegidas.length > 0, errorCapital === null, erroresParam.every((e) => e === null), nombreFinal.trim().length > 0 && nombreFinal.trim().length <= 60];
  const ir = (n: number) => {
    setPaso(n);
    setAlcanzado((a) => Math.max(a, n));
    window.scrollTo({ top: 0 });
  };

  const elegirPlantilla = (p: PlantillaBot) => {
    setClave(p.clave);
    setParametros({});
    // Las monedas sugeridas que existan, de entrada (una si la plantilla es de una sola).
    const existen = new Set(monedas.datos?.monedas.map((m) => m.coin) ?? []);
    const sugeridas = p.monedas_sugeridas.filter((c) => !existen.size || existen.has(c));
    setElegidas(p.monedas === "una" ? sugeridas.slice(0, 1) : sugeridas);
  };

  return (
    <div className="max-w-3xl space-y-6">
      <Link href="/bots/" className="inline-flex min-h-11 items-center gap-1.5 text-[0.9375rem] font-medium text-marca hover:underline">
        <ArrowLeft aria-hidden="true" className="h-4 w-4" /> Tus bots
      </Link>
      <Encabezado antetitulo="Bots" titulo="Desplegar un bot" bajada="Elige qué hace, con qué monedas y cuánto capital ficticio le das. Puedes pararlo o borrarlo cuando quieras." />
      <NotaBots />

      {plantillas.error ? <ErrorApiVista error={plantillas.error} reintentar={plantillas.recargar} /> : null}
      {!plantillas.datos && !plantillas.error ? <CargandoLento texto="Cargando las plantillas…" lento="Sigue cargando las plantillas…" /> : null}

      {plantillas.datos ? (
        <Asistente pasos={PASOS} actual={paso} alcanzado={alcanzado} onIr={ir} etiqueta="Pasos para desplegar un bot">
          {paso === 0 ? (
            <PasoPlantilla plantillas={plantillas.datos.plantillas} clave={clave} onElegir={elegirPlantilla} />
          ) : paso === 1 && plantilla ? (
            <PasoMonedas plantilla={plantilla} monedas={monedas.datos?.monedas ?? []} cargando={!monedas.datos} elegidas={elegidas} onCambio={setElegidas} />
          ) : paso === 2 ? (
            <CampoImporte
              etiqueta="¿Cuánto capital ficticio le das?"
              grande
              moneda="USDC"
              valor={capital}
              onCambio={setCapital}
              error={capital.trim() ? errorCapital : null}
              atajos={["500", "1000", "2500", "5000"]}
              ayuda="Son USDC ficticios para este bot: lo que gane o pierda se mide contra esta cifra. Nada sale a ningún exchange."
            />
          ) : paso === 3 && plantilla ? (
            <PasoParametros
              plantilla={plantilla}
              valor={valorParam}
              errores={erroresParam}
              onCambio={(k, v) => setParametros((x) => ({ ...x, [k]: v }))}
              onDefecto={(k) => setParametros((x) => Object.fromEntries(Object.entries(x).filter(([c]) => c !== k)))}
            />
          ) : paso === 4 && plantilla ? (
            <PasoNombre
              plantilla={plantilla}
              nombre={nombreFinal}
              onNombre={(v) => {
                setNombre(v);
                setNombreTocado(true);
              }}
              elegidas={elegidas}
              capital={capitalLimpio ?? "0"}
              valorParam={valorParam}
            />
          ) : null}

          {desplegar.error ? <ErrorApiVista error={desplegar.error} className="mt-6" /> : null}

          <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-linea pt-5">
            {paso > 0 ? (
              <Boton onClick={() => ir(paso - 1)} disabled={desplegar.enCurso}>
                Atrás
              </Boton>
            ) : (
              <span />
            )}
            {paso < PASOS.length - 1 ? (
              <Boton variante="primario" disabled={!valido[paso]} onClick={() => ir(paso + 1)}>
                Siguiente: {PASOS[paso + 1]}
              </Boton>
            ) : (
              <Boton
                variante="primario"
                disabled={!valido.every(Boolean) || desplegar.enCurso || !plantilla}
                onClick={() => {
                  if (!plantilla || capitalLimpio === null) return;
                  const params: Record<string, string> = {};
                  for (const p of plantilla.parametros) {
                    const v = valorParam(p);
                    params[p.clave] = p.tipo === "entero" || p.tipo === "decimal" ? (leerImporte(v) ?? v) : v;
                  }
                  void desplegar.ejecutar({ plantilla: plantilla.clave, nombre: nombreFinal.trim(), monedas: elegidas, capital: capitalLimpio, parametros: params });
                }}
              >
                {desplegar.enCurso ? "Desplegando…" : "Desplegar"}
              </Boton>
            )}
          </div>
        </Asistente>
      ) : null}
    </div>
  );
}

function PasoPlantilla({ plantillas, clave, onElegir }: { plantillas: readonly PlantillaBot[]; clave: string | null; onElegir: (p: PlantillaBot) => void }) {
  const nombre = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="titular text-xl leading-snug font-medium text-tinta">¿Qué quieres que haga?</legend>
      <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">Cada plantilla es una regla fija. Ninguna adivina el futuro, y algunas no tienen ninguna prueba: lo dicen.</p>
      <div className="mt-4 grid gap-3">
        {plantillas.map((p) => {
          const elegida = p.clave === clave;
          return (
            <label
              key={p.clave}
              className={clases(
                "block cursor-pointer rounded-tarjeta border px-4 py-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco sm:px-5",
                elegida ? "border-marca bg-marca-suave/60" : "border-linea bg-superficie hover:border-linea-control/60",
              )}
            >
              <input type="radio" name={nombre} className="sr-only" checked={elegida} onChange={() => onElegir(p)} />
              <span className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                <span className="flex min-w-0 items-start gap-3">
                  <span aria-hidden="true" className={clases("mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2", elegida ? "border-marca" : "border-linea-control")}>
                    {elegida ? <span className="h-2.5 w-2.5 rounded-full bg-marca" /> : null}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-lg font-semibold text-tinta">{p.nombre}</span>
                    <span className="block text-[0.9375rem] text-tinta-suave">{p.frase}</span>
                  </span>
                </span>
                <MedidorRiesgo nivel={p.riesgo} texto={p.riesgo_texto} compacto />
              </span>
              <span className="mt-3 flex flex-wrap items-center gap-2 pl-8">
                <ChipEvidenciaBot evidencia={p.evidencia} />
                <span className="text-sm text-tinta-suave">Operaciones: {p.operaciones_esperadas.toLowerCase()}</span>
              </span>
              {elegida ? (
                <span className="mt-3 block space-y-3 pl-8">
                  <span className="block text-sm text-tinta">{p.evidencia.texto}</span>
                  <span className="block">
                    <span className="block text-sm font-semibold text-tinta">Cómo funciona</span>
                    <ol className="mt-1 list-decimal space-y-1 pl-5 text-[0.9375rem] text-tinta">
                      {p.como_funciona.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ol>
                  </span>
                  {p.avisos.length ? (
                    <Aviso tipo="aviso" titulo="Antes de desplegarlo" className="text-sm">
                      <ul className="list-disc space-y-0.5 pl-4">
                        {p.avisos.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </Aviso>
                  ) : null}
                </span>
              ) : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function PasoMonedas({
  plantilla,
  monedas,
  cargando,
  elegidas,
  onCambio,
}: {
  plantilla: PlantillaBot;
  monedas: readonly MonedaVivo[];
  cargando: boolean;
  elegidas: string[];
  onCambio: (c: string[]) => void;
}) {
  const [busqueda, setBusqueda] = useState("");
  const nombre = useId();
  const una = plantilla.monedas === "una";
  const sugeridas = useMemo(() => new Set(plantilla.monedas_sugeridas), [plantilla]);
  const q = normalizar(busqueda);
  const lista = useMemo(() => {
    const filtro = q ? monedas.filter((m) => normalizar(m.nombre).includes(q) || normalizar(m.coin).includes(q)) : monedas;
    return [...filtro].sort((a, b) => Number(sugeridas.has(b.coin)) - Number(sugeridas.has(a.coin)));
  }, [monedas, q, sugeridas]);

  return (
    <fieldset className="min-w-0">
      <legend className="titular text-xl leading-snug font-medium text-tinta">{una ? "¿Con qué moneda?" : "¿Con qué monedas?"}</legend>
      <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">
        {una ? "Esta plantilla opera con una sola moneda." : "Puedes elegir varias: el capital se reparte a partes iguales."} Las sugeridas van primero.
      </p>
      <label className="relative mt-4 block max-w-sm">
        <span className="sr-only">Buscar moneda</span>
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-tinta-suave" />
        <input
          type="search"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Bitcoin, ETH…"
          className="min-h-11 w-full rounded-xl border border-linea-control/70 bg-superficie py-2 pr-3 pl-9 text-base text-tinta placeholder:text-tinta-suave/70"
        />
      </label>
      {cargando ? <p className="mt-4 text-sm text-tinta-suave">Cargando las monedas…</p> : null}
      <div className="mt-3 grid gap-2 sm:max-h-[26rem] sm:grid-cols-2 sm:overflow-y-auto sm:pr-1">
        {lista.map((m) => {
          const elegida = elegidas.includes(m.coin);
          return (
            <label
              key={m.coin}
              className={clases(
                "flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-2.5 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco",
                elegida ? "border-marca bg-marca-suave/60" : "border-linea bg-superficie hover:bg-superficie-2",
              )}
            >
              <input
                type={una ? "radio" : "checkbox"}
                name={nombre}
                checked={elegida}
                onChange={() => onCambio(una ? [m.coin] : elegida ? elegidas.filter((c) => c !== m.coin) : [...elegidas, m.coin])}
                className="h-5 w-5 shrink-0 accent-[var(--marca)]"
              />
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-tinta">
                  {m.nombre} <span className="font-normal text-tinta-suave">{m.coin}</span>
                </span>
                <span className="cifras block text-sm text-tinta-suave">
                  {precioFijo(m.precio, decimalesPrecio(m.precio, m.decimales_cantidad))} USDC · <span className="whitespace-nowrap"><CambioPct pct={m.var_24h} className="text-xs" /> en 24 h</span>
                </span>
              </span>
              {sugeridas.has(m.coin) ? <span className="shrink-0 rounded-full bg-destaque-suave px-2 py-0.5 text-xs font-medium text-destaque-tinta">Sugerida</span> : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function PasoParametros({
  plantilla,
  valor,
  errores,
  onCambio,
  onDefecto,
}: {
  plantilla: PlantillaBot;
  valor: (p: ParametroBot) => string;
  errores: (string | null)[];
  onCambio: (clave: string, v: string) => void;
  onDefecto: (clave: string) => void;
}) {
  const base = useId();
  if (!plantilla.parametros.length) {
    return <p className="text-[0.9375rem] text-tinta">Esta plantilla no tiene nada que ajustar.</p>;
  }
  return (
    <div className="space-y-6">
      <div>
        <h3 className="titular text-xl leading-snug font-medium text-tinta">Ajustes de «{plantilla.nombre}»</h3>
        <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">Ya vienen con su valor por defecto: si no sabes qué tocar, no toques nada.</p>
      </div>
      {plantilla.parametros.map((p, i) => {
        const id = `${base}-${p.clave}`;
        const v = valor(p);
        const error = errores[i] ?? null;
        const cambiado = v !== p.defecto;
        return (
          <Tarjeta key={p.clave} className="p-4 sm:p-5">
            {p.tipo === "opcion" || p.tipo === "intervalo" ? (
              <Segmentado
                etiqueta={p.nombre}
                opciones={(p.opciones ?? []).map((o) => ({ valor: o, texto: p.tipo === "intervalo" ? nombreIntervalo(o) : o }))}
                valor={v}
                onCambio={(o) => onCambio(p.clave, o)}
              />
            ) : (
              <div className="flex flex-col gap-1.5">
                <label htmlFor={id} className="text-[0.9375rem] font-medium text-tinta">
                  {p.nombre}
                </label>
                <input
                  id={id}
                  inputMode={p.tipo === "entero" ? "numeric" : "decimal"}
                  value={v.replace(".", ",")}
                  onChange={(e) => onCambio(p.clave, e.target.value)}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={`${id}-ayuda${error ? ` ${id}-error` : ""}`}
                  className="cifras min-h-12 w-40 rounded-xl border border-linea-control/70 bg-superficie px-3.5 text-lg text-tinta aria-[invalid=true]:border-real"
                />
                {error ? (
                  <p id={`${id}-error`} className="text-sm font-medium text-real-tinta">
                    {error}
                  </p>
                ) : null}
              </div>
            )}
            <p id={`${id}-ayuda`} className="mt-2 text-[0.9375rem] leading-relaxed text-tinta">
              {p.explicacion}
            </p>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-tinta-suave">
              <span>
                Por defecto: {textoValor(p, p.defecto)}
                {p.minimo !== null && p.maximo !== null ? ` · entre ${p.minimo.replace(".", ",")} y ${p.maximo.replace(".", ",")}` : ""}
              </span>
              {cambiado ? (
                <button type="button" onClick={() => onDefecto(p.clave)} className="inline-flex min-h-11 items-center font-medium text-marca underline underline-offset-4">
                  Volver al valor por defecto
                </button>
              ) : null}
            </p>
          </Tarjeta>
        );
      })}
    </div>
  );
}

function PasoNombre({
  plantilla,
  nombre,
  onNombre,
  elegidas,
  capital,
  valorParam,
}: {
  plantilla: PlantillaBot;
  nombre: string;
  onNombre: (v: string) => void;
  elegidas: string[];
  capital: string;
  valorParam: (p: ParametroBot) => string;
}) {
  const id = useId();
  const largo = nombre.trim().length;
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={id} className="titular text-xl leading-snug font-medium text-tinta">
          ¿Cómo lo llamas?
        </label>
        <input
          id={id}
          value={nombre}
          maxLength={60}
          onChange={(e) => onNombre(e.target.value)}
          aria-invalid={largo === 0 ? true : undefined}
          className="min-h-12 w-full max-w-md rounded-xl border border-linea-control/70 bg-superficie px-3.5 text-lg text-tinta aria-[invalid=true]:border-real"
        />
        <p className="text-sm text-tinta-suave">{largo === 0 ? "Ponle un nombre para reconocerlo en la lista." : `${largo} de 60 letras.`}</p>
      </div>
      <Tarjeta className="p-5">
        <h3 className="text-base font-semibold text-tinta">Lo que vas a desplegar</h3>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-[0.9375rem] sm:grid-cols-[auto_1fr]">
          <dt className="text-tinta-suave">Plantilla</dt>
          <dd className="text-tinta">
            {plantilla.nombre} <span className="text-tinta-suave">· riesgo {plantilla.riesgo_texto.toLowerCase()}</span>
          </dd>
          <dt className="text-tinta-suave">Monedas</dt>
          <dd className="text-tinta">{elegidas.join(", ")}</dd>
          <dt className="text-tinta-suave">Capital ficticio</dt>
          <dd className="cifras text-tinta">{formatoImporte(capital)} USDC</dd>
          {plantilla.parametros.map((p) => (
            <div key={p.clave} className="contents">
              <dt className="text-tinta-suave">{p.nombre}</dt>
              <dd className="cifras text-tinta">{textoValor(p, valorParam(p))}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <ChipEvidenciaBot evidencia={plantilla.evidencia} />
          <span className="text-sm text-tinta-suave">{plantilla.evidencia.texto}</span>
        </div>
      </Tarjeta>
    </div>
  );
}
