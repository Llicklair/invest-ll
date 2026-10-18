"use client";

import { Banknote, CircleCheck, CircleX, ExternalLink, FlaskConical, KeyRound, ShieldAlert, Trash2 } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import type { CampoClave, EstadoExchange, EstadoRedExchange, ExchangeDisponible, MercadosExchange, PruebaExchange, RedExchange } from "@/api/tipos";
import { ConfirmacionTecleada } from "@/componentes/ConfirmacionTecleada";
import { Hoja } from "@/componentes/Hoja";
import { Pestanas } from "@/componentes/Pestanas";
import { Aviso, Boton, BotonEnlace, CampoTexto, Cargando, Chip, ESTILO_ENTRADA, ErrorApiVista, clases } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";
import { formatoCantidad } from "@/lib/decimal";
import { momento } from "@/lib/formato";

import { CaminoPlanBinance, Etapa, type EstadoEtapa } from "./Conexion";

const NOMBRE_RED: Record<RedExchange, string> = { pruebas: "la red de pruebas", real: "dinero real" };

/** Sin conectar · Pruebas · Dinero real: icono + palabra, el color nunca va solo. */
export function ChipEstadoExchange({ activo, className }: { activo: EstadoExchange["activo"]; className?: string }) {
  if (activo === "real") {
    return (
      <Chip tono="real" className={className} icono={<Banknote aria-hidden="true" className="h-3.5 w-3.5" />}>
        Dinero real
      </Chip>
    );
  }
  if (activo === "pruebas") {
    return (
      <Chip tono="pruebas" className={className} icono={<FlaskConical aria-hidden="true" className="h-3.5 w-3.5" />}>
        Pruebas
      </Chip>
    );
  }
  return (
    <Chip tono="neutro" className={className}>
      Sin conectar
    </Chip>
  );
}

/** Los pasos para conseguir las claves, con los dominios convertidos en enlaces. */
function Pasos({ pasos }: { pasos: readonly string[] }) {
  return (
    <ol className="list-decimal space-y-2 pl-5 text-[0.9375rem] leading-relaxed text-tinta marker:text-tinta-suave">
      {pasos.map((p) => (
        <li key={p}>
          <ConEnlaces texto={p} />
        </li>
      ))}
    </ol>
  );
}

const DOMINIO = /\b((?:[a-z0-9-]+\.)+(?:com|xyz|vision|io))(\/[\w/-]*)?\b/gi;

function ConEnlaces({ texto }: { texto: string }) {
  const partes: (string | { dominio: string })[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(DOMINIO)) {
    const i = m.index ?? 0;
    partes.push(texto.slice(ultimo, i));
    partes.push({ dominio: m[0] });
    ultimo = i + m[0].length;
  }
  partes.push(texto.slice(ultimo));
  return (
    <>
      {partes.map((p, i) =>
        typeof p === "string" ? (
          p
        ) : (
          <a key={i} href={`https://${p.dominio}`} target="_blank" rel="noopener noreferrer" className="font-semibold text-marca underline underline-offset-4 [overflow-wrap:anywhere]">
            {p.dominio}
            <ExternalLink aria-hidden="true" className="ml-1 inline h-3.5 w-3.5 align-[-2px]" />
            <span className="sr-only">(se abre en otra pestaña)</span>
          </a>
        ),
      )}
    </>
  );
}

function ResultadoPruebaExchange({ r }: { r: PruebaExchange }) {
  return (
    <Aviso tipo={r.ok ? "hecho" : "critico"} vivo titulo={r.ok ? "La conexión funciona" : "La conexión no funciona"}>
      <p>{r.detalle}</p>
      {r.saldo.length ? (
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Saldo">
          {r.saldo.map((s) => (
            <li key={s.moneda} className="cifras rounded-full bg-superficie px-3 py-1 text-sm text-tinta">
              {formatoCantidad(s.cantidad)} {s.moneda}
            </li>
          ))}
        </ul>
      ) : null}
      {r.permisos ? <p className="mt-2 text-sm">Permisos de la clave: {r.permisos}</p> : null}
    </Aviso>
  );
}

