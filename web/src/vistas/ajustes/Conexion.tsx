"use client";

import { Check, CircleCheck, CircleX, ExternalLink, KeyRound, Lock, ShieldAlert, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";

import { api, pedir, pedirSinCuerpo } from "@/api/cliente";
import type { Conexion as DatosConexion, ModoPanel, PruebaConexion, Red } from "@/api/tipos";
import { ConfirmacionTecleada } from "@/componentes/ConfirmacionTecleada";
import { Hoja } from "@/componentes/Hoja";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { Aviso, Boton, BotonEnlace, CampoTexto, Cargando, Chip, ErrorApiVista, Tarjeta, clases } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { NOMBRE_MODO, useModo } from "@/contexto/modo";
import { useAccion } from "@/lib/consulta";
import { formatoCantidad } from "@/lib/decimal";
import { enUnaFrase } from "@/lib/formato";

type EstadoEtapa = "hecha" | "actual" | "bloqueada";

function Etapa({
  numero,
  titulo,
  estado,
  resumen,
  children,
}: {
  numero: number;
  titulo: string;
  estado: EstadoEtapa;
  resumen: string;
  children: ReactNode;
}) {
  const [abierta, setAbierta] = useState<boolean | null>(null);
  const visible = abierta ?? estado === "actual";
  return (
    <li className="relative pl-14 after:absolute after:top-16 after:-bottom-4 after:left-[17px] after:w-0.5 after:rounded-full after:bg-linea last:after:hidden">
      <span
        className={clases(
          "absolute top-5 left-0 flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold",
          estado === "hecha" && "bg-sube text-white",
          estado === "actual" && "bg-marca text-marca-tinta",
          estado === "bloqueada" && "bg-superficie-2 text-tinta-suave ring-1 ring-linea",
        )}
        aria-hidden="true"
      >
        {estado === "hecha" ? <Check className="h-4 w-4" strokeWidth={3} /> : estado === "bloqueada" ? <Lock className="h-4 w-4" /> : numero}
      </span>
      <Tarjeta className={clases("p-5 sm:p-6", estado === "bloqueada" && "bg-superficie-2/40 shadow-none")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="titular text-xl font-semibold text-tinta">
              <span className="sr-only">Etapa {numero}: </span>
              {titulo}
            </h3>
            <p className="mt-1 text-[0.9375rem] text-tinta-suave">{resumen}</p>
          </div>
          <div className="flex items-center gap-2">
            <Chip tono={estado === "hecha" ? "sube" : estado === "actual" ? "marca" : "neutro"}>
              {estado === "hecha" ? "Hecha" : estado === "actual" ? "Ahora" : "Más adelante"}
            </Chip>
            {estado !== "actual" ? (
              <button
                type="button"
                aria-expanded={visible}
                onClick={() => setAbierta(!visible)}
                className="inline-flex min-h-11 items-center px-2 text-sm font-semibold text-marca underline-offset-4 hover:underline"
              >
                {visible ? "Ocultar" : "Ver"}
              </button>
            ) : null}
          </div>
        </div>
        {visible ? <div className="mt-5 space-y-5 border-t border-linea pt-5">{children}</div> : null}
      </Tarjeta>
    </li>
  );
}

function ResultadoPrueba({ r }: { r: PruebaConexion }) {
  return (
    <Aviso tipo={r.ok ? "hecho" : "critico"} vivo titulo={r.ok ? "La conexión funciona" : "La conexión no funciona"}>
      <p>{r.detalle}</p>
      {r.saldo.length ? (
        <ul className="mt-2 flex flex-wrap gap-2">
          {r.saldo.map((s) => (
            <li key={s.moneda} className="cifras rounded-full bg-superficie px-3 py-1 text-sm text-tinta">
              {formatoCantidad(s.cantidad)} {s.moneda}
            </li>
          ))}
        </ul>
      ) : null}
    </Aviso>
  );
}

/** Guardar, probar y borrar las claves de una red. Una vez guardadas, nunca se vuelven a ensenar. */
function Claves({ red, conexion, onCambio }: { red: Red; conexion: DatosConexion; onCambio: () => void }) {
  const estado = conexion.redes.find((r) => r.red === red);
  const [clave, setClave] = useState("");
  const [secreto, setSecreto] = useState("");

  const guardar = useAccion(async () => {
    await pedirSinCuerpo(
      api.PUT("/api/conexion/claves/{red}", { params: { path: { red } }, body: { clave: clave.trim(), secreto: secreto.trim() } }),
    );
    setClave("");
    setSecreto("");
    onCambio();
    return true;
  });
  const borrar = useAccion(async () => {
    await pedirSinCuerpo(api.DELETE("/api/conexion/claves/{red}", { params: { path: { red } } }));
    onCambio();
    return true;
  });
  const probar = useAccion(() => pedir(api.POST("/api/conexion/probar/{red}", { params: { path: { red } } })));

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    void guardar.ejecutar();
  };

  if (estado?.origen === "entorno") {
    return (
      <div className="space-y-4">
        <Aviso tipo="info" titulo="Configuradas desde el entorno">
          Las claves de {red === "pruebas" ? "pruebas" : "dinero real"} vienen de las variables de entorno (docs/operar-de-verdad.md). Mandan
          ellas: el panel las usa, pero ni las guarda ni las muestra.
        </Aviso>
        <Boton variante="secundario" onClick={() => void probar.ejecutar()} disabled={probar.enCurso}>
          {probar.enCurso ? "Probando…" : "Probar la conexión"}
        </Boton>
        {probar.error ? <ErrorApiVista error={probar.error} /> : null}
        {probar.resultado ? <ResultadoPrueba r={probar.resultado} /> : null}
      </div>
    );
  }

  if (estado?.claves_guardadas) {
    return (
      <div className="space-y-4">
        <p className="flex items-start gap-3 rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">
          <KeyRound aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-marca" strokeWidth={1.75} />
          Claves guardadas en el almacén de credenciales de Windows. Por seguridad no se vuelven a mostrar en ninguna pantalla.
        </p>
        <div className="flex flex-wrap gap-3">
          <Boton variante="secundario" onClick={() => void probar.ejecutar()} disabled={probar.enCurso}>
            {probar.enCurso ? "Probando…" : "Probar la conexión"}
          </Boton>
          <Boton variante="peligro" onClick={() => void borrar.ejecutar()} disabled={borrar.enCurso}>
            <Trash2 aria-hidden="true" className="h-4 w-4" />
            Borrar las claves
          </Boton>
        </div>
        <p className="text-sm text-tinta-suave">Probar solo lee tu saldo: no envía ninguna orden.</p>
        {probar.error ? <ErrorApiVista error={probar.error} /> : null}
        {probar.resultado ? <ResultadoPrueba r={probar.resultado} /> : null}
        {borrar.error ? <ErrorApiVista error={borrar.error} prefijo="No se borraron:" /> : null}
      </div>
    );
  }

  return (
    <form onSubmit={enviar} className="space-y-4" autoComplete="off">
      <CampoTexto
        etiqueta={red === "pruebas" ? "Clave de la red de pruebas (API Key)" : "Clave de dinero real (API Key)"}
        value={clave}
        onChange={(e) => setClave(e.target.value)}
        autoComplete="off"
        spellCheck={false}
        required
        minLength={8}
      />
      <CampoTexto
        etiqueta="Secreto (Secret Key)"
        type="password"
        value={secreto}
        onChange={(e) => setSecreto(e.target.value)}
        autoComplete="new-password"
        spellCheck={false}
        required
        minLength={8}
        ayuda="Se guardan en el almacén de credenciales de Windows, nunca en un fichero ni en el repositorio. Después no se vuelven a mostrar."
      />
      {guardar.error ? <ErrorApiVista error={guardar.error} prefijo="No se guardaron:" /> : null}
      <Boton type="submit" variante="primario" disabled={guardar.enCurso || clave.trim().length < 8 || secreto.trim().length < 8}>
        {guardar.enCurso ? "Guardando…" : "Guardar las claves"}
      </Boton>
    </form>
  );
}

function CambiarModo({ a, conexion, onCambio, texto }: { a: ModoPanel; conexion: DatosConexion; onCambio: () => void; texto: string }) {
  const cambiar = useAccion(async () => {
    const r = await pedir(api.PUT("/api/conexion/modo", { body: { modo: a } }));
    onCambio();
    return r;
  });
  const disponible = conexion.modos.find((m) => m.modo === a);
  const entorno = conexion.modo_origen === "entorno";
  return (
    <div className="space-y-2">
      <Boton
        variante={a === "simulacion" ? "secundario" : "primario"}
        onClick={() => void cambiar.ejecutar()}
        disabled={cambiar.enCurso || entorno || disponible?.disponible === false}
      >
        {cambiar.enCurso ? "Cambiando…" : texto}
      </Boton>
      {disponible && !disponible.disponible && disponible.que_falta.length ? (
        <p className="text-sm text-tinta-suave">Falta: {enUnaFrase(disponible.que_falta)}</p>
      ) : null}
      {cambiar.error ? <ErrorApiVista error={cambiar.error} prefijo="No se cambió el modo:" /> : null}
    </div>
  );
}

function Cerrojos({ conexion }: { conexion: DatosConexion }) {
  return (
    <div>
      <p className="font-semibold text-tinta">Los cuatro cerrojos del dinero real</p>
      <p className="mt-1 text-sm text-tinta-suave">Tienen que estar los cuatro abiertos. Ninguno se puede saltar desde el panel.</p>
      <ul className="mt-3 divide-y divide-linea rounded-xl border border-linea">
        {conexion.cerrojos_real.map((c) => (
          <li key={c.nombre} className="flex items-start gap-3 px-4 py-3">
            {c.ok ? (
              <CircleCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
            ) : (
              <CircleX aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-tinta-suave" strokeWidth={1.75} />
            )}
            <div>
              <p className="text-[0.9375rem] font-medium text-tinta">
                {c.nombre}
                <span className="sr-only">{c.ok ? ": abierto" : ": cerrado"}</span>
              </p>
              <p className="text-sm text-tinta-suave">{c.detalle}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HojaDineroReal({ abierta, onCerrar, onActivado }: { abierta: boolean; onCerrar: () => void; onActivado: () => void }) {
  const [escrito, setEscrito] = useState("");
  const coincide = escrito === "DINERO REAL";
  const activar = useAccion(async () => {
    const r = await pedir(api.PUT("/api/conexion/modo", { body: { modo: "real", confirmacion: escrito } }));
    onActivado();
    return r;
  });
  return (
    <Hoja
      abierta={abierta}
      onCerrar={() => {
        setEscrito("");
        activar.limpiar();
        onCerrar();
      }}
      cerrable={!activar.enCurso}
      titulo="Activar el dinero real"
      bajada="A partir de aquí, las órdenes que confirmes mueven dinero de verdad de tu cuenta de Binance."
    >
      {activar.resultado ? (
        <div className="space-y-6">
          <Aviso tipo="critico" vivo titulo="Dinero real activado">
            Verás una franja roja arriba en todas las pantallas mientras dure. Cada orden te seguirá pidiendo que teclees la cantidad.
          </Aviso>
          <Boton variante="primario" className="w-full" onClick={onCerrar}>
            Entendido
          </Boton>
        </div>
      ) : (
        <div className="space-y-6">
          <ul className="list-disc space-y-2 pl-5 text-[0.9375rem] leading-relaxed text-tinta marker:text-tinta-suave">
            <li>El panel no compra ni vende solo: cada orden la revisas y la confirmas tú.</li>
            <li>Puedes volver a simulación cuando quieras, desde aquí mismo.</li>
            <li>Si algo falla a mitad de una orden, te lo dirá y tendrás que comprobarlo en Binance.</li>
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
            {activar.enCurso ? "Activando…" : "Activar el dinero real"}
          </Boton>
        </div>
      )}
    </Hoja>
  );
}

/**
 * Conectar Binance (docs/panel-v2.md, 4.6): un camino de tres etapas con su estado. Los cuatro
 * cerrojos de live/mode.py no se relajan: el panel solo cambia de donde salen el modo y las claves.
 */
export function Conexion() {
  const { conexion, error, cargando, modo } = useModo();
  const { refrescarDatos } = useEstado();
  const [hojaReal, setHojaReal] = useState(false);

  if (!conexion) {
    if (error && !cargando) return <ErrorApiVista error={error} prefijo="No se pudo leer la conexión:" reintentar={refrescarDatos} />;
    return <Cargando texto="Leyendo la conexión…" />;
  }

  const pruebas = conexion.redes.find((r) => r.red === "pruebas");
  const real = conexion.redes.find((r) => r.red === "real");
  // La etapa 1 esta hecha cuando el modo pruebas esta ACTIVO, no al guardar unas claves (que
  // pueden no funcionar): plegarla entonces escondia Probar, Usar el modo pruebas y Borrar.
  const enPruebasOMas = modo === "pruebas" || modo === "real";
  const etapa1: EstadoEtapa = enPruebasOMas ? "hecha" : "actual";
  const etapa2: EstadoEtapa = pruebas?.verificada ? "hecha" : modo === "pruebas" ? "actual" : "bloqueada";
  const etapa3: EstadoEtapa = modo === "real" ? "hecha" : pruebas?.verificada ? "actual" : "bloqueada";
  const disponibleReal = conexion.modos.find((m) => m.modo === "real");

  return (
    <div className="space-y-6">
      <Tarjeta className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <p className="text-sm text-tinta-suave">Modo actual</p>
          <p className="titular text-2xl font-semibold text-tinta">{modo ? NOMBRE_MODO[modo] : "Desconocido"}</p>
          {conexion.modo_origen === "entorno" ? (
            <p className="mt-1 text-sm text-tinta-suave">Lo fija el entorno (INVEST_LL_MODE): para cambiarlo, cámbialo allí.</p>
          ) : null}
        </div>
        {modo !== "simulacion" ? <CambiarModo a="simulacion" conexion={conexion} onCambio={refrescarDatos} texto="Volver a simulación" /> : null}
      </Tarjeta>

      <ol className="space-y-4">
        <Etapa
          numero={1}
          titulo="Pruebas"
          estado={etapa1}
          resumen="Dinero ficticio, órdenes de verdad: aprendes sin pagar."
        >
          <ol className="list-decimal space-y-2 pl-5 text-[0.9375rem] leading-relaxed text-tinta">
            <li>
              Entra en{" "}
              <a
                href="https://testnet.binance.vision"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-semibold text-marca underline underline-offset-4"
              >
                testnet.binance.vision
                <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                <span className="sr-only">(se abre en otra pestaña)</span>
              </a>{" "}
              con tu cuenta de GitHub.
            </li>
            <li>
              Crea una clave de tipo <strong className="font-semibold">HMAC-SHA256</strong> (las de tipo Ed25519 o RSA no sirven aquí).
            </li>
            <li>Pega aquí la clave y el secreto, y prueba la conexión.</li>
          </ol>
          <Claves red="pruebas" conexion={conexion} onCambio={refrescarDatos} />
          {modo === "simulacion" && pruebas?.claves_guardadas ? (
            <div className="space-y-2 border-t border-linea pt-5">
              <p className="text-[0.9375rem] text-tinta">
                Cuando la prueba diga que la conexión funciona, pasa al modo pruebas. Si las claves no sirven, el panel no
                cambiará de modo y te dirá por qué.
              </p>
              <CambiarModo a="pruebas" conexion={conexion} onCambio={refrescarDatos} texto="Usar el modo pruebas" />
            </div>
          ) : modo === "pruebas" ? (
            <p className="flex items-start gap-3 text-[0.9375rem] text-tinta">
              <CircleCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
              Estás en modo pruebas: las órdenes salen de verdad a Binance, con dinero ficticio.
            </p>
          ) : null}
          <QueEsEsto clave="pruebas" />
        </Etapa>

        <Etapa
          numero={2}
          titulo="Haz una orden de prueba"
          estado={etapa2}
          resumen="Se marca sola cuando hay una orden de pruebas ejecutada en tu registro."
        >
          {pruebas?.verificada ? (
            <p className="flex items-start gap-3 text-[0.9375rem] text-tinta">
              <CircleCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-sube-texto" strokeWidth={1.75} />
              Hecha: hay una orden de pruebas ejecutada en tu registro.
            </p>
          ) : (
            <>
              <p className="text-[0.9375rem] leading-relaxed text-tinta">
                En modo pruebas, haz una compra pequeña desde Invertir: la que toque hoy o una a mano en «Avanzado». Cuando se ejecute,
                esta etapa se marcará sola. Es la prueba de que sabes cómo funciona, no una casilla que se marca a mano.
              </p>
              {modo === "pruebas" ? (
                <BotonEnlace href="/invertir/" variante="primario">
                  Ir a Invertir
                </BotonEnlace>
              ) : (
                <p className="text-sm text-tinta-suave">Primero, pasa al modo pruebas en la etapa 1.</p>
              )}
            </>
          )}
        </Etapa>

        <Etapa
          numero={3}
          titulo="Dinero real"
          estado={etapa3}
          resumen="Con claves distintas, que solo puedan leer y operar al contado. Nunca retirar."
        >
          <div className="rounded-xl bg-superficie-2 px-4 py-4">
            <p className="font-semibold text-tinta">Al crear la clave en Binance, marca solo:</p>
            <ul className="mt-2 space-y-1.5 text-[0.9375rem] text-tinta">
              <li className="flex gap-2">
                <Check aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-sube-texto" /> Lectura
              </li>
              <li className="flex gap-2">
                <Check aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-sube-texto" /> Operar al contado (spot)
              </li>
              <li className="flex gap-2 font-semibold">
                <CircleX aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-real-tinta" /> Nunca «retiradas»
              </li>
              <li className="flex gap-2 text-tinta-suave">
                <Check aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" /> Si puedes, restringe la clave a tu IP
              </li>
            </ul>
          </div>
          <p className="text-[0.9375rem] text-tinta">Tienen que ser distintas de las de pruebas.</p>
          {real ? <Claves red="real" conexion={conexion} onCambio={refrescarDatos} /> : null}
          <Cerrojos conexion={conexion} />
          {modo !== "real" ? (
            <div className="space-y-2">
              <Boton
                variante="real"
                onClick={() => setHojaReal(true)}
                disabled={!disponibleReal?.disponible || conexion.modo_origen === "entorno"}
              >
                <ShieldAlert aria-hidden="true" className="h-4 w-4" />
                Activar el dinero real
              </Boton>
              {disponibleReal && !disponibleReal.disponible ? (
                <p className="text-sm text-tinta-suave">Falta: {enUnaFrase(disponibleReal.que_falta)}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-[0.9375rem] text-tinta">
              El dinero real está activado. Puedes volver a{" "}
              <Link href="/ajustes/#conexion" className="font-semibold text-marca underline underline-offset-4" onClick={() => window.scrollTo({ top: 0 })}>
                simulación
              </Link>{" "}
              cuando quieras.
            </p>
          )}
        </Etapa>
      </ol>

      <HojaDineroReal abierta={hojaReal} onCerrar={() => setHojaReal(false)} onActivado={refrescarDatos} />
    </div>
  );
}
