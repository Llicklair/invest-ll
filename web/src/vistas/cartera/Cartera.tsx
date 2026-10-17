"use client";

import { ArrowDownLeft, ArrowUpRight, Banknote, Landmark, NotebookPen, Plus, Sprout } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";

import { api, pedir } from "@/api/cliente";
import type {
  Cartera as DatosCartera,
  Movimiento,
  NuevoMovimiento,
  PosicionAbierta,
  PosicionRetirada,
  TipoMovimiento,
} from "@/api/tipos";
import { BuscadorActivo, type OpcionActivo } from "@/componentes/BuscadorActivo";
import { EstadoVacio } from "@/componentes/EstadoVacio";
import { Hoja } from "@/componentes/Hoja";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  Boton,
  BotonEnlace,
  CampoTexto,
  Chip,
  Codigo,
  Desplegable,
  Encabezado,
  ErrorApiVista,
  Esqueleto,
  Nota,
  Segmentado,
  Tarjeta,
  TextoApi,
  clases,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useModo } from "@/contexto/modo";
import { useAccion, useConsulta } from "@/lib/consulta";
import { compararDecimal, formatoCantidad, signoDecimal } from "@/lib/decimal";
import { enMoneda, fecha, fechaCorta, hoyLocal, mesYAnioCorto, momento, simboloMoneda } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";
import { base, enLaMoneda, unidad } from "@/lib/nombres";

import { Proteccion } from "./Proteccion";

function cuanto(p: PosicionAbierta): string {
  const u = unidad(p.activo);
  return `${formatoCantidad(p.cantidad)} ${u === "participaciones" ? (p.cantidad === "1" ? "participación" : "participaciones") : u}`;
}

/**
 * Una fila de "Lo que tienes". Si la posicion es de referencia (una compra del broker hecha desde
 * el plan), `cantidad` y `coste_medio` son del fondo de EE.UU. con que se calcula, no tuyos: se
 * ensenan importes ("pusiste 3.536 €"), nunca "4,63 participaciones a 763 €".
 */
function FilaTienes({ p }: { p: PosicionAbierta }) {
  const s = p.pnl_no_realizado === null ? null : signoDecimal(p.pnl_no_realizado);
  return (
    <li className="grid gap-1 py-4 sm:grid-cols-[1fr_auto] sm:items-baseline sm:gap-6">
      <div className="min-w-0">
        <p className="font-semibold text-tinta">{p.nombre}</p>
        <p className="cifras text-[0.9375rem] text-tinta-suave">
          {p.es_referencia ? (
            <>Pusiste {enMoneda(p.invertido, p.moneda)} en tu bróker</>
          ) : (
            <>
              Tienes {cuanto(p)} · pusiste {enMoneda(p.invertido, p.moneda)}
            </>
          )}
        </p>
      </div>
      <div className="sm:text-right">
        <p className="cifras text-lg font-semibold text-tinta">
          {p.valor === null ? "Sin precio" : `Valen ${p.es_referencia ? "unos " : ""}${enMoneda(p.valor, p.moneda)}`}
        </p>
        {p.pnl_no_realizado !== null ? (
          <p className={clases("cifras text-[0.9375rem]", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "text-tinta-suave")}>
            {s === 1 ? "Ganas " : s === -1 ? "Pierdes " : ""}
            {enMoneda(p.pnl_no_realizado, p.moneda, { conSigno: true })} si vendieras hoy
          </p>
        ) : null}
        <p className="text-sm text-tinta-suave">
          {!p.precio_fecha
            ? "Sin precio descargado: no se puede saber cuánto vale"
            : p.es_referencia
              ? `Calculado con el fondo de EE.UU. que sigue, al cierre del ${fechaCorta(p.precio_fecha)}`
              : `Precio del cierre del ${fechaCorta(p.precio_fecha)}`}
        </p>
      </div>
    </li>
  );
}