/** Lo que se sabe de si la clave puede retirar (solo cuenta en dinero real). */
function Retirada({ estado, nombre }: { estado: EstadoRedExchange; nombre: string }) {
  if (!estado.claves_guardadas) return null;
  if (estado.puede_retirar === true) {
    return (
      <Aviso tipo="critico" titulo="Esta clave PUEDE retirar dinero">
        Con ella se podría sacar dinero de tu cuenta de {nombre}. Bórrala aquí y en {nombre}, y crea otra sin el permiso de retirada.
      </Aviso>
    );
  }
  if (estado.puede_retirar === false) {
    return (
      <p className="flex items-start gap-2 text-[0.9375rem] text-tinta">
        <CircleCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
        {nombre} dice que esta clave no puede retirar dinero.
      </p>
    );
  }
  if (estado.red === "real") {
    return (
      <Aviso tipo="aviso">
        {nombre} no dice si esta clave puede retirar. {estado.comprobado ? "Compruébalo tú en su página de claves: tiene que estar sin ese permiso." : "Prueba la conexión: a veces se sabe al probar."}
      </Aviso>
    );
  }
  return null;
}

/**
 * Una clave que ocupa varias lineas (la privada EC de Coinbase, en PEM). Un input de contrasena se
 * come los saltos de linea al pegar y la clave deja de valer, asi que va en un textarea con los
 * caracteres tapados (-webkit-text-security: Chromium y Safari; en Firefox se veria). El contrato
 * no dice que campo es de varias lineas (`CampoClave` no lo lleva): se reconoce por su ayuda.
 */
function esMultilinea(c: CampoClave): boolean {
  return c.secreto && /BEGIN|PEM|varias l[ií]neas/i.test(`${c.nombre} ${c.ayuda}`);
}

function CampoSecretoLargo({ campo, valor, onCambio }: { campo: CampoClave; valor: string; onCambio: (v: string) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[0.9375rem] font-medium text-tinta">
        {campo.nombre}
      </label>
      <textarea
        id={id}
        rows={5}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        spellCheck={false}
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        required
        aria-describedby={`${id}-ayuda`}
        className={clases(ESTILO_ENTRADA, "py-3 font-mono text-sm [-webkit-text-security:disc]")}
      />
      <p id={`${id}-ayuda`} className="text-sm text-tinta-suave">
        {campo.ayuda} Ocupa varias líneas: pégala entera, con la primera y la última. Se escribe tapada.
      </p>
    </div>
  );
}

/**
 * Guardar, probar y borrar las claves de una red de un exchange, con los campos que pide ESE
 * exchange (`CampoClave`). Los secretos se escriben ocultos; una vez guardadas, ninguna clave se
 * vuelve a ensenar en ninguna pantalla.
 */
