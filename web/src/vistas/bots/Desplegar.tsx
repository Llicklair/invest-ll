"use client";

import { ArrowLeft, Banknote, CircleDashed, FlaskConical, Lock, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useId, useMemo, useState, type ReactNode } from "react";

import { api, pedir } from "@/api/cliente";
import type { EstadoExchange, MercadoExchange, MonedaVivo, NuevoBot, ParametroBot, PlantillaBot, ResumenEstrategia } from "@/api/tipos";
import { Asistente } from "@/componentes/Asistente";
import { CambioPct } from "@/componentes/CifraGrande";
import { CampoImporte } from "@/componentes/CampoImporte";
import { MedidorRiesgo } from "@/componentes/MedidorRiesgo";
import { Aviso, Boton, CargandoLento, Encabezado, ErrorApiVista, Segmentado, Selector, Tarjeta, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoCantidad, formatoImporte } from "@/lib/decimal";
import { leerImporte } from "@/lib/importe";
import { nombreExchange } from "@/lib/nombres";
import { decimalesPrecio, nombreIntervalo, normalizar, precioFijo } from "@/lib/vivo";
import { ChipEstadoEstrategia, LineaPrueba } from "@/vistas/medida/comun";

import { ChipEvidenciaBot, NotaBots } from "./comun";
import { CamposLimites, EXPLICACION_LIMITE, borradorDe, leerLimites, type BorradorLimites } from "./real";

const PASOS = ["Qué hace", "Dónde", "Monedas", "Capital y límites", "Ajustes", "Nombre"] as const;

type Origen = { tipo: "plantilla"; clave: string } | { tipo: "medida"; id: string };
type ModoNuevo = "ficticio" | "pruebas";

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

/** Los exchanges donde se puede desplegar en pruebas: conectados, con claves de pruebas. */
function enPruebas(e: EstadoExchange): boolean {
  return e.activo !== "sin_conectar" && e.redes.some((r) => r.red === "pruebas" && r.claves_guardadas);
}

/**
 * Desplegar un bot (docs/panel-v3-vivo.md §3; docs/panel-v4-real.md §3): una plantilla o una
 * estrategia a medida -> donde (ficticio o la red de pruebas de un exchange) -> monedas -> capital
 * y limites (obligatorios en pruebas, cada uno con su explicacion llana) -> ajustes -> nombre. El
 * dinero real NO se elige aqui: se activa despues, desde la ficha del bot, tecleando.
 */
