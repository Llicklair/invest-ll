"use client";

import { Banknote, CircleDashed, CirclePlay, FlaskConical, OctagonX, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { Bots, DetalleBot, EstadoReal, LimitesBot, LimitesBotEntrada, ModoBot, ParadaGeneral, ResumenBot } from "@/api/tipos";
import { useAlmacenVivo } from "@/api/vivo";
import { CampoImporte } from "@/componentes/CampoImporte";
import { ConfirmacionTecleada } from "@/componentes/ConfirmacionTecleada";
import { Hoja } from "@/componentes/Hoja";
import { Medidor } from "@/componentes/Medidor";
import { Aviso, Boton, Chip, ErrorApiVista, clases } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { compararDecimal, formatoCantidad, formatoImporte } from "@/lib/decimal";
import { hora } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";
import { nombreExchange } from "@/lib/nombres";

import { usdc } from "./comun";

// -- Modo y exchange ------------------------------------------------------------------------------

export const NOMBRE_MODO_BOT: Record<ModoBot, string> = { ficticio: "Dinero ficticio", pruebas: "Pruebas", real: "Dinero real" };

/**
 * El modo y el exchange de un bot, inconfundibles: dinero real en rojo con su billete, pruebas en
 * ambar con su matraz, ficticio en gris. Icono + palabra: el color nunca va solo.
 */
export function ChipModo({ modo, exchange, className }: { modo: ModoBot; exchange: string | null; className?: string }) {
  const donde = exchange ? ` · ${nombreExchange(exchange)}` : "";
  if (modo === "real") {
    return (
      <Chip tono="real" className={clases("font-semibold", className)} icono={<Banknote aria-hidden="true" className="h-4 w-4" />}>
        Dinero real{donde}
      </Chip>
    );
  }
  if (modo === "pruebas") {
    return (
      <Chip tono="pruebas" className={className} icono={<FlaskConical aria-hidden="true" className="h-3.5 w-3.5" />}>
        Pruebas{donde}
      </Chip>
    );
  }
  return (
    <Chip tono="neutro" className={className} icono={<CircleDashed aria-hidden="true" className="h-3.5 w-3.5" />}>
      Ficticio{exchange ? donde : ""}
    </Chip>
  );
}

/** La franja de color de arriba de la tarjeta (real: roja; pruebas: ambar; ficticio: ninguna). */
export function bordeModo(modo: ModoBot): string | undefined {
  if (modo === "real") return "border-t-4 border-t-real";
  if (modo === "pruebas") return "border-t-4 border-t-pruebas";
  return undefined;
}

/** ¿Lo ha pausado el sistema (estado desconocido, conciliacion) y no la persona? */
export function pausadoSolo(bot: Pick<ResumenBot, "modo" | "estado" | "aviso">): boolean {
  return bot.modo !== "ficticio" && bot.estado !== "en_marcha" && Boolean(bot.aviso);
}

// -- Limites ----------------------------------------------------------------------------------------

/** Cada limite con su explicacion llana (docs/panel-v4-real.md §3). */
export const EXPLICACION_LIMITE = {
  capital_max: {
    nombre: "Capital máximo",
    texto: "Lo más que este bot puede tener invertido a la vez. Aunque en tu cuenta haya más saldo, no lo toca.",
  },
  orden_max: {
    nombre: "Tamaño máximo por orden",
    texto: "Ninguna compra o venta suya puede pasar de esta cantidad. Si su regla pide más, la orden no sale y lo apunta.",
  },
  perdida_max_pct: {
    nombre: "Pérdida máxima",
    texto: "Si el bot llega a perder este porcentaje de su capital, se para solo.",
  },
  vender_al_parar: {
    nombre: "Al pararse por pérdida, vender todo",
    texto: "Si lo marcas, además de pararse vende lo que tenga y se queda en USDC. Si no, se para y conserva lo que tiene.",
  },
  operaciones_max_dia: {
    nombre: "Operaciones por día",
    texto: "Cuántas compras y ventas puede hacer como mucho en un día. Protege de un bot que se pone a operar sin parar.",
  },
} as const;

const pct = (x: number, decimales = 1) => `${(x * 100).toLocaleString("es-ES", { maximumFractionDigits: decimales })} %`;

/** Lo consumido de cada limite de un bot: barras con su cifra en palabras. */
export function LimitesConsumo({ bot, className }: { bot: Pick<ResumenBot, "limites" | "consumo" | "modo">; className?: string }) {
  const l = bot.limites;
  if (!l) return null;
  const c = bot.consumo;
  const fCapital = c ? Number(c.gastado) / Number(l.capital_max) : null;
  const fPerdida = c ? c.perdida_pct / l.perdida_max_pct : null;
  const fOps = c ? c.operaciones_hoy / l.operaciones_max_dia : null;
  return (
    <div className={clases("space-y-3", className)}>
      <Medidor
        etiqueta="Capital invertido ahora"
        fraccion={fCapital}
        texto={c ? `${formatoImporte(c.gastado, { decimales: 0 })} de ${formatoImporte(l.capital_max, { decimales: 0 })} USDC` : `máx. ${formatoImporte(l.capital_max, { decimales: 0 })} USDC`}
      />
      <Medidor
        etiqueta="Pérdida desde su capital"
        fraccion={fPerdida}
        texto={c ? `${pct(c.perdida_pct)} de un máx. de ${pct(l.perdida_max_pct)}` : `máx. ${pct(l.perdida_max_pct)}`}
        detalle={l.vender_al_parar ? "Al llegar, se para y vende todo lo suyo." : "Al llegar, se para y conserva lo que tiene."}
      />
      <Medidor etiqueta="Operaciones hoy" fraccion={fOps} texto={c ? `${c.operaciones_hoy} de ${l.operaciones_max_dia}` : `máx. ${l.operaciones_max_dia}`} />
      <p className="cifras text-sm text-tinta-suave">Ninguna orden de más de {formatoImporte(l.orden_max, { decimales: 0 })} USDC.</p>
    </div>
  );
}

export interface BorradorLimites {
  capital_max: string;
  orden_max: string;
  perdida: string;
  vender_al_parar: boolean;
  operaciones_max_dia: string;
}

export function borradorDe(l: LimitesBot | null, capital: string): BorradorLimites {
  if (!l) {
    const n = leerImporte(capital);
    const orden = n === null ? "" : formatoImporte(String(Math.max(10, Math.round(Number(n) / 5))), { decimales: 0 });
    return { capital_max: n === null ? "" : formatoImporte(n, { decimales: 0 }), orden_max: orden, perdida: "10", vender_al_parar: true, operaciones_max_dia: "10" };
  }
  return {
    capital_max: formatoCantidad(l.capital_max),
    orden_max: formatoCantidad(l.orden_max),
    perdida: (Math.round(l.perdida_max_pct * 10_000) / 100).toLocaleString("es-ES", { maximumFractionDigits: 2 }),
    vender_al_parar: l.vender_al_parar,
    operaciones_max_dia: String(l.operaciones_max_dia),
  };
}

export type ErroresLimites = Partial<Record<keyof BorradorLimites, string>>;

/** Lee el borrador: los limites para enviar, o lo que falla en cada campo (en llano). */
export function leerLimites(b: BorradorLimites, capitalBot?: string | null): { limites: LimitesBotEntrada | null; errores: ErroresLimites } {
  const errores: ErroresLimites = {};
  const capital = leerImporte(b.capital_max);
  const orden = leerImporte(b.orden_max);
  const perdida = leerImporte(b.perdida);
  const ops = Number(b.operaciones_max_dia.trim());
  if (capital === null || Number(capital) <= 0) errores.capital_max = "Pon cuánto puede tener invertido como mucho: 500 o 1.000.";
  else if (capitalBot && compararDecimal(capital, capitalBot) < 0) errores.capital_max = "No puede ser menor que el capital que le das.";
  if (orden === null || Number(orden) <= 0) errores.orden_max = "Pon el tamaño máximo de cada orden.";
  else if (capital !== null && compararDecimal(orden, capital) > 0) errores.orden_max = "Una orden no puede ser mayor que el capital máximo.";
  if (perdida === null || Number(perdida) <= 0 || Number(perdida) >= 100) errores.perdida = "Un porcentaje mayor que 0 y menor que 100: por ejemplo, 10.";
  if (!Number.isInteger(ops) || ops < 1 || ops > 1000) errores.operaciones_max_dia = "Un número entero entre 1 y 1.000.";
  if (Object.keys(errores).length || capital === null || orden === null || perdida === null) return { limites: null, errores };
  return {
    limites: { capital_max: capital, orden_max: orden, perdida_max_pct: Number(perdida) / 100, vender_al_parar: b.vender_al_parar, operaciones_max_dia: ops },
    errores,
  };
}

/** ¿Algun limite se afloja? (subir capital, orden, perdida u operaciones, o dejar de vender al parar). */
export function seAflojan(viejo: LimitesBot | null, nuevo: LimitesBotEntrada): boolean {
  if (!viejo) return false;
  return (
    compararDecimal(String(nuevo.capital_max), viejo.capital_max) > 0 ||
    compararDecimal(String(nuevo.orden_max), viejo.orden_max) > 0 ||
    nuevo.perdida_max_pct > viejo.perdida_max_pct + 1e-9 ||
    nuevo.operaciones_max_dia > viejo.operaciones_max_dia ||
    (viejo.vender_al_parar && !nuevo.vender_al_parar)
  );
}

/** Los cinco limites, cada uno con su explicacion llana. */
export function CamposLimites({ valor, onCambio, errores, mostrarErrores }: { valor: BorradorLimites; onCambio: (b: BorradorLimites) => void; errores: ErroresLimites; mostrarErrores: boolean }) {
  const base = useId();
  const e = (k: keyof BorradorLimites) => (mostrarErrores ? (errores[k] ?? null) : null);
  const fila = "rounded-tarjeta border border-linea bg-superficie p-4 sm:p-5";
  return (
    <div className="space-y-3">
      <div className={fila}>
        <CampoImporte etiqueta={EXPLICACION_LIMITE.capital_max.nombre} ayuda={EXPLICACION_LIMITE.capital_max.texto} moneda="USDC" valor={valor.capital_max} onCambio={(v) => onCambio({ ...valor, capital_max: v })} error={e("capital_max")} />
      </div>
      <div className={fila}>
        <CampoImporte etiqueta={EXPLICACION_LIMITE.orden_max.nombre} ayuda={EXPLICACION_LIMITE.orden_max.texto} moneda="USDC" valor={valor.orden_max} onCambio={(v) => onCambio({ ...valor, orden_max: v })} error={e("orden_max")} />
      </div>
      <div className={fila}>
        <CampoImporte etiqueta={EXPLICACION_LIMITE.perdida_max_pct.nombre} ayuda={EXPLICACION_LIMITE.perdida_max_pct.texto} moneda="%" valor={valor.perdida} onCambio={(v) => onCambio({ ...valor, perdida: v })} error={e("perdida")} atajos={["5", "10", "20"]} />
        <label htmlFor={`${base}-vender`} className="mt-4 flex min-h-11 cursor-pointer items-start gap-3 rounded-xl bg-superficie-2 px-3 py-2.5">
          <input
            id={`${base}-vender`}
            type="checkbox"
            checked={valor.vender_al_parar}
            onChange={(ev) => onCambio({ ...valor, vender_al_parar: ev.target.checked })}
            className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--marca)]"
          />
          <span>
            <span className="block text-[0.9375rem] font-medium text-tinta">{EXPLICACION_LIMITE.vender_al_parar.nombre}</span>
            <span className="block text-sm text-tinta-suave">{EXPLICACION_LIMITE.vender_al_parar.texto}</span>
          </span>
        </label>
      </div>
      <div className={fila}>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${base}-ops`} className="text-[0.9375rem] font-medium text-tinta">
            {EXPLICACION_LIMITE.operaciones_max_dia.nombre}
          </label>
          <p id={`${base}-ops-ayuda`} className="text-[0.9375rem] text-tinta-suave">
            {EXPLICACION_LIMITE.operaciones_max_dia.texto}
          </p>
          <input
            id={`${base}-ops`}
            inputMode="numeric"
            value={valor.operaciones_max_dia}
            onChange={(ev) => onCambio({ ...valor, operaciones_max_dia: ev.target.value })}
            aria-invalid={e("operaciones_max_dia") ? true : undefined}
            aria-describedby={`${base}-ops-ayuda${e("operaciones_max_dia") ? ` ${base}-ops-error` : ""}`}
            className="cifras min-h-12 w-32 rounded-xl border border-linea-control/70 bg-superficie px-3.5 text-lg text-tinta aria-[invalid=true]:border-real"
          />
          {e("operaciones_max_dia") ? (
            <p id={`${base}-ops-error`} className="text-sm font-medium text-real-tinta">
              {e("operaciones_max_dia")}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Cambiar los limites de un bot: bajarlos es libre; subirlos en uno real pide la confirmacion. */
export function HojaLimites({ bot, abierta, onCerrar, onCambio }: { bot: DetalleBot; abierta: boolean; onCerrar: () => void; onCambio: (d: DetalleBot) => void }) {
  const [borrador, setBorrador] = useState<BorradorLimites>(() => borradorDe(bot.limites, bot.capital));
  const [escrito, setEscrito] = useState("");
  const [intentado, setIntentado] = useState(false);
  const { limites, errores } = leerLimites(borrador);
  const afloja = limites !== null && bot.modo === "real" && seAflojan(bot.limites, limites);
  const esperado = `ACTIVAR ${bot.nombre}`;
  const guardar = useAccion(async () => {
    if (!limites) return null;
    const d = await pedir(
      api.PUT("/api/bots/{bot_id}/limites", { params: { path: { bot_id: bot.id } }, body: { limites, confirmacion: afloja ? escrito : null } }),
    );
    onCambio(d);
    return d;
  });
  const cerrar = () => {
    guardar.limpiar();
    setEscrito("");
    setIntentado(false);
    setBorrador(borradorDe(bot.limites, bot.capital));
    onCerrar();
  };
  const listo = limites !== null && (!afloja || escrito === esperado);
  return (
    <Hoja
      abierta={abierta}
      onCerrar={cerrar}
      cerrable={!guardar.enCurso}
      ancho="ancho"
      titulo={bot.limites ? `Cambiar los límites de «${bot.nombre}»` : `Ponerle límites a «${bot.nombre}»`}
      bajada={bot.modo === "real" ? "Bajarlos es libre y se aplica al momento. Subirlos en un bot con dinero real pide escribir la confirmación." : "Hacen falta para usarlo en pruebas o con dinero real."}
      pie={
        guardar.resultado ? (
          <Boton variante="primario" className="w-full" onClick={cerrar}>
            Entendido
          </Boton>
        ) : (
          <Boton
            variante={afloja ? "real" : "primario"}
            className="w-full"
            disabled={guardar.enCurso || (intentado && !listo)}
            onClick={() => {
              setIntentado(true);
              if (listo) void guardar.ejecutar();
            }}
          >
            {guardar.enCurso ? "Guardando…" : afloja ? "Subir los límites" : "Guardar los límites"}
          </Boton>
        )
      }
    >
      {guardar.resultado ? (
        <Aviso tipo="hecho" vivo titulo="Límites guardados">
          Se aplican desde su próxima orden.
        </Aviso>
      ) : (
        <div className="space-y-5">
          <CamposLimites valor={borrador} onCambio={setBorrador} errores={errores} mostrarErrores={intentado} />
          {afloja ? (
            <div className="space-y-3 rounded-tarjeta border-2 border-real/50 bg-real-suave/40 p-4">
              <p className="text-[0.9375rem] font-semibold text-real-tinta">Estás aflojando un límite de un bot con dinero real.</p>
              <ConfirmacionTecleada
                esperado={esperado}
                valor={escrito}
                onCambio={setEscrito}
                texto
                tono="real"
                estado={escrito.trim() === "" ? { tipo: "vacio" } : escrito === esperado ? { tipo: "puede" } : { tipo: "no", motivo: `Escribe exactamente ${esperado}, con mayúsculas y espacios.` }}
              />
            </div>
          ) : null}
          {guardar.error ? <ErrorApiVista error={guardar.error} prefijo="No se guardaron:" /> : null}
        </div>
      )}
    </Hoja>
  );
}

// -- Activar dinero real ----------------------------------------------------------------------------

/**
 * Pasar un bot a dinero real (docs/panel-v4-real.md §3): que va a pasar, en una frase y sin
 * jerga; sus limites; cuantos dias lleva su estrategia en ficticio; y escribir `ACTIVAR <nombre>`
 * (y `SIN PRUEBA EN FICTICIO` si no llega a 7 dias). El boton solo se habilita con el texto
 * exacto, tecleado (no se puede pegar). Lo que falta (exchange, limites, el exchange en real), se
 * dice antes y el boton no se ofrece.
 */
export function HojaActivarReal({
  bot,
  real,
  abierta,
  onCerrar,
  onActivado,
  onPonerLimites,
}: {
  bot: DetalleBot;
  real: EstadoReal | null;
  abierta: boolean;
  onCerrar: () => void;
  onActivado: (d: DetalleBot) => void;
  onPonerLimites: () => void;
}) {
  const conexiones = useConsulta(abierta ? "conexiones:activar" : null, () => pedir(api.GET("/api/conexiones")));
  const [escrito, setEscrito] = useState("");
  const [sinPrueba, setSinPrueba] = useState("");
  const esperado = `ACTIVAR ${bot.nombre}`;
  const dias = bot.probado_en_ficticio_dias;
  const faltaFicticio = dias === null || dias < 7;
  const exchange = bot.exchange;
  const nombre = nombreExchange(exchange);
  const estadoExchange = exchange ? conexiones.datos?.exchanges.find((x) => x.id === exchange) : undefined;
  const activar = useAccion(async () => {
    const d = await pedir(
      api.POST("/api/bots/{bot_id}/activar-real", { params: { path: { bot_id: bot.id } }, body: { confirmacion: escrito, sin_ficticio: faltaFicticio ? sinPrueba : null } }),
    );
    onActivado(d);
    return d;
  });
  const cerrar = () => {
    setEscrito("");
    setSinPrueba("");
    activar.limpiar();
    onCerrar();
  };

  const bloqueos: { texto: string; accion?: { texto: string; href?: string; onClick?: () => void } }[] = [];
  if (!exchange) bloqueos.push({ texto: "No tiene exchange: es un bot ficticio, con precios de Hyperliquid. Despliega uno en pruebas con su misma estrategia y actívalo cuando esté listo.", accion: { texto: "Desplegar en pruebas", href: `/bots/nuevo/?modo=pruebas${bot.estrategia ? `&estrategia=${encodeURIComponent(bot.estrategia)}` : ""}` } });
  if (!bot.limites) bloqueos.push({ texto: "No tiene límites. Sin límites no se puede usar dinero real.", accion: { texto: "Ponerle límites", onClick: onPonerLimites } });
  if (exchange && estadoExchange && estadoExchange.activo !== "real") bloqueos.push({ texto: `${nombre} no está activado con dinero real.`, accion: { texto: "Ir a Conexiones", href: "/conexiones/" } });
  if (real?.parado_todo) bloqueos.push({ texto: "Está puesto «Parar todo lo real». Quítalo antes (arriba, en Bots)." });

  const coincide = escrito === esperado;
  const coincideSin = !faltaFicticio || sinPrueba === "SIN PRUEBA EN FICTICIO";
  const puede = !bloqueos.length && coincide && coincideSin && !activar.enCurso && !conexiones.cargando;
  const l = bot.limites;
  const idMotivo = useId();

  return (
    <Hoja
      abierta={abierta}
      onCerrar={cerrar}
      cerrable={!activar.enCurso}
      ancho="ancho"
      titulo={`Activar dinero real en «${bot.nombre}»`}
      bajada="A partir de aquí, este bot opera con tu dinero sin pedirte confirmación en cada orden, dentro de sus límites."
    >
      {activar.resultado ? (
        <div className="space-y-6">
          <Aviso tipo="critico" vivo titulo={`«${bot.nombre}» opera ya con dinero real en ${nombre}`}>
            Lo verás en rojo en Bots. Puedes pararlo cuando quieras desde su ficha, o pararlo todo con «Parar todo lo real».
          </Aviso>
          <Boton variante="primario" className="w-full" onClick={cerrar}>
            Entendido
          </Boton>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="rounded-tarjeta border-2 border-real/60 bg-real-suave/50 p-4 sm:p-5">
            <p className="flex items-start gap-3 text-[1.0625rem] leading-relaxed text-tinta">
              <Banknote aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-real-tinta" />
              <span>
                Este bot comprará y venderá <strong className="font-semibold">SOLO</strong>, con <strong className="font-semibold">tu dinero</strong>, en{" "}
                <strong className="font-semibold">{nombre || "su exchange"}</strong>
                {l ? (
                  <>
                    , hasta <strong className="cifras font-semibold">{formatoImporte(l.capital_max, { decimales: 0 })} USDC</strong>. Ninguna orden pasará de{" "}
                    <span className="cifras">{formatoImporte(l.orden_max, { decimales: 0 })} USDC</span>, hará como mucho {l.operaciones_max_dia} operaciones al día y, si pierde
                    un {pct(l.perdida_max_pct)} de su capital, se parará{l.vender_al_parar ? " y venderá todo lo suyo" : ""}.
                  </>
                ) : (
                  "."
                )}
              </span>
            </p>
            <p className="mt-2 pl-8 text-sm text-tinta-suave">
              Sigue «{bot.nombre_plantilla}» con {bot.monedas.join(", ")}.
            </p>
          </div>

          {l ? (
            <dl className="cifras grid gap-x-6 gap-y-2 text-[0.9375rem] sm:grid-cols-[auto_1fr]">
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.capital_max.nombre}</dt>
              <dd className="font-semibold text-tinta">{usdc(l.capital_max, { decimales: 0 })}</dd>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.orden_max.nombre}</dt>
              <dd className="font-semibold text-tinta">{usdc(l.orden_max, { decimales: 0 })}</dd>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.perdida_max_pct.nombre}</dt>
              <dd className="font-semibold text-tinta">
                {pct(l.perdida_max_pct)} <span className="font-normal text-tinta-suave">({l.vender_al_parar ? "se para y vende todo" : "se para y conserva lo suyo"})</span>
              </dd>
              <dt className="text-tinta-suave">{EXPLICACION_LIMITE.operaciones_max_dia.nombre}</dt>
              <dd className="font-semibold text-tinta">{l.operaciones_max_dia}</dd>
              {real?.limite_diario ? (
                <>
                  <dt className="text-tinta-suave">Pérdida máxima diaria de todos los reales</dt>
                  <dd className="font-semibold text-tinta">{usdc(real.limite_diario, { decimales: 0 })}</dd>
                </>
              ) : null}
            </dl>
          ) : null}

          {dias !== null && dias >= 7 ? (
            <Aviso tipo="hecho" titulo={`Su estrategia lleva ${Math.floor(dias)} días en ficticio`}>
              Se recomiendan 7 antes de usar dinero real.
            </Aviso>
          ) : (
            <Aviso tipo="aviso" titulo={dias === null || dias < 1 ? "Su estrategia no ha pasado por ficticio" : `Su estrategia solo lleva ${dias.toLocaleString("es-ES", { maximumFractionDigits: 1 })} días en ficticio`}>
              Se recomiendan 7 días con dinero ficticio para ver cómo se porta en vivo antes de usar dinero real. Puedes saltártelo, pero tendrás que escribirlo, y la
              decisión queda registrada.
            </Aviso>
          )}

          {bloqueos.length ? (
            <div className="space-y-2">
              <p className="font-semibold text-tinta">Antes, falta esto:</p>
              <ul className="space-y-2">
                {bloqueos.map((b) => (
                  <li key={b.texto} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-linea px-4 py-3 text-[0.9375rem] text-tinta">
                    <span className="min-w-0 flex-1">{b.texto}</span>
                    {b.accion?.href ? (
                      <Link href={b.accion.href} className="inline-flex min-h-11 items-center font-semibold text-marca underline underline-offset-4">
                        {b.accion.texto}
                      </Link>
                    ) : b.accion?.onClick ? (
                      <Boton tamano="compacto" onClick={b.accion.onClick}>
                        {b.accion.texto}
                      </Boton>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="space-y-5">
              <ConfirmacionTecleada
                esperado={esperado}
                valor={escrito}
                onCambio={setEscrito}
                texto
                tono="real"
                estado={escrito.trim() === "" ? { tipo: "vacio" } : coincide ? { tipo: "puede" } : { tipo: "no", motivo: `Escribe exactamente ${esperado}, con sus mayúsculas y espacios.` }}
              />
              {faltaFicticio ? (
                <ConfirmacionTecleada
                  esperado="SIN PRUEBA EN FICTICIO"
                  valor={sinPrueba}
                  onCambio={setSinPrueba}
                  mayusculas
                  tono="real"
                  etiqueta="Y, como no ha pasado 7 días en ficticio, escribe también SIN PRUEBA EN FICTICIO"
                  estado={sinPrueba.trim() === "" ? { tipo: "vacio" } : coincideSin ? { tipo: "puede" } : { tipo: "no", motivo: "Escribe exactamente SIN PRUEBA EN FICTICIO, en mayúsculas." }}
                />
              ) : null}
            </div>
          )}
          {conexiones.error ? <ErrorApiVista error={conexiones.error} prefijo="No se pudo comprobar el exchange:" /> : null}
          {activar.error ? <ErrorApiVista error={activar.error} prefijo="No se activó:" /> : null}
          <div className="space-y-2">
            <Boton variante="real" className="w-full" disabled={!puede} aria-describedby={!puede ? idMotivo : undefined} onClick={() => void activar.ejecutar()}>
              <ShieldAlert aria-hidden="true" className="h-5 w-5" />
              {activar.enCurso ? "Activando…" : "Activar dinero real"}
            </Boton>
            {!puede && !activar.enCurso ? (
              <p id={idMotivo} className="text-sm text-tinta-suave">
                {bloqueos.length ? "Primero, lo que falta de arriba." : "El botón se activa cuando lo escrito coincide exactamente."}
              </p>
            ) : null}
          </div>
        </div>
      )}
    </Hoja>
  );
}

// -- Lo real, arriba y siempre a la vista ------------------------------------------------------------

function HojaLimiteDiario({ real, abierta, onCerrar, onCambio }: { real: EstadoReal; abierta: boolean; onCerrar: () => void; onCambio: (r: EstadoReal) => void }) {
  const [valor, setValor] = useState(() => (real.limite_diario ? formatoCantidad(real.limite_diario) : "100"));
  const [escrito, setEscrito] = useState("");
  const limpio = leerImporte(valor);
  const sube = limpio !== null && real.limite_diario !== null && compararDecimal(limpio, real.limite_diario) > 0;
  const guardar = useAccion(async () => {
    if (limpio === null) return null;
    const r = await pedir(api.PUT("/api/bots-real/limite-diario", { body: { limite: limpio, confirmacion: sube ? escrito : null } }));
    onCambio(r);
    return r;
  });
  const cerrar = () => {
    guardar.limpiar();
    setEscrito("");
    setValor(real.limite_diario ? formatoCantidad(real.limite_diario) : "100");
    onCerrar();
  };
  const error = valor.trim() === "" ? null : limpio === null || Number(limpio) <= 0 ? "Escribe una cantidad mayor que cero: 100 o 250,50." : null;
  return (
    <Hoja
      abierta={abierta}
      onCerrar={cerrar}
      cerrable={!guardar.enCurso}
      titulo="Pérdida máxima diaria"
      bajada="Entre todos los bots con dinero real. Si en un día se pierde esto, ninguno envía más órdenes hasta el día siguiente."
      pie={
        guardar.resultado ? (
          <Boton variante="primario" className="w-full" onClick={cerrar}>
            Entendido
          </Boton>
        ) : (
          <Boton
            variante={sube ? "real" : "primario"}
            className="w-full"
            disabled={limpio === null || error !== null || guardar.enCurso || (sube && escrito !== "DINERO REAL")}
            onClick={() => void guardar.ejecutar()}
          >
            {guardar.enCurso ? "Guardando…" : sube ? "Subir la pérdida máxima" : "Guardar"}
          </Boton>
        )
      }
    >
      {guardar.resultado ? (
        <Aviso tipo="hecho" vivo>
          Guardado: como mucho {usdc(guardar.resultado.limite_diario, { decimales: 0 })} de pérdida al día entre todos.
        </Aviso>
      ) : (
        <div className="space-y-5">
          <CampoImporte etiqueta="Como mucho, al día" moneda="USDC" valor={valor} onCambio={setValor} error={error} atajos={["50", "100", "250"]} ayuda={real.limite_diario ? `Ahora: ${usdc(real.limite_diario, { decimales: 0 })}. Bajarlo es libre.` : "Ahora no hay ninguno."} />
          {sube ? (
            <ConfirmacionTecleada
              esperado="DINERO REAL"
              valor={escrito}
              onCambio={setEscrito}
              mayusculas
              tono="real"
              etiqueta="Subirlo deja perder más dinero: escribe DINERO REAL para confirmarlo"
              estado={escrito.trim() === "" ? { tipo: "vacio" } : escrito === "DINERO REAL" ? { tipo: "puede" } : { tipo: "no", motivo: "Escribe exactamente DINERO REAL, en mayúsculas." }}
            />
          ) : null}
          {guardar.error ? <ErrorApiVista error={guardar.error} prefijo="No se guardó:" /> : null}
        </div>
      )}
    </Hoja>
  );
}

/** ¿Hay algo que no sea ficticio? Entonces el panel de lo real va arriba. */
export function hayNoFicticio(datos: Bots | null | undefined): boolean {
  if (!datos) return false;
  return datos.real.bots_reales > 0 || datos.real.parado_todo || datos.bots.some((b) => b.modo !== "ficticio");
}

/**
 * Lo real, siempre a la vista (docs/panel-v4-real.md §3): cuantos bots operan con dinero real, la
 * perdida de hoy frente a la maxima diaria, y el interruptor "Parar todo lo real" -- rojo, grande y
 * SIN confirmacion: parar tiene que ser facil. Al pulsarlo dice que paro, que ordenes cancelo y que
 * no pudo, y como se reanuda. Cuando el panel sale de la vista al hacer scroll, una barra fina con
 * el mismo interruptor queda fija arriba: siempre a la vista, sin tapar media pantalla del movil.
 */
export function PanelReal({ datos, className }: { datos: Bots; className?: string }) {
  const almacen = useAlmacenVivo();
  const real = datos.real;
  const [hojaLimite, setHojaLimite] = useState(false);
  const idDescripcion = useId();
  const idTitulo = useId();
  const panel = useRef<HTMLElement>(null);
  const [fuera, setFuera] = useState(false);
  useEffect(() => {
    const el = panel.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    // Fuera de la vista por ARRIBA (se ha hecho scroll): entonces, la barra fija.
    const obs = new IntersectionObserver(([e]) => setFuera(Boolean(e && !e.isIntersecting && e.boundingClientRect.top < 0)), { threshold: 0 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  const parar = useAccion(async () => {
    const r: ParadaGeneral = await pedir(api.POST("/api/bots-real/parar-todo"));
    // El stream tarda ~2 s: lo parado se ve parado al momento.
    const lista = almacen.leer("bots");
    if (lista) {
      almacen.fijarYa("bots", {
        ...lista,
        real: { ...lista.real, parado_todo: true, en_marcha: 0 },
        bots: lista.bots.map((b) => (r.parados.includes(b.id) ? { ...b, estado: "parado" as const } : b)),
      });
    }
    return r;
  });
  const reanudar = useAccion(async () => {
    const r = await pedir(api.POST("/api/bots-real/reanudar-todo"));
    const lista = almacen.leer("bots");
    if (lista) almacen.fijarYa("bots", { ...lista, real: r });
    parar.limpiar();
    return r;
  });
  const fijarReal = (r: EstadoReal) => {
    const lista = almacen.leer("bots");
    if (lista) almacen.fijarYa("bots", { ...lista, real: r });
  };
  const nombreDe = (id: string) => datos.bots.find((b) => b.id === id)?.nombre ?? id;
  const perdida = Number(real.perdida_hoy);
  const fraccion = real.limite_diario ? perdida / Number(real.limite_diario) : null;
  const sinReales = real.bots_reales === 0;
  const resultado = parar.resultado;

  return (
    <>
      {fuera ? (
        <div
          role="region"
          aria-label="Dinero real, siempre a la vista"
          className="fixed inset-x-0 top-16 z-20 border-b-2 border-real/60 bg-superficie/95 px-4 py-2 shadow-alta backdrop-blur-md lg:top-0 lg:left-64"
        >
          <div className="mx-auto flex max-w-[1120px] items-center gap-3 lg:px-8">
            <p className="flex min-w-0 flex-1 items-center gap-2 text-sm text-tinta">
              <Banknote aria-hidden="true" className="h-4 w-4 shrink-0 text-real-tinta" />
              <span className="truncate">
                <span className="font-semibold text-real-tinta">Dinero real</span>
                {real.parado_todo ? " · todo parado" : ` · ${real.en_marcha} en marcha`}
                {real.parado_todo ? null : (
                  <span className="hidden sm:inline">
                    {` · hoy ${usdc(real.perdida_hoy)}${real.limite_diario ? ` de ${usdc(real.limite_diario, { decimales: 0 })}` : ""}`}
                  </span>
                )}
              </span>
            </p>
            {real.parado_todo ? null : (
              <button
                type="button"
                onClick={() => void parar.ejecutar()}
                disabled={parar.enCurso || sinReales}
                aria-describedby={idDescripcion}
                className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl bg-real px-4 text-[0.9375rem] font-bold text-real-boton-tinta hover:bg-real-hover disabled:cursor-not-allowed disabled:opacity-45"
              >
                <OctagonX aria-hidden="true" className="h-5 w-5" />
                {parar.enCurso ? "Parando…" : "Parar todo lo real"}
              </button>
            )}
          </div>
        </div>
      ) : null}
      <section
        ref={panel}
        aria-labelledby={idTitulo}
        className={clases(
          "rounded-tarjeta border-2 bg-superficie p-4 shadow-alta sm:p-5",
          real.parado_todo ? "border-linea-control/60" : sinReales ? "border-linea" : "border-real/60",
          className,
        )}
      >
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="min-w-0 flex-1 basis-64">
            <h2 id={idTitulo} className="flex items-center gap-2 text-base font-semibold text-real-tinta">
              <Banknote aria-hidden="true" className="h-5 w-5" />
              Dinero real
            </h2>
            <p className="mt-0.5 text-[0.9375rem] text-tinta">
              {real.parado_todo
                ? "Todo lo real está parado."
                : sinReales
                  ? "Ningún bot usa dinero real ahora."
                  : `${real.bots_reales} ${real.bots_reales === 1 ? "bot usa" : "bots usan"} dinero real · ${real.en_marcha} en marcha.`}
            </p>
            <div className="mt-2 max-w-md">
              <Medidor
                etiqueta="Pérdida de hoy, entre todos"
                fraccion={fraccion}
                texto={real.limite_diario ? `${usdc(real.perdida_hoy)} de ${usdc(real.limite_diario, { decimales: 0 })}` : `${usdc(real.perdida_hoy)} · sin máximo diario`}
              />
              <button type="button" onClick={() => setHojaLimite(true)} className="mt-1 inline-flex min-h-11 items-center text-sm font-semibold text-marca underline-offset-4 hover:underline">
                {real.limite_diario ? "Cambiar la pérdida máxima diaria" : "Poner una pérdida máxima diaria"}
              </button>
            </div>
          </div>
          {real.parado_todo ? (
            <Boton onClick={() => void reanudar.ejecutar()} disabled={reanudar.enCurso} aria-describedby={idDescripcion}>
              <CirclePlay aria-hidden="true" className="h-5 w-5" />
              {reanudar.enCurso ? "Quitando…" : "Quitar el interruptor general"}
            </Boton>
          ) : (
            <button
              type="button"
              onClick={() => void parar.ejecutar()}
              disabled={parar.enCurso || sinReales}
              aria-describedby={idDescripcion}
              className="inline-flex min-h-14 w-full items-center justify-center gap-2.5 rounded-xl bg-real px-6 text-[1.0625rem] font-bold text-real-boton-tinta shadow-sm hover:bg-real-hover disabled:cursor-not-allowed disabled:opacity-45 sm:w-auto"
            >
              <OctagonX aria-hidden="true" className="h-6 w-6" />
              {parar.enCurso ? "Parando todo lo real…" : "Parar todo lo real"}
            </button>
          )}
        </div>
        <p id={idDescripcion} className="mt-2 text-sm text-tinta-suave">
          {real.parado_todo
            ? "Quitarlo no reanuda nada: después, cada bot se reanuda uno a uno desde su ficha."
            : sinReales
              ? "Cuando actives algún bot con dinero real, desde aquí los paras todos de golpe."
              : "Para todos los bots con dinero real y cancela sus órdenes abiertas, sin preguntar. Lo que tengan comprado se queda."}
        </p>
        {real.aviso ? (
          <Aviso tipo={real.parado_todo ? "info" : "aviso"} className="mt-3 text-sm">
            {real.aviso}
          </Aviso>
        ) : null}
        {parar.error ? <ErrorApiVista error={parar.error} prefijo="No se pudo parar todo:" className="mt-3" reintentar={() => void parar.ejecutar()} /> : null}
        {reanudar.error ? <ErrorApiVista error={reanudar.error} className="mt-3" /> : null}
      </section>
      {resultado ? (
        <div role="alert" className="rounded-tarjeta border border-linea bg-superficie p-4 sm:p-5">
          <p className="titular text-lg font-semibold text-tinta">Parado todo lo real a las {hora(new Date().toISOString())}</p>
          <ul className="mt-2 space-y-1 text-[0.9375rem] text-tinta">
            <li>
              {resultado.parados.length
                ? `Parados: ${resultado.parados.map(nombreDe).join(", ")}.`
                : "No había ningún bot real en marcha: ninguno que parar."}
            </li>
            <li>
              Órdenes abiertas canceladas: <span className="cifras font-semibold">{resultado.ordenes_canceladas}</span>.
            </li>
          </ul>
          {resultado.avisos.length ? (
            <Aviso tipo="critico" titulo="Lo que no se pudo cancelar o comprobar" className="mt-3 text-sm">
              <ul className="list-disc space-y-0.5 pl-4">
                {resultado.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Aviso>
          ) : null}
          <p className="mt-3 text-sm leading-relaxed text-tinta-suave">
            Para volver a operar: primero quita el interruptor general (arriba) y después reanuda cada bot desde su ficha, cuando quieras. Nada vuelve a operar solo.
          </p>
        </div>
      ) : null}
      <HojaLimiteDiario real={real} abierta={hojaLimite} onCerrar={() => setHojaLimite(false)} onCambio={fijarReal} />
    </>
  );
}