function ClavesRed({
  exchange,
  red,
  estado,
  onCambio,
}: {
  exchange: ExchangeDisponible;
  red: RedExchange;
  estado: EstadoRedExchange | undefined;
  onCambio: () => void;
}) {
  const [valores, setValores] = useState<Record<string, string>>({});
  const base = useId();
  const guardar = useAccion(async () => {
    const limpios = Object.fromEntries(exchange.campos.map((c) => [c.clave, (valores[c.clave] ?? "").trim()]));
    await pedirSinCuerpo(api.PUT("/api/conexiones/{exchange}/claves/{red}", { params: { path: { exchange: exchange.id, red } }, body: { valores: limpios } }));
    setValores({});
    onCambio();
    return true;
  });
  const borrar = useAccion(async () => {
    await pedirSinCuerpo(api.DELETE("/api/conexiones/{exchange}/claves/{red}", { params: { path: { exchange: exchange.id, red } } }));
    onCambio();
    return true;
  });
  const probar = useAccion(async () => {
    const r = await pedir(api.POST("/api/conexiones/{exchange}/probar/{red}", { params: { path: { exchange: exchange.id, red } } }));
    onCambio();
    return r;
  });

  const completos = exchange.campos.every((c) => (valores[c.clave] ?? "").trim().length > 0);
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (completos) void guardar.ejecutar();
  };

  const acciones = (
    <>
      <p className="text-sm text-tinta-suave">Probar solo lee tu saldo y lo que puede hacer la clave: no envía ninguna orden.</p>
      {estado?.comprobado ? <p className="text-sm text-tinta-suave">Última prueba buena: {momento(estado.comprobado)}.</p> : null}
      {probar.error ? <ErrorApiVista error={probar.error} /> : null}
      {probar.resultado ? <ResultadoPruebaExchange r={probar.resultado} /> : null}
      {estado ? <Retirada estado={estado} nombre={exchange.nombre} /> : null}
    </>
  );

  if (estado?.origen === "entorno") {
    return (
      <div className="space-y-4">
        <Aviso tipo="info" titulo="Configuradas desde el entorno">
          Las claves de {NOMBRE_RED[red]} de {exchange.nombre} vienen de las variables de entorno. Mandan ellas: el panel las usa, pero ni las guarda ni las muestra.
        </Aviso>
        <Boton onClick={() => void probar.ejecutar()} disabled={probar.enCurso}>
          {probar.enCurso ? "Probando…" : "Probar la conexión"}
        </Boton>
        {acciones}
      </div>
    );
  }

  if (estado?.claves_guardadas) {
    return (
      <div className="space-y-4">
        <p className="flex items-start gap-3 rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">
          <KeyRound aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-marca" strokeWidth={1.75} />
          Claves de {NOMBRE_RED[red]} guardadas en el almacén de credenciales de Windows. Por seguridad no se vuelven a mostrar en ninguna pantalla.
        </p>
        <div className="flex flex-wrap gap-3">
          <Boton onClick={() => void probar.ejecutar()} disabled={probar.enCurso}>
            {probar.enCurso ? "Probando…" : "Probar la conexión"}
          </Boton>
          <Boton variante="peligro" onClick={() => void borrar.ejecutar()} disabled={borrar.enCurso}>
            <Trash2 aria-hidden="true" className="h-4 w-4" />
            {borrar.enCurso ? "Borrando…" : "Borrar las claves"}
          </Boton>
        </div>
        {acciones}
        {borrar.error ? <ErrorApiVista error={borrar.error} prefijo="No se borraron:" /> : null}
      </div>
    );
  }

  return (
    <form onSubmit={enviar} className="space-y-4" autoComplete="off" aria-label={`Claves de ${NOMBRE_RED[red]} de ${exchange.nombre}`}>
      {exchange.campos.map((c: CampoClave) =>
        esMultilinea(c) ? (
          <CampoSecretoLargo key={`${base}-${c.clave}`} campo={c} valor={valores[c.clave] ?? ""} onCambio={(v) => setValores((x) => ({ ...x, [c.clave]: v }))} />
        ) : (
        <CampoTexto
          key={`${base}-${c.clave}`}
          etiqueta={c.nombre}
          ayuda={c.ayuda}
          type={c.secreto ? "password" : "text"}
          value={valores[c.clave] ?? ""}
          onChange={(e) => setValores((v) => ({ ...v, [c.clave]: e.target.value }))}
          autoComplete={c.secreto ? "new-password" : "off"}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          required
        />
        ),
      )}
      <p className="text-sm text-tinta-suave">
        Se guardan en el almacén de credenciales de Windows, nunca en un fichero ni en el repositorio, y no se vuelven a mostrar.
        {red === "real" ? " Tienen que ser distintas de las de pruebas." : ""}
      </p>
      {guardar.error ? <ErrorApiVista error={guardar.error} prefijo="No se guardaron:" /> : null}
      <Boton type="submit" variante="primario" disabled={guardar.enCurso || !completos}>
        {guardar.enCurso ? "Guardando…" : "Guardar las claves"}
      </Boton>
    </form>
  );
}