function FilaVendido({ r }: { r: PosicionRetirada }) {
  const s = signoDecimal(r.pnl_realizado);
  const palabra = s === 1 ? "Ganaste" : s === -1 ? "Perdiste" : "Ni ganaste ni perdiste";
  const importe = s === -1 ? r.pnl_realizado.replace(/^-/, "") : r.pnl_realizado;
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3">
      <p className="min-w-0 text-[0.9375rem] text-tinta">
        <span className={clases("font-semibold", s === 1 ? "text-sube-texto" : s === -1 ? "text-baja-texto" : "")}>
          {palabra}
          {s !== 0 ? <span className="cifras"> {enMoneda(importe, r.moneda)}</span> : null}
        </span>{" "}
        con {r.nombre}
      </p>
      <p className="shrink-0 text-sm text-tinta-suave">
        {mesYAnioCorto(r.abierta)} – {mesYAnioCorto(r.retirada)}
      </p>
    </li>
  );
}

const ICONO_MOVIMIENTO = { compra: ArrowDownLeft, venta: ArrowUpRight, ingreso: Banknote, retirada: Banknote } as const;
const TEXTO_MOVIMIENTO = { compra: "Compra", venta: "Venta", ingreso: "Ingreso", retirada: "Retirada" } as const;

/** El detalle de un movimiento, en llano. Los de referencia cuentan lo que de verdad compraste (`nota`). */
function detalleMovimiento(m: Movimiento): string | null {
  if (m.tipo !== "compra" && m.tipo !== "venta") return m.nota;
  if (m.es_referencia) return m.nota ?? `${m.tipo === "venta" ? "Venta" : "Compra"} de tu bróker anotada desde tu plan.`;
  const cuantas = m.simbolo?.includes("/") ? base(m.simbolo) : formatoCantidad(m.cantidad) === "1" ? "participación" : "participaciones";
  return `${formatoCantidad(m.cantidad)} ${cuantas} a ${enMoneda(m.precio, m.moneda)}`;
}

function FilaMovimiento({ m }: { m: Movimiento }) {
  const Icono = m.es_referencia ? Landmark : ICONO_MOVIMIENTO[m.tipo];
  const conActivo = m.tipo === "compra" || m.tipo === "venta";
  // La `nota` de la API es una frase con su punto: aqui va entre " · ", sin el.
  const detalle = detalleMovimiento(m)?.replace(/\.\s*$/, "") ?? null;
  const origen = m.origen === "panel" ? "desde el panel" : m.origen === "plan" ? "de tu plan" : null;
  return (
    <li className="flex items-start gap-3 py-3 sm:gap-4">
      <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-superficie-2 text-tinta-suave" aria-hidden="true">
        <Icono className="h-4 w-4" strokeWidth={1.75} />
      </span>
      {/* En el movil el detalle se parte en lineas: cortarlo con "…" escondia justo la cifra. */}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="min-w-0 text-[0.9375rem] text-tinta">
            <span className="font-semibold">{TEXTO_MOVIMIENTO[m.tipo]}</span>
            {conActivo && m.activo ? ` de ${m.activo}` : ""}
          </p>
          <p className="cifras shrink-0 text-right font-semibold text-tinta">{enMoneda(m.importe, m.moneda)}</p>
        </div>
        <p className="cifras text-sm text-tinta-suave [overflow-wrap:anywhere]">
          {fecha(m.fecha)}
          {detalle ? ` · ${detalle}` : ""}
          {origen ? ` · ${origen}` : ""}
        </p>
      </div>
    </li>
  );
}

/** Anotar un movimiento: escribe en tu registro lo que ya hiciste. NO envia ninguna orden. */
function HojaAnotar({ abierta, onCerrar, alAnotar }: { abierta: boolean; onCerrar: () => void; alAnotar: () => void }) {
  return (
    <Hoja abierta={abierta} onCerrar={onCerrar} titulo="Anotar un movimiento" bajada="Para lo que hiciste fuera del panel. Esto NO envía nada: solo lo apunta.">
      {abierta ? <FormularioAnotar alAnotar={alAnotar} onCerrar={onCerrar} /> : null}
    </Hoja>
  );
}

const TIPOS: readonly { valor: TipoMovimiento; texto: string }[] = [
  { valor: "compra", texto: "Compré" },
  { valor: "venta", texto: "Vendí" },
  { valor: "ingreso", texto: "Ingresé" },
  { valor: "retirada", texto: "Retiré" },
];

/**
 * Los activos que el panel conoce (`GET /api/estado`), con el nombre llano y la moneda de su
 * precio que trae cada uno (contrato v2.1: `Activo.nombre` y `Activo.moneda`).
 */