export function Desplegar() {
  const router = useRouter();
  const params = useSearchParams();
  const plantillas = useConsulta("bots:plantillas", () => pedir(api.GET("/api/bots/plantillas")));
  const monedas = useConsulta("vivo:monedas", () => pedir(api.GET("/api/vivo/monedas")));
  const medida = useConsulta("medida:lista", () => pedir(api.GET("/api/medida")));
  const conexiones = useConsulta("conexiones:desplegar", () => pedir(api.GET("/api/conexiones")));

  const pedidaEstrategia = params.get("estrategia");
  const pedidoModo: ModoNuevo = params.get("modo") === "pruebas" ? "pruebas" : "ficticio";
  // Al llegar desde una estrategia a medida, ya esta elegido "que hace": se empieza en "Donde".
  const [paso, setPaso] = useState(pedidaEstrategia ? 1 : 0);
  const [alcanzado, setAlcanzado] = useState(pedidaEstrategia ? 1 : 0);
  const [origen, setOrigen] = useState<Origen | null>(pedidaEstrategia ? { tipo: "medida", id: pedidaEstrategia } : null);
  const [modo, setModo] = useState<ModoNuevo>(pedidoModo);
  const [exchange, setExchange] = useState<string | null>(params.get("exchange"));
  const [elegidas, setElegidas] = useState<string[]>([]);
  const [capital, setCapital] = useState("1.000");
  const [conLimites, setConLimites] = useState(false);
  const [limites, setLimites] = useState<BorradorLimites>(() => borradorDe(null, "1000"));
  const [limitesTocados, setLimitesTocados] = useState(false);
  const [intentado, setIntentado] = useState(false);
  const [parametros, setParametros] = useState<Record<string, string>>({});
  const [nombre, setNombre] = useState("");
  const [nombreTocado, setNombreTocado] = useState(false);

  const plantilla = origen?.tipo === "plantilla" ? (plantillas.datos?.plantillas.find((p) => p.clave === origen.clave) ?? null) : null;
  const estrategia = origen?.tipo === "medida" ? (medida.datos?.estrategias.find((e) => e.id === origen.id) ?? null) : null;
  const exchangesPruebas = (conexiones.datos?.exchanges ?? []).filter(enPruebas);
  const mercados = useConsulta(modo === "pruebas" && exchange ? `mercados:${exchange}` : null, () =>
    pedir(api.GET("/api/conexiones/{exchange}/mercados", { params: { path: { exchange: exchange ?? "" }, query: { red: "pruebas" } } })),
  );
  const permitidas = modo === "pruebas" && mercados.datos ? new Set(mercados.datos.mercados.map((m) => m.base)) : null;

  // En pruebas, las elegidas que no tenga ese exchange no cuentan (las sugeridas son de Hyperliquid).
  const monedasBot = estrategia ? estrategia.monedas : permitidas ? elegidas.filter((c) => permitidas.has(c)) : elegidas;
  const capitalLimpio = leerImporte(capital);
  const errorCapital =
    capital.trim() === ""
      ? "Pon cuánto capital le das."
      : capitalLimpio === null
        ? "Escribe una cantidad: 1.000 o 2500,50."
        : Number(capitalLimpio) < 10
          ? "Pon al menos 10 USDC: con menos no llega ni para las comisiones."
          : null;
  // Mientras no se toquen, los limites siguen al capital (capital maximo = capital, orden = un quinto).
  const borrador = limitesTocados ? limites : borradorDe(null, capitalLimpio ?? "0");
  const lecturaLimites = leerLimites(borrador, capitalLimpio);
  const usaLimites = modo === "pruebas" || conLimites;
  const valorParam = (p: ParametroBot) => parametros[p.clave] ?? p.defecto;
  const erroresParam = plantilla ? plantilla.parametros.map((p) => errorParametro(p, valorParam(p))) : [];
  const nombreBase = estrategia ? estrategia.nombre.split(" ").slice(0, 3).join(" ") : plantilla ? plantilla.nombre : "";
  // Sin signos raros: si un dia pasa a dinero real, este nombre se teclea ("ACTIVAR <nombre>").
  const nombrePropuesto = nombreBase ? `${nombreBase} - ${modo === "pruebas" && exchange ? nombreExchange(exchange) : monedasBot.join(" y ")}` : "";
  const nombreFinal = nombreTocado ? nombre : nombrePropuesto;

  const desplegar = useAccion(async (cuerpo: NuevoBot) => {
    const bot = await pedir(api.POST("/api/bots", { body: cuerpo }));
    router.push(`/bots/ficha/?id=${encodeURIComponent(bot.id)}&nuevo=1`);
    return bot;
  });

  const valido = [
    origen !== null && (plantilla !== null || estrategia !== null),
    modo === "ficticio" || (exchange !== null && exchangesPruebas.some((e) => e.id === exchange)),
    monedasBot.length > 0 && (!permitidas || monedasBot.every((c) => permitidas.has(c))),
    errorCapital === null && (!usaLimites || lecturaLimites.limites !== null),
    erroresParam.every((e) => e === null),
    nombreFinal.trim().length > 0 && nombreFinal.trim().length <= 60,
  ];
  const ir = (n: number) => {
    setPaso(n);
    setAlcanzado((a) => Math.max(a, n));
    setIntentado(false);
    window.scrollTo({ top: 0 });
  };
  const siguiente = () => {
    if (paso === 3 && !valido[3]) {
      setIntentado(true);
      return;
    }
    ir(paso + 1);
  };

  const elegirPlantilla = (p: PlantillaBot) => {
    setOrigen({ tipo: "plantilla", clave: p.clave });
    setParametros({});
    // Las monedas sugeridas que existan, de entrada (una si la plantilla es de una sola).
    const existen = new Set(monedas.datos?.monedas.map((m) => m.coin) ?? []);
    const sugeridas = p.monedas_sugeridas.filter((c) => !existen.size || existen.has(c));
    setElegidas(p.monedas === "una" ? sugeridas.slice(0, 1) : sugeridas);
  };
  const elegirEstrategia = (e: ResumenEstrategia) => {
    setOrigen({ tipo: "medida", id: e.id });
    setParametros({});
    setElegidas(e.monedas);
  };

  const enviar = () => {
    if (!origen || capitalLimpio === null) return;
    const params: Record<string, string> = {};
    for (const p of plantilla?.parametros ?? []) {
      const v = valorParam(p);
      params[p.clave] = p.tipo === "entero" || p.tipo === "decimal" ? (leerImporte(v) ?? v) : v;
    }
    void desplegar.ejecutar({
      plantilla: origen.tipo === "medida" ? "medida" : origen.clave,
      estrategia: origen.tipo === "medida" ? origen.id : null,
      nombre: nombreFinal.trim(),
      monedas: monedasBot,
      capital: capitalLimpio,
      parametros: params,
      modo,
      exchange: modo === "pruebas" ? exchange : null,
      limites: usaLimites ? lecturaLimites.limites : null,
    });
  };

  const cargando = !plantillas.datos && !plantillas.error;

  return (
    <div className="max-w-3xl space-y-6">
      <Link href="/bots/" className="inline-flex min-h-11 items-center gap-1.5 text-[0.9375rem] font-medium text-marca hover:underline">
        <ArrowLeft aria-hidden="true" className="h-4 w-4" /> Tus bots
      </Link>
      <Encabezado
        antetitulo="Bots"
        titulo="Desplegar un bot"
        bajada="Elige qué hace, dónde opera, con qué monedas, cuánto le das y sus límites. Puedes pararlo o borrarlo cuando quieras."
      />
      {modo === "pruebas" ? (
        <p className="inline-flex items-start gap-1.5 rounded-xl bg-pruebas-suave px-3 py-2 text-sm font-medium text-pruebas-tinta">
          <FlaskConical aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2} />
          En la red de pruebas{exchange ? ` de ${nombreExchange(exchange)}` : ""}: dinero ficticio del exchange, órdenes de verdad.
        </p>
      ) : (
        <NotaBots />
      )}

      {pedidaEstrategia && medida.datos && !estrategia && origen?.tipo === "medida" ? (
        <Aviso tipo="aviso">No encuentro esa estrategia a medida (puede que la hayas borrado). Elige qué hace en el primer paso.</Aviso>
      ) : null}
      {plantillas.error ? <ErrorApiVista error={plantillas.error} reintentar={plantillas.recargar} /> : null}
      {cargando ? <CargandoLento texto="Cargando las plantillas…" lento="Sigue cargando las plantillas…" /> : null}

      {plantillas.datos ? (
        <Asistente pasos={PASOS} actual={paso} alcanzado={alcanzado} onIr={ir} etiqueta="Pasos para desplegar un bot">
          {paso === 0 ? (
            <PasoQueHace
              plantillas={plantillas.datos.plantillas}
              estrategias={medida.datos?.estrategias ?? []}
              cargandoEstrategias={medida.cargando && !medida.datos}
              origen={origen}
              onPlantilla={elegirPlantilla}
              onEstrategia={elegirEstrategia}
            />
          ) : paso === 1 ? (
            <PasoDonde
              modo={modo}
              onModo={(m) => {
                setModo(m);
                if (m === "pruebas" && !exchange && exchangesPruebas.length === 1) setExchange(exchangesPruebas[0]?.id ?? null);
              }}
              exchange={exchange}
              onExchange={setExchange}
              exchanges={exchangesPruebas}
              cargando={conexiones.cargando && !conexiones.datos}
              error={conexiones.error ? conexiones.error.detalle : null}
            />
          ) : paso === 2 ? (
            estrategia ? (
              <div className="space-y-3">
                <h3 className="titular text-xl leading-snug font-medium text-tinta">Las monedas las pone su estrategia</h3>
                <p className="text-[0.9375rem] text-tinta">
                  «{estrategia.nombre}» opera con <strong className="font-semibold">{estrategia.monedas.join(", ")}</strong>. Para cambiarlas, crea una versión nueva desde su ficha.
                </p>
                {permitidas && !estrategia.monedas.every((c) => permitidas.has(c)) ? (
                  <Aviso tipo="aviso">
                    La red de pruebas de {nombreExchange(exchange)} no tiene {estrategia.monedas.filter((c) => !permitidas.has(c)).join(", ")}: elige otro exchange en el paso anterior.
                  </Aviso>
                ) : null}
              </div>
            ) : plantilla ? (
              <PasoMonedas
                plantilla={plantilla}
                monedas={monedas.datos?.monedas ?? []}
                cargando={modo === "pruebas" ? mercados.cargando && !mercados.datos : !monedas.datos}
                elegidas={monedasBot}
                onCambio={setElegidas}
                mercados={modo === "pruebas" ? (mercados.datos?.mercados ?? null) : null}
                donde={modo === "pruebas" && exchange ? `la red de pruebas de ${nombreExchange(exchange)}` : null}
              />
            ) : null
          ) : paso === 3 ? (
            <div className="space-y-8">
              <CampoImporte
                etiqueta={modo === "pruebas" ? "¿Cuánto capital de pruebas le das?" : "¿Cuánto capital ficticio le das?"}
                grande
                moneda="USDC"
                valor={capital}
                onCambio={setCapital}
                error={capital.trim() ? errorCapital : null}
                atajos={["500", "1000", "2500", "5000"]}
                ayuda={
                  modo === "pruebas"
                    ? `Del saldo ficticio de tu cuenta de pruebas de ${nombreExchange(exchange)}. Lo que gane o pierda se mide contra esta cifra.`
                    : "Son USDC ficticios para este bot: lo que gane o pierda se mide contra esta cifra. Nada sale a ningún exchange."
                }
              />
              <div className="space-y-4">
                <div>
                  <h3 className="titular text-xl leading-snug font-medium text-tinta">Sus límites</h3>
                  <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">
                    {modo === "pruebas"
                      ? "Obligatorios en pruebas: así se ensaya lo mismo que hará con dinero real. Antes de cada orden se comprueba que cabe."
                      : "Con dinero ficticio no hacen falta. Ponérselos ya te ahorra un paso si un día lo pasas a real."}
                  </p>
                </div>
                {modo === "ficticio" ? (
                  <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-linea bg-superficie px-4 py-3">
                    <input type="checkbox" checked={conLimites} onChange={(e) => setConLimites(e.target.checked)} className="h-5 w-5 shrink-0 accent-[var(--marca)]" />
                    <span className="text-[0.9375rem] font-medium text-tinta">Ponerle límites ya</span>
                  </label>
                ) : null}
                {usaLimites ? (
                  <CamposLimites
                    valor={borrador}
                    onCambio={(b) => {
                      setLimites(b);
                      setLimitesTocados(true);
                    }}
                    errores={lecturaLimites.errores}
                    mostrarErrores={intentado || limitesTocados}
                  />
                ) : null}
              </div>
            </div>
          ) : paso === 4 ? (
            plantilla ? (
              <PasoParametros
                plantilla={plantilla}
                valor={valorParam}
                errores={erroresParam}
                onCambio={(k, v) => setParametros((x) => ({ ...x, [k]: v }))}
                onDefecto={(k) => setParametros((x) => Object.fromEntries(Object.entries(x).filter(([c]) => c !== k)))}
              />
            ) : (
              <p className="text-[0.9375rem] text-tinta">
                Una estrategia a medida no tiene ajustes aquí: todo está en su definición. Para cambiarla, crea una versión nueva desde su ficha.
              </p>
            )
          ) : paso === 5 ? (
            <PasoNombre
              plantilla={plantilla}
              estrategia={estrategia}
              nombre={nombreFinal}
              onNombre={(v) => {
                setNombre(v);
                setNombreTocado(true);
              }}
              monedas={monedasBot}
              capital={capitalLimpio ?? "0"}
              valorParam={valorParam}
              modo={modo}
              exchange={exchange}
              limites={usaLimites ? lecturaLimites.limites : null}
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
              <Boton variante="primario" disabled={paso === 3 ? errorCapital !== null : !valido[paso]} onClick={siguiente}>
                Siguiente: {PASOS[paso + 1]}
              </Boton>
            ) : (
              <Boton variante="primario" disabled={!valido.every(Boolean) || desplegar.enCurso || !origen} onClick={enviar}>
                {desplegar.enCurso ? "Desplegando…" : modo === "pruebas" ? "Desplegar en pruebas" : "Desplegar"}
              </Boton>
            )}
          </div>
        </Asistente>
      ) : null}
    </div>
  );
}