function HojaRealExchange({ exchange, abierta, onCerrar, onActivado }: { exchange: ExchangeDisponible; abierta: boolean; onCerrar: () => void; onActivado: () => void }) {
  const [escrito, setEscrito] = useState("");
  const coincide = escrito === "DINERO REAL";
  const activar = useAccion(async () => {
    const r = await pedir(api.POST("/api/conexiones/{exchange}/activar", { params: { path: { exchange: exchange.id } }, body: { red: "real", confirmacion: escrito } }));
    onActivado();
    return r;
  });
  const cerrar = () => {
    setEscrito("");
    activar.limpiar();
    onCerrar();
  };
  return (
    <Hoja
      abierta={abierta}
      onCerrar={cerrar}
      cerrable={!activar.enCurso}
      titulo={`Usar dinero real en ${exchange.nombre}`}
      bajada={`A partir de aquí, los bots que TÚ actives con dinero real podrán comprar y vender en tu cuenta de ${exchange.nombre}.`}
    >
      {activar.resultado ? (
        <div className="space-y-6">
          <Aviso tipo="critico" vivo titulo={`${exchange.nombre}: dinero real activado`}>
            Ningún bot usa todavía dinero real: cada uno se activa aparte, desde su ficha, con sus límites y escribiendo «ACTIVAR» y su nombre.
          </Aviso>
          <Boton variante="primario" className="w-full" onClick={cerrar}>
            Entendido
          </Boton>
        </div>
      ) : (
        <div className="space-y-6">
          <ul className="list-disc space-y-2 pl-5 text-[0.9375rem] leading-relaxed text-tinta marker:text-tinta-suave">
            <li>Esto no activa ningún bot: cada bot se pasa a dinero real aparte, desde su ficha, con sus límites puestos.</li>
            <li>Los bots reales operan solos, sin pedirte confirmación en cada orden, y nunca fuera de sus límites.</li>
            <li>Arriba, en Bots, tendrás siempre a la vista el botón «Parar todo lo real».</li>
            <li>Claude no puede hacer esto: solo tú, desde aquí.</li>
          </ul>
          <ConfirmacionTecleada
            esperado="DINERO REAL"
            valor={escrito}
            onCambio={setEscrito}
            mayusculas
            tono="real"
            estado={escrito.trim() === "" ? { tipo: "vacio" } : coincide ? { tipo: "puede" } : { tipo: "no", motivo: "Escribe exactamente DINERO REAL, en mayúsculas." }}
          />
          {activar.error ? <ErrorApiVista error={activar.error} prefijo="No se activó:" /> : null}
          <Boton variante="real" className="w-full" disabled={!coincide || activar.enCurso} onClick={() => void activar.ejecutar()}>
            <ShieldAlert aria-hidden="true" className="h-4 w-4" />
            {activar.enCurso ? "Activando…" : `Usar dinero real en ${exchange.nombre}`}
          </Boton>
        </div>
      )}
    </Hoja>
  );
}