function useActivosConocidos(): OpcionActivo[] {
  const { estado } = useEstado();
  return useMemo(() => {
    const vistos = new Set<string>();
    const lista: OpcionActivo[] = [];
    for (const a of estado?.activos ?? []) {
      if (vistos.has(a.symbol)) continue;
      vistos.add(a.symbol);
      lista.push({ simbolo: a.symbol, nombre: a.nombre, moneda: a.moneda, cripto: a.is_crypto });
    }
    return lista.sort((x, y) => x.nombre.localeCompare(y.nombre, "es"));
  }, [estado]);
}

function FormularioAnotar({ alAnotar, onCerrar }: { alAnotar: () => void; onCerrar: () => void }) {
  const { versionDatos } = useEstado();
  const [tipo, setTipo] = useState<TipoMovimiento>("compra");
  const [activo, setActivo] = useState<OpcionActivo | null>(null);
  const [dia, setDia] = useState(hoyLocal);
  const [cantidad, setCantidad] = useState("");
  const [precio, setPrecio] = useState("");
  const [comision, setComision] = useState("0");
  const conActivo = tipo === "compra" || tipo === "venta";
  const conocidos = useActivosConocidos();
  // Si es un fondo de tu plan que hoy toca comprar o vender, se anota desde "Ya lo he comprado" o
  // "Ya lo he vendido": asi cuenta en el plan y se guarda con lo que de verdad pagaste o cobraste.
  const hoy = useConsulta(conActivo ? `hoy:${versionDatos}` : null, () => pedir(api.GET("/api/plan/hoy")));
  const lado = tipo === "compra" ? "buy" : "sell";
  const delPlan =
    conActivo && activo
      ? (hoy.datos?.acciones.find((a) => a.donde === "broker" && a.lado === lado && (a.referencia ?? a.simbolo) === activo.simbolo) ?? null)
      : null;
  const boton = lado === "sell" ? "«Ya lo he vendido»" : "«Ya lo he comprado»";
  const moneda = conActivo ? (activo?.moneda ?? "") : "EUR";
  const sufijo = moneda ? simboloMoneda(moneda) : undefined;

  const registrar = useAccion(async (movimiento: NuevoMovimiento) => {
    const r = await pedir(api.POST("/api/cartera/movimientos", { body: movimiento }));
    alAnotar();
    return r;
  });

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (conActivo && !activo) return;
    void registrar.ejecutar({
      tipo,
      fecha: dia,
      cantidad: leerImporte(cantidad) ?? cantidad.trim(),
      comision: leerImporte(comision === "" ? "0" : comision) ?? comision.trim(),
      ...(conActivo && activo ? { simbolo: activo.simbolo, precio: leerImporte(precio) ?? precio.trim() } : {}),
    });
  };

  if (registrar.resultado) {
    return (
      <div className="space-y-6">
        <Aviso tipo="hecho" vivo titulo="Anotado">
          Queda en tu registro (movimiento <Codigo>{registrar.resultado.activity_id}</Codigo>). No se ha enviado ninguna orden.
        </Aviso>
        <Boton variante="primario" className="w-full" onClick={onCerrar}>
          Hecho
        </Boton>
      </div>
    );
  }

  return (
    <form onSubmit={enviar} className="space-y-5">
      <Segmentado etiqueta="Qué hiciste" opciones={TIPOS} valor={tipo} onCambio={setTipo} repartido />
      {conActivo ? (
        <BuscadorActivo
          etiqueta={tipo === "compra" ? "Qué compraste" : "Qué vendiste"}
          ayuda="Busca por su nombre. Si no está en la lista, puedes escribirlo como aparece en tu bróker o en Binance."
          opciones={conocidos}
          valor={activo}
          onCambio={setActivo}
        />
      ) : null}
      {delPlan ? (
        <Aviso tipo="info" titulo="Es un fondo de tu plan">
          Si lo {lado === "sell" ? "vendiste" : "compraste"} siguiendo tu plan, anótalo desde Invertir con {boton}: así cuenta en
          tu plan y se guarda con lo que {lado === "sell" ? "cobraste" : "pagaste"} en tu bróker.{" "}
          <Link href={`/invertir/#accion-${delPlan.id}`} className="font-semibold underline underline-offset-4" onClick={onCerrar}>
            Ir a {boton}
          </Link>
        </Aviso>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto
          etiqueta={conActivo ? (activo?.cripto ? `Cantidad (${base(activo.simbolo)})` : "Cantidad") : "Importe"}
          sufijo={conActivo ? undefined : "€"}
          value={cantidad}
          onChange={(e) => setCantidad(e.target.value)}
          inputMode="decimal"
          required
        />
        {conActivo ? (
          <CampoTexto
            etiqueta="Precio por unidad"
            sufijo={sufijo}
            ayuda={activo ? (activo.moneda ? `El de ${activo.nombre} va ${enLaMoneda(activo.moneda)}.` : "En la moneda en que lo pagaste.") : undefined}
            value={precio}
            onChange={(e) => setPrecio(e.target.value)}
            inputMode="decimal"
            required
          />
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto etiqueta="Comisión" sufijo={sufijo ?? "€"} value={comision} onChange={(e) => setComision(e.target.value)} inputMode="decimal" />
        <CampoTexto etiqueta="Fecha" type="date" max={hoyLocal()} value={dia} onChange={(e) => setDia(e.target.value)} required />
      </div>
      {registrar.error ? <ErrorApiVista error={registrar.error} prefijo="No se anotó:" /> : null}
      <Boton type="submit" variante={delPlan ? "secundario" : "primario"} className="w-full" disabled={registrar.enCurso || (conActivo && !activo)}>
        {registrar.enCurso ? "Anotando…" : delPlan ? "Anotarlo aquí de todos modos" : "Anotar en mi registro"}
      </Boton>
      {conActivo && !activo ? <p className="text-center text-sm text-tinta-suave">Elige primero qué {tipo === "compra" ? "compraste" : "vendiste"}.</p> : null}
    </form>
  );
}

function OrdenesEnviadas({ version }: { version: number }) {
  const consulta = useConsulta(`ordenes:${version}`, () => pedir(api.GET("/api/ordenes")));
  const o = consulta.datos;
  return (
    <div className="space-y-3">
      <Nota>Lo que de verdad salió a Binance, con el modo de cada orden a la vista. La cartera dice qué tienes; esto, qué mandaste.</Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!o && consulta.cargando ? <Esqueleto className="h-24" /> : null}
      {o && o.total === 0 ? <p className="text-[0.9375rem] text-tinta-suave">Ninguna orden enviada todavía.</p> : null}
      {o && o.total > 0 ? (
        <>
          <MarcoTabla etiqueta="Órdenes enviadas, la más reciente primero" altoMaximo={420}>
            <thead>
              <tr>
                <Th>cuándo</Th>
                <Th>modo</Th>
                <Th>qué</Th>
                <Th numerica>pedida</Th>
                <Th numerica>hecha</Th>
                <Th numerica>precio</Th>
                <Th>estado</Th>
              </tr>
            </thead>
            <tbody>
              {o.filas.map((f, i) => (
                <tr key={`${f.cuando}-${i}`}>
                  <Td>{momento(f.cuando)}</Td>
                  <Td className={f.modo.toUpperCase() === "REAL" ? "font-bold text-real-tinta" : undefined}>
                    {f.modo.toUpperCase() === "REAL" ? "dinero real" : f.modo}
                  </Td>
                  <Td className="font-medium">
                    {f.lado === "buy" ? "Compra" : "Venta"} de {f.nombre}
                  </Td>
                  <Td numerica>{formatoCantidad(f.pedida)}</Td>
                  <Td numerica>{formatoCantidad(f.ejecutada)}</Td>
                  <Td numerica>{f.precio === null ? "—" : enMoneda(f.precio, f.moneda)}</Td>
                  <Td>
                    {{ filled: "hecha", partial: "en parte", rejected: "rechazada", unknown: "desconocido" }[f.estado] ?? f.estado}
                  </Td>
                </tr>
              ))}
            </tbody>
          </MarcoTabla>
          <Nota>
            {o.total} {o.total === 1 ? "orden" : "órdenes"} · <strong className="text-tinta">{o.reales} con dinero real</strong> · registro en{" "}
            <Codigo>{o.registro}</Codigo>
          </Nota>
          {o.atencion.map((a) => (
            <Aviso key={a} tipo={a.includes("DESCONOCIDO") ? "critico" : "aviso"}>
              <TextoApi texto={a} />
            </Aviso>
          ))}
        </>
      ) : null}
    </div>
  );
}

/**
 * Lo que tienes sin invertir, en una frase. `efectivo` sale de tus movimientos (negativo si
 * faltan ingresos por anotar); `efectivo_broker` es lo cobrado al vender con el plan y aún no
 * reinvertido (v2.2), que tienes seguro en tu bróker aunque el efectivo salga menor.
 */
function sinInvertir(c: Pick<DatosCartera, "efectivo" | "efectivo_broker" | "moneda">): string | null {
  const enBroker = signoDecimal(c.efectivo_broker) === 1;
  const total = enBroker && compararDecimal(c.efectivo_broker, c.efectivo) >= 0 ? c.efectivo_broker : c.efectivo;
  if (signoDecimal(total) !== 1) return null;
  const cifra = enMoneda(total, c.moneda);
  if (!enBroker) return `Además, ${cifra} sin invertir.`;
  if (total === c.efectivo_broker) {
    return `Además, ${cifra} sin invertir en tu bróker: lo que cobraste al vender con tu plan y aún no has vuelto a invertir.`;
  }
  return `Además, ${cifra} sin invertir; de ello, ${enMoneda(c.efectivo_broker, c.moneda)} en tu bróker, de lo que vendiste con tu plan.`;
}

/**
 * La linea "En total", en la moneda de la cartera (`Cartera.moneda`). La API suma sin convertir y
 * `nota_moneda` lo dice ("Aproximado: sin contar el cambio euro-dólar.").
 */
function Total({ c }: { c: DatosCartera }) {
  const aproximado = c.nota_moneda !== null;
  const efectivo = sinInvertir(c);
  return (
    <div className="space-y-1 border-t border-linea py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-[0.9375rem] text-tinta-suave">En total</p>
        <p className="cifras text-right text-[0.9375rem] text-tinta">
          {c.valor_total === null ? (
            "No se puede sumar: falta algún precio"
          ) : (
            <>
              Valen {aproximado ? "unos " : ""}
              <strong className="font-semibold">{enMoneda(c.valor_total, c.moneda)}</strong> · pusiste{" "}
              {enMoneda(c.invertido_abiertas, c.moneda)}
            </>
          )}
        </p>
      </div>
      {efectivo ? <p className="cifras text-right text-sm text-tinta-suave">{efectivo}</p> : null}
      {c.nota_moneda ? <p className="text-right text-sm text-tinta-suave">{c.nota_moneda}</p> : null}
    </div>
  );
}

/** Cartera: ¿que tengo? (docs/panel-v2.md, 4.4). La del modo activo, con sus fechas. */
export function Cartera() {
  const [version, setVersion] = useState(0);
  const { versionDatos, refrescarDatos } = useEstado();
  const { modo } = useModo();
  const [anotar, setAnotar] = useState(false);
  const clave = `${version}:${versionDatos}:${modo ?? "?"}`;
  const cartera = useConsulta(`cartera:${clave}`, () => pedir(api.GET("/api/cartera")));
  const movs = useConsulta(`movimientos:${clave}`, () => pedir(api.GET("/api/cartera/movimientos")));
  const c = cartera.datos;
  const ficticio = c?.cartera === "pruebas" || movs.datos?.cartera === "pruebas";
  const recargar = () => {
    setVersion((v) => v + 1);
    refrescarDatos();
  };

  return (
    <div>
      <Encabezado
        titulo="Cartera"
        bajada="Lo que tienes, lo que vendiste y todos tus movimientos."
        accion={
          <Boton variante="secundario" onClick={() => setAnotar(true)}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            Anotar un movimiento
          </Boton>
        }
      />
      {ficticio ? (
        <Aviso tipo="aviso" className="mb-6" titulo="Dinero ficticio">
          Estás en modo pruebas: esta es tu cartera de la red de pruebas de Binance, no la de verdad.
        </Aviso>
      ) : null}

      <div className="space-y-12">
        <section aria-labelledby="tienes-titulo" className="space-y-4">
          <h2 id="tienes-titulo" className="titular text-2xl font-semibold text-tinta">
            Lo que tienes
          </h2>
          {cartera.error ? <ErrorApiVista error={cartera.error} reintentar={cartera.recargar} /> : null}
          {!c && cartera.cargando ? <Esqueleto className="h-48" /> : null}
          {c?.error ? (
            <Aviso tipo="critico" titulo="Tu registro cuenta una historia imposible">
              <TextoApi texto={c.error} />
            </Aviso>
          ) : null}
          {c?.avisos.map((a) => (
            <Aviso key={a} tipo="aviso">
              <TextoApi texto={a} />
            </Aviso>
          ))}
          {c && !c.error && c.vacia ? (
            <EstadoVacio
              icono={Sprout}
              tono="neutro"
              titulo="Aún no tienes nada"
              accion={
                <BotonEnlace href="/invertir/" variante="primario">
                  Ver qué toca hacer
                </BotonEnlace>
              }
            >
              Cuando compres algo desde Invertir o anotes una compra, aparecerá aquí con lo que vale.
            </EstadoVacio>
          ) : null}
          {c && !c.error && c.abiertas.length ? (
            <Tarjeta className={clases("px-5 sm:px-6", cartera.cargando && "opacity-70")}>
              <ul className="divide-y divide-linea">
                {c.abiertas.map((p) => (
                  <FilaTienes key={p.activo} p={p} />
                ))}
              </ul>
              <Total c={c} />
            </Tarjeta>
          ) : null}
          {c && !c.error && !c.abiertas.length && signoDecimal(c.efectivo_broker) === 1 ? (
            // Lo vendiste todo con el plan y aún no lo has reinvertido: sin fondos, pero con dinero.
            <Tarjeta className="p-5 sm:p-6">
              <p className="cifras text-[0.9375rem] text-tinta">{sinInvertir(c)}</p>
            </Tarjeta>
          ) : null}
          {c?.abiertas.some((p) => p.es_referencia) ? (
            <Nota>
              Lo que compras en tu bróker desde el plan se sigue con el fondo de EE.UU. al que imita: por eso ves cuánto pusiste y
              cuánto vale, no tus participaciones. Las tuyas están en cada movimiento.
            </Nota>
          ) : null}
        </section>

        {c && c.retiradas.length ? (
          <section aria-labelledby="vendiste-titulo" className="space-y-4">
            <h2 id="vendiste-titulo" className="titular text-2xl font-semibold text-tinta">
              Lo que ya vendiste
            </h2>
            <Tarjeta className="px-5 sm:px-6">
              <ul className="divide-y divide-linea">
                {c.retiradas.map((r) => (
                  <FilaVendido key={`${r.activo}-${r.abierta}-${r.retirada}`} r={r} />
                ))}
              </ul>
            </Tarjeta>
            <Nota>Esto ya es un hecho: no cambia con los precios.</Nota>
          </section>
        ) : null}

        <section aria-labelledby="movimientos-titulo" className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="movimientos-titulo" className="titular text-2xl font-semibold text-tinta">
              Movimientos
            </h2>
            {ficticio ? <Chip tono="pruebas">dinero ficticio</Chip> : null}
          </div>
          {movs.error ? <ErrorApiVista error={movs.error} reintentar={movs.recargar} /> : null}
          {!movs.datos && movs.cargando ? <Esqueleto className="h-40" /> : null}
          {movs.datos && movs.datos.movimientos.length === 0 ? (
            <EstadoVacio icono={NotebookPen} tono="neutro" titulo="Tu registro está vacío">
              Cada compra, venta, ingreso o retirada que hagas o anotes quedará aquí, con su fecha.
            </EstadoVacio>
          ) : null}
          {movs.datos && movs.datos.movimientos.length ? (
            <Tarjeta className="px-4 sm:px-6">
              <ul className="divide-y divide-linea">
                {movs.datos.movimientos.map((m) => (
                  <FilaMovimiento key={m.id} m={m} />
                ))}
              </ul>
            </Tarjeta>
          ) : null}
        </section>

        <Proteccion activos={c?.abiertas.map((p) => ({ simbolo: p.activo, nombre: p.nombre })) ?? []} />

        <Desplegable resumen="Órdenes enviadas a Binance">
          <OrdenesEnviadas version={version} />
        </Desplegable>
      </div>

      <HojaAnotar abierta={anotar} onCerrar={() => setAnotar(false)} alAnotar={recargar} />
    </div>
  );
}