function PasoQueHace({
  plantillas,
  estrategias,
  cargandoEstrategias,
  origen,
  onPlantilla,
  onEstrategia,
}: {
  plantillas: readonly PlantillaBot[];
  estrategias: readonly ResumenEstrategia[];
  cargandoEstrategias: boolean;
  origen: Origen | null;
  onPlantilla: (p: PlantillaBot) => void;
  onEstrategia: (e: ResumenEstrategia) => void;
}) {
  const nombre = useId();
  const tarjeta = (elegida: boolean) =>
    clases(
      "block cursor-pointer rounded-tarjeta border px-4 py-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco sm:px-5",
      elegida ? "border-marca bg-marca-suave/60" : "border-linea bg-superficie hover:border-linea-control/60",
    );
  const punto = (elegida: boolean) => (
    <span aria-hidden="true" className={clases("mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2", elegida ? "border-marca" : "border-linea-control")}>
      {elegida ? <span className="h-2.5 w-2.5 rounded-full bg-marca" /> : null}
    </span>
  );
  return (
    <fieldset className="min-w-0">
      <legend className="titular text-xl leading-snug font-medium text-tinta">¿Qué quieres que haga?</legend>
      <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">Una plantilla (una regla fija) o una de tus estrategias a medida. Ninguna adivina el futuro, y las que no tienen pruebas lo dicen.</p>

      <p className="mt-6 text-sm font-semibold tracking-wide text-tinta-suave uppercase">Plantillas</p>
      <div className="mt-2 grid gap-3">
        {plantillas.map((p) => {
          const elegida = origen?.tipo === "plantilla" && origen.clave === p.clave;
          return (
            <label key={p.clave} className={tarjeta(elegida)}>
              <input type="radio" name={nombre} className="sr-only" checked={elegida} onChange={() => onPlantilla(p)} />
              <span className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                <span className="flex min-w-0 items-start gap-3">
                  {punto(elegida)}
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

      <p className="mt-8 text-sm font-semibold tracking-wide text-tinta-suave uppercase">Tus estrategias a medida</p>
      {cargandoEstrategias ? <p className="mt-2 text-sm text-tinta-suave">Cargando tus estrategias…</p> : null}
      {!cargandoEstrategias && !estrategias.length ? (
        <p className="mt-2 text-[0.9375rem] text-tinta-suave">
          Aún no tienes ninguna.{" "}
          <Link href="/estrategias/medida/disenar/" className="font-semibold text-marca underline underline-offset-4">
            Diséñala con Claude
          </Link>
          .
        </p>
      ) : null}
      <div className="mt-2 grid gap-3">
        {estrategias.map((e) => {
          const elegida = origen?.tipo === "medida" && origen.id === e.id;
          return (
            <label key={e.id} className={tarjeta(elegida)}>
              <input type="radio" name={nombre} className="sr-only" checked={elegida} onChange={() => onEstrategia(e)} />
              <span className="flex min-w-0 items-start gap-3">
                {punto(elegida)}
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-semibold text-tinta">{e.nombre}</span>
                    <ChipEstadoEstrategia estado={e.estado} />
                  </span>
                  <span className="mt-0.5 block text-sm text-tinta-suave">
                    <Sparkles aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />
                    Versión {e.version} · {e.monedas.join(", ")} · velas de {nombreIntervalo(e.intervalo)}
                  </span>
                  <span className="mt-2 block">
                    <LineaPrueba p={e.ultima_prueba} />
                  </span>
                  {elegida && e.estado === "borrador" ? (
                    <span className="mt-2 block">
                      <Aviso tipo="aviso" className="text-sm">
                        Es un borrador: aún no se ha probado sobre el pasado. Mejor pruébala antes desde su ficha.
                      </Aviso>
                    </span>
                  ) : null}
                </span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function PasoDonde({
  modo,
  onModo,
  exchange,
  onExchange,
  exchanges,
  cargando,
  error,
}: {
  modo: ModoNuevo;
  onModo: (m: ModoNuevo) => void;
  exchange: string | null;
  onExchange: (e: string | null) => void;
  exchanges: readonly EstadoExchange[];
  cargando: boolean;
  error: string | null;
}) {
  const nombre = useId();
  const opcion = (m: ModoNuevo, Icono: typeof FlaskConical, titulo: string, texto: string, tono: string) => {
    const elegida = modo === m;
    return (
      <label
        className={clases(
          "flex cursor-pointer items-start gap-3 rounded-tarjeta border px-4 py-4 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco sm:px-5",
          elegida ? "border-marca bg-marca-suave/60" : "border-linea bg-superficie hover:border-linea-control/60",
        )}
      >
        <input type="radio" name={nombre} className="sr-only" checked={elegida} onChange={() => onModo(m)} />
        <span aria-hidden="true" className={clases("flex h-10 w-10 shrink-0 items-center justify-center rounded-full", tono)}>
          <Icono className="h-5 w-5" />
        </span>
        <span className="min-w-0">
          <span className="block text-lg font-semibold text-tinta">{titulo}</span>
          <span className="block text-[0.9375rem] text-tinta-suave">{texto}</span>
        </span>
      </label>
    );
  };
  return (
    <div className="space-y-6">
      <fieldset className="min-w-0">
        <legend className="titular text-xl leading-snug font-medium text-tinta">¿Dónde opera?</legend>
        <div className="mt-4 grid gap-3">
          {opcion("ficticio", CircleDashed, "Con dinero ficticio", "Precios en vivo de Hyperliquid y una cuenta de mentira. Nada sale a ningún exchange.", "bg-superficie-2 text-tinta-suave")}
          {opcion("pruebas", FlaskConical, "En la red de pruebas de un exchange", "Dinero ficticio del propio exchange, pero órdenes de verdad: se ensaya todo lo que hará con dinero real. Límites obligatorios.", "bg-pruebas-suave text-pruebas-tinta")}
          <div className="flex items-start gap-3 rounded-tarjeta border border-dashed border-linea-control/60 px-4 py-4 sm:px-5" aria-disabled="true">
            <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-real-suave text-real-tinta">
              <Banknote className="h-5 w-5" />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-2 text-lg font-semibold text-tinta">
                Con dinero real <Lock aria-hidden="true" className="h-4 w-4 text-tinta-suave" />
              </span>
              <span className="block text-[0.9375rem] text-tinta-suave">
                No se elige al crear. Despliégalo en pruebas o en ficticio y, cuando te convenza, actívalo desde su ficha, con sus límites y escribiendo «ACTIVAR» y su nombre.
              </span>
            </span>
          </div>
        </div>
      </fieldset>
      {modo === "pruebas" ? (
        <div className="space-y-2">
          {cargando ? <p className="text-sm text-tinta-suave">Leyendo tus exchanges…</p> : null}
          {error ? <Aviso tipo="critico">{error}</Aviso> : null}
          {!cargando && !exchanges.length ? (
            <Aviso tipo="aviso" titulo="Ningún exchange está conectado en pruebas">
              Conecta uno en{" "}
              <Link href="/ajustes/#conexion" className="font-semibold underline underline-offset-4">
                Ajustes → Conexiones
              </Link>{" "}
              (guarda y prueba sus claves de pruebas) y vuelve.
            </Aviso>
          ) : null}
          {exchanges.length ? (
            <Selector etiqueta="Exchange" value={exchange ?? ""} onChange={(e) => onExchange(e.target.value || null)} ayuda="Solo los que tienen la red de pruebas conectada.">
              <option value="">Elige uno…</option>
              {exchanges.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nombre}
                </option>
              ))}
            </Selector>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PasoMonedas({
  plantilla,
  monedas,
  cargando,
  elegidas,
  onCambio,
  mercados,
  donde,
}: {
  plantilla: PlantillaBot;
  monedas: readonly MonedaVivo[];
  cargando: boolean;
  elegidas: string[];
  onCambio: (c: string[]) => void;
  /** En pruebas, los pares de contado de ese exchange en su red de pruebas (no los de Hyperliquid). */
  mercados: readonly MercadoExchange[] | null;
  donde: string | null;
}) {
  const [busqueda, setBusqueda] = useState("");
  const nombre = useId();
  const una = plantilla.monedas === "una";
  const sugeridas = useMemo(() => new Set(plantilla.monedas_sugeridas), [plantilla]);
  const q = normalizar(busqueda);
  const lista = useMemo(() => {
    const base: { coin: string; nombre: string; detalle: ReactNode }[] = mercados
      ? mercados.map((mk) => ({
          coin: mk.base,
          nombre: mk.nombre,
          detalle: `${mk.par}${mk.minimo_importe ? ` · mínimo ${formatoCantidad(mk.minimo_importe)} ${mk.cotizada} por orden` : ""}`,
        }))
      : monedas.map((m) => ({
          coin: m.coin,
          nombre: m.nombre,
          detalle: (
            <>
              {precioFijo(m.precio, decimalesPrecio(m.precio, m.decimales_cantidad))} USDC · <span className="whitespace-nowrap"><CambioPct pct={m.var_24h} className="text-xs" /> en 24 h</span>
            </>
          ),
        }));
    const filtro = q ? base.filter((m) => normalizar(m.nombre).includes(q) || normalizar(m.coin).includes(q)) : base;
    return [...filtro].sort((a, b) => Number(sugeridas.has(b.coin)) - Number(sugeridas.has(a.coin)));
  }, [monedas, q, sugeridas, mercados]);

  return (
    <fieldset className="min-w-0">
      <legend className="titular text-xl leading-snug font-medium text-tinta">{una ? "¿Con qué moneda?" : "¿Con qué monedas?"}</legend>
      <p className="mt-1.5 text-[0.9375rem] text-tinta-suave">
        {una ? "Esta plantilla opera con una sola moneda." : "Puedes elegir varias: el capital se reparte a partes iguales."} Las sugeridas van primero.
        {donde ? ` Solo las que hay en ${donde}.` : ""}
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
      {!cargando && mercados && !mercados.length ? <p className="mt-4 text-sm text-tinta-suave">Su red de pruebas no tiene ningún par de contado ahora.</p> : null}
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
                <span className="cifras block text-sm text-tinta-suave">{m.detalle}</span>
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
  estrategia,
  nombre,
  onNombre,
  monedas,
  capital,
  valorParam,
  modo,
  exchange,
  limites,
}: {
  plantilla: PlantillaBot | null;
  estrategia: ResumenEstrategia | null;
  nombre: string;
  onNombre: (v: string) => void;
  monedas: string[];
  capital: string;
  valorParam: (p: ParametroBot) => string;
  modo: ModoNuevo;
  exchange: string | null;
  limites: { capital_max: string | number; orden_max: string | number; perdida_max_pct: number; vender_al_parar: boolean; operaciones_max_dia: number } | null;
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
          aria-describedby={`${id}-ayuda`}
          className="min-h-12 w-full max-w-md rounded-xl border border-linea-control/70 bg-superficie px-3.5 text-lg text-tinta aria-[invalid=true]:border-real"
        />
        <p id={`${id}-ayuda`} className="text-sm text-tinta-suave">
          {largo === 0 ? "Ponle un nombre para reconocerlo en la lista." : `${largo} de 60 letras. Si un día lo pasas a dinero real, tendrás que escribir «ACTIVAR» y este nombre.`}
        </p>
      </div>
      <Tarjeta className="p-5">
        <h3 className="text-base font-semibold text-tinta">Lo que vas a desplegar</h3>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-[0.9375rem] sm:grid-cols-[auto_1fr]">
          <dt className="text-tinta-suave">Qué hace</dt>
          <dd className="text-tinta">
            {estrategia ? `Estrategia a medida: ${estrategia.nombre} (versión ${estrategia.version})` : plantilla ? `${plantilla.nombre} · riesgo ${plantilla.riesgo_texto.toLowerCase()}` : "—"}
          </dd>
          <dt className="text-tinta-suave">Dónde</dt>
          <dd className="text-tinta">{modo === "pruebas" ? `Red de pruebas de ${nombreExchange(exchange)} (dinero ficticio, órdenes de verdad)` : "Dinero ficticio, precios de Hyperliquid"}</dd>
          <dt className="text-tinta-suave">Monedas</dt>
          <dd className="text-tinta">{monedas.join(", ")}</dd>
          <dt className="text-tinta-suave">Capital</dt>
          <dd className="cifras text-tinta">{formatoImporte(capital)} USDC</dd>
          {limites ? (
            <>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.capital_max.nombre}</dt>
              <dd className="cifras text-tinta">{formatoImporte(String(limites.capital_max), { decimales: 0 })} USDC</dd>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.orden_max.nombre}</dt>
              <dd className="cifras text-tinta">{formatoImporte(String(limites.orden_max), { decimales: 0 })} USDC</dd>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.perdida_max_pct.nombre}</dt>
              <dd className="cifras text-tinta">
                {(limites.perdida_max_pct * 100).toLocaleString("es-ES", { maximumFractionDigits: 2 })} % {limites.vender_al_parar ? "(y vende todo)" : "(conserva lo suyo)"}
              </dd>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.operaciones_max_dia.nombre}</dt>
              <dd className="cifras text-tinta">{limites.operaciones_max_dia}</dd>
            </>
          ) : (
            <>
              <dt className="text-tinta-suave">Límites</dt>
              <dd className="text-tinta">Sin límites (dinero ficticio)</dd>
            </>
          )}
          {plantilla?.parametros.map((p) => (
            <div key={p.clave} className="contents">
              <dt className="text-tinta-suave">{p.nombre}</dt>
              <dd className="cifras text-tinta">{textoValor(p, valorParam(p))}</dd>
            </div>
          ))}
        </dl>
        {plantilla ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <ChipEvidenciaBot evidencia={plantilla.evidencia} />
            <span className="text-sm text-tinta-suave">{plantilla.evidencia.texto}</span>
          </div>
        ) : estrategia ? (
          <div className="mt-4">
            <LineaPrueba p={estrategia.ultima_prueba} />
          </div>
        ) : null}
      </Tarjeta>
    </div>
  );
}