/** Los pares de contado del exchange (datos publicos): se piden al abrir, no antes. */
function Mercados({ exchange, red }: { exchange: ExchangeDisponible; red: RedExchange }) {
  const pedirMercados = useAccion(() => pedir(api.GET("/api/conexiones/{exchange}/mercados", { params: { path: { exchange: exchange.id }, query: { red } } })));
  const [abierto, setAbierto] = useState(false);
  const id = useId();
  const datos: MercadosExchange | null = pedirMercados.resultado;
  return (
    <div className="border-t border-linea pt-4">
      <button
        type="button"
        aria-expanded={abierto}
        aria-controls={id}
        onClick={() => {
          setAbierto(!abierto);
          if (!abierto && !datos) void pedirMercados.ejecutar();
        }}
        className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline"
      >
        {abierto ? "Ocultar sus monedas" : `Qué monedas tiene ${exchange.nombre} (${red === "pruebas" ? "red de pruebas" : "contado"})`}
      </button>
      {abierto ? (
        <div id={id} className="mt-2 space-y-2">
          {pedirMercados.enCurso ? <Cargando texto="Leyendo sus pares de contado…" /> : null}
          {pedirMercados.error ? <ErrorApiVista error={pedirMercados.error} /> : null}
          {datos ? (
            <>
              <p className="text-sm text-tinta-suave">
                {datos.mercados.length} pares de contado. El mínimo es lo menos que acepta por orden.
              </p>
              <ul className="grid gap-2 sm:grid-cols-2">
                {datos.mercados.map((mk) => (
                  <li key={mk.par} className="flex items-baseline justify-between gap-3 rounded-xl border border-linea px-3 py-2 text-sm">
                    <span>
                      <span className="font-semibold text-tinta">{mk.nombre}</span> <span className="text-tinta-suave">{mk.par}</span>
                    </span>
                    <span className="cifras text-tinta-suave">{mk.minimo_importe ? `mín. ${formatoCantidad(mk.minimo_importe)} ${mk.cotizada}` : "—"}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function CaminoBots({ exchange, estado, onCambio }: { exchange: ExchangeDisponible; estado: EstadoExchange; onCambio: () => void }) {
  const [hojaReal, setHojaReal] = useState(false);
  const pruebas = estado.redes.find((r) => r.red === "pruebas");
  const real = estado.redes.find((r) => r.red === "real");
  const usarPruebas = useAccion(async () => {
    const r = await pedir(api.POST("/api/conexiones/{exchange}/activar", { params: { path: { exchange: exchange.id } }, body: { red: "pruebas" } }));
    onCambio();
    return r;
  });

  const enPruebasOMas = estado.activo === "pruebas" || estado.activo === "real";
  const etapa1: EstadoEtapa = enPruebasOMas ? "hecha" : "actual";
  const etapa2: EstadoEtapa = pruebas?.verificada ? "hecha" : estado.activo === "pruebas" ? "actual" : "bloqueada";
  const etapa3: EstadoEtapa = estado.activo === "real" ? "hecha" : !exchange.tiene_pruebas || pruebas?.verificada ? "actual" : "bloqueada";

  const realPuedo = estado.activo !== "real" && estado.que_falta_real.length === 0;

  const etapaReal = (numero: number) => (
    <Etapa
      numero={numero}
      titulo="Dinero real"
      estado={etapa3}
      resumen="Con claves distintas, que solo puedan leer y operar al contado. Nunca retirar."
    >
      <div className="rounded-xl bg-superficie-2 px-4 py-4">
        <p className="font-semibold text-tinta">Cómo conseguir las claves de dinero real, sin permiso de retirada:</p>
        <div className="mt-2">
          <Pasos pasos={exchange.como_conseguir_real} />
        </div>
      </div>
      {real ? <ClavesRed exchange={exchange} red="real" estado={real} onCambio={onCambio} /> : null}
      {estado.activo === "real" ? (
        <div className="space-y-3">
          <p className="flex items-start gap-3 text-[0.9375rem] text-tinta">
            <Banknote aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-real-tinta" strokeWidth={1.75} />
            {exchange.nombre} está con dinero real. Solo operan con él los bots que actives tú, uno a uno, desde su ficha.
          </p>
          {exchange.tiene_pruebas && pruebas?.claves_guardadas ? (
            <Boton onClick={() => void usarPruebas.ejecutar()} disabled={usarPruebas.enCurso}>
              {usarPruebas.enCurso ? "Cambiando…" : "Volver a la red de pruebas"}
            </Boton>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2">
          {estado.que_falta_real.length ? (
            <div>
              <p className="font-semibold text-tinta">Lo que falta para usar dinero real</p>
              <ul className="mt-2 divide-y divide-linea rounded-xl border border-linea">
                {estado.que_falta_real.map((f) => (
                  <li key={f} className="flex items-start gap-3 px-4 py-3 text-[0.9375rem] text-tinta">
                    <CircleX aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-tinta-suave" strokeWidth={1.75} />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <Boton variante="real" onClick={() => setHojaReal(true)} disabled={!realPuedo}>
            <ShieldAlert aria-hidden="true" className="h-4 w-4" />
            Usar dinero real en {exchange.nombre}
          </Boton>
        </div>
      )}
      {usarPruebas.error ? <ErrorApiVista error={usarPruebas.error} /> : null}
      <HojaRealExchange exchange={exchange} abierta={hojaReal} onCerrar={() => setHojaReal(false)} onActivado={onCambio} />
    </Etapa>
  );

  if (!exchange.tiene_pruebas) {
    return (
      <div className="space-y-5">
        <Aviso tipo="aviso" titulo={`${exchange.nombre} no tiene red de pruebas`}>
          {exchange.aviso ??
            `Aquí no hay dinero ficticio con órdenes de verdad. Antes de activar un bot con dinero real en ${exchange.nombre}, su estrategia tiene que haber pasado por ficticio (se recomienda un mes) y aprobar su examen sobre el pasado.`}{" "}
          Si no, al activarlo tendrás que escribir «SIN PRUEBA EN FICTICIO», y la decisión queda registrada.
        </Aviso>
        <ol className="space-y-4">{etapaReal(1)}</ol>
        <Mercados exchange={exchange} red="real" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <ol className="space-y-4">
        <Etapa numero={1} titulo="Red de pruebas" estado={etapa1} resumen="Dinero ficticio, órdenes de verdad: aprendes sin pagar.">
          <Pasos pasos={exchange.como_conseguir_pruebas} />
          <ClavesRed exchange={exchange} red="pruebas" estado={pruebas} onCambio={onCambio} />
          {estado.activo === "sin_conectar" && pruebas?.claves_guardadas ? (
            <div className="space-y-2 border-t border-linea pt-5">
              <p className="text-[0.9375rem] text-tinta">
                Úsalo en pruebas para poder desplegar bots en su red de pruebas. Al activarlo, el panel prueba antes la conexión: si no funciona, te dice por qué y no cambia nada.
              </p>
              <Boton variante="primario" onClick={() => void usarPruebas.ejecutar()} disabled={usarPruebas.enCurso}>
                {usarPruebas.enCurso ? "Activando…" : `Usar ${exchange.nombre} en pruebas`}
              </Boton>
              {usarPruebas.error ? <ErrorApiVista error={usarPruebas.error} prefijo="No se activó:" /> : null}
            </div>
          ) : enPruebasOMas ? (
            <p className="flex items-start gap-3 text-[0.9375rem] text-tinta">
              <CircleCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
              {estado.activo === "pruebas" ? `${exchange.nombre} está en pruebas: los bots que despliegues aquí operan con su dinero ficticio.` : "Hecha."}
            </p>
          ) : null}
        </Etapa>

        <Etapa numero={2} titulo="Una orden de prueba" estado={etapa2} resumen="Se marca sola cuando un bot ejecuta una orden en su red de pruebas.">
          {pruebas?.verificada ? (
            <p className="flex items-start gap-3 text-[0.9375rem] text-tinta">
              <CircleCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
              Hecha: hay al menos una orden ejecutada en la red de pruebas de {exchange.nombre}. Es la evidencia de que todo funciona, no una casilla.
            </p>
          ) : (
            <>
              <p className="text-[0.9375rem] leading-relaxed text-tinta">
                Despliega un bot en pruebas con {exchange.nombre}. Cuando ejecute su primera orden, esta etapa se marcará sola: es la prueba de que las claves,
                el exchange y el bot funcionan juntos, no una casilla que se marca a mano.
              </p>
              {estado.activo === "pruebas" ? (
                <BotonEnlace href={`/bots/nuevo/?modo=pruebas&exchange=${encodeURIComponent(exchange.id)}`} variante="primario">
                  Desplegar un bot en pruebas
                </BotonEnlace>
              ) : (
                <p className="text-sm text-tinta-suave">Primero, úsalo en pruebas en la etapa 1.</p>
              )}
            </>
          )}
        </Etapa>

        {etapaReal(3)}
      </ol>
      <Mercados exchange={exchange} red={estado.activo === "pruebas" ? "pruebas" : "real"} />
    </div>
  );
}

/**
 * El asistente de un exchange (docs/panel-v4-real.md §1): pruebas -> una orden de prueba -> dinero
 * real, como el de Binance de v2, con los campos y los pasos que manda la API para ESE exchange.
 * Binance ademas guarda aqui el camino de tu plan (Invertir), el de v2, tal cual.
 */
export function AsistenteExchange({ exchange, estado, onCambio, id }: { exchange: ExchangeDisponible; estado: EstadoExchange; onCambio: () => void; id: string }) {
  const [pestana, setPestana] = useState<"bots" | "plan">("bots");
  const conPlan = exchange.id === "binance";
  return (
    <div id={id} className="space-y-5 border-t border-linea bg-fondo/50 px-4 py-5 sm:px-6">
      {exchange.aviso && exchange.tiene_pruebas ? <Aviso tipo="info">{exchange.aviso}</Aviso> : null}
      {conPlan ? (
        <Pestanas
          etiqueta={`Para qué usas ${exchange.nombre}`}
          pestanas={[
            { clave: "bots", texto: "Para tus bots" },
            { clave: "plan", texto: "Para tu plan (Invertir)" },
          ]}
          actual={pestana}
          onCambio={setPestana}
          idPanel={`${id}-panel`}
        />
      ) : null}
      <div id={`${id}-panel`} role={conPlan ? "tabpanel" : undefined} aria-labelledby={conPlan ? `pestana-${pestana}` : undefined} className={clases(conPlan && "pt-1")}>
        {conPlan && pestana === "plan" ? <CaminoPlanBinance /> : <CaminoBots exchange={exchange} estado={estado} onCambio={onCambio} />}
      </div>
    </div>
  );
}
