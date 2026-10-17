"use client";

import { CircleCheck, CircleDashed, OctagonAlert, ShieldAlert, TriangleAlert } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { api, pedir } from "@/api/cliente";
import type { Accion, ModoPanel, ResultadoOrden } from "@/api/tipos";
import { ConfirmacionTecleada, useComprobacionOrden } from "@/componentes/ConfirmacionTecleada";
import { Hoja } from "@/componentes/Hoja";
import { Boton, ErrorApiVista, clases } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";
import { formatoCantidad } from "@/lib/decimal";
import { normalizarTecleo } from "@/lib/importe";
import { enMoneda, fechaCorta } from "@/lib/formato";
import { base } from "@/lib/nombres";

/** Lo que dice el resultado de una orden, en llano y con su gravedad. */
export function Resultado({ r, modo }: { r: ResultadoOrden; modo: ModoPanel | null }) {
  const estado = r.estado.toLowerCase();
  let titulo = "Orden enviada";
  let texto = r.descripcion;
  let Icono = CircleCheck;
  let estilo = "bg-sube-suave text-sube-texto";
  if (estado === "filled") {
    titulo = "Hecho";
  } else if (estado === "partial") {
    titulo = "Se hizo solo una parte";
    Icono = TriangleAlert;
    estilo = "bg-pruebas-suave text-pruebas-tinta";
  } else if (estado === "rejected") {
    titulo = "Binance la ha rechazado";
    Icono = OctagonAlert;
    estilo = "bg-real-suave text-real-tinta";
  } else if (estado === "unknown") {
    titulo = "Estado desconocido: compruébalo en Binance";
    texto = `${r.descripcion} Antes de volver a operar, entra en Binance y mira si la orden está o no: si la repites sin mirar, podrías comprar dos veces.`;
    Icono = OctagonAlert;
    estilo = "bg-real-suave text-real-tinta";
  } else {
    Icono = CircleDashed;
    estilo = "bg-superficie-2 text-tinta";
  }
  return (
    <div className="space-y-4" role={estado === "unknown" || estado === "rejected" ? "alert" : "status"}>
      <div className={clases("flex gap-4 rounded-2xl p-5", estilo)}>
        <Icono aria-hidden="true" className="h-7 w-7 shrink-0" strokeWidth={1.75} />
        <div>
          <p className="titular text-xl font-semibold">{titulo}</p>
          <p className="mt-1 text-[0.9375rem] leading-relaxed text-tinta">{texto}</p>
        </div>
      </div>
      {estado === "filled" || estado === "partial" ? (
        <p className="text-[0.9375rem] text-tinta-suave">
          Lo ejecutado ya está en tu cartera{modo === "pruebas" ? " de pruebas (dinero ficticio)" : ""}. Queda registrado con el modo
          «{r.modo}».
        </p>
      ) : (
        <p className="text-[0.9375rem] text-tinta-suave">Queda registrado con el modo «{r.modo}».</p>
      )}
    </div>
  );
}

function Fila({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-3">
      <dt className="text-[0.9375rem] text-tinta-suave">{etiqueta}</dt>
      <dd className="cifras text-right text-[0.9375rem] font-semibold text-tinta">{children}</dd>
    </div>
  );
}

function Contenido({
  accion: a,
  modo,
  onTerminar,
  onOcupada,
}: {
  accion: Accion;
  modo: ModoPanel | null;
  onTerminar: () => void;
  onOcupada: (si: boolean) => void;
}) {
  const cantidad = a.cantidad ?? "";
  const [escrito, setEscrito] = useState("");
  const normal = normalizarTecleo(escrito);
  const enviar = useAccion(async () =>
    pedir(api.POST("/api/ordenes", { body: { par: a.par ?? "", lado: a.lado, cantidad, escrito: normal } })),
  );
  const { estado } = useComprobacionOrden(cantidad, escrito, !enviar.resultado && !enviar.enCurso);
  useEffect(() => onOcupada(enviar.enCurso), [enviar.enCurso, onOcupada]);
  const real = modo === "real";
  const verbo = a.lado === "buy" ? "Comprar" : "Vender";
  const moneda = base(a.par ?? a.simbolo);

  if (enviar.resultado) {
    return (
      <div className="space-y-6">
        <Resultado r={enviar.resultado} modo={modo} />
        <Boton variante="primario" className="w-full" onClick={onTerminar}>
          Volver a Qué toca hoy
        </Boton>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {real ? (
        <div className="flex gap-3 rounded-2xl border-2 border-real bg-real-suave p-4 text-real-tinta" role="note">
          <ShieldAlert aria-hidden="true" className="h-6 w-6 shrink-0" strokeWidth={1.75} />
          <p className="text-[0.9375rem] leading-relaxed">
            <strong className="font-semibold">Dinero real.</strong> Esta orden mueve dinero de verdad de tu cuenta de Binance y
            no se puede deshacer.
          </p>
        </div>
      ) : (
        <p className="rounded-xl bg-pruebas-suave px-4 py-3 text-[0.9375rem] text-pruebas-tinta">
          Modo pruebas: la orden sale de verdad a Binance, con dinero ficticio.
        </p>
      )}

      <dl className="divide-y divide-linea rounded-2xl border border-linea px-4">
        <Fila etiqueta="Qué">
          {verbo} {a.activo}
        </Fila>
        <Fila etiqueta="Cantidad">
          {formatoCantidad(cantidad)} {moneda}
        </Fila>
        <Fila etiqueta="Precio aproximado">
          {a.precio_ref ? enMoneda(a.precio_ref, a.moneda) : "—"}
          {a.precio_fecha ? <span className="block text-sm font-normal text-tinta-suave">cierre del {fechaCorta(a.precio_fecha)}</span> : null}
        </Fila>
        <Fila etiqueta="Importe aproximado">≈ {enMoneda(a.importe, a.moneda)}</Fila>
        <Fila etiqueta="Dónde">{real ? "Binance · dinero real" : "Binance · pruebas"}</Fila>
      </dl>
      <p className="text-sm text-tinta-suave">
        El precio final será el del momento en que se ejecute: puede variar un poco respecto a este.
      </p>

      <ConfirmacionTecleada
        esperado={cantidad}
        valor={escrito}
        onCambio={setEscrito}
        estado={estado}
        tono={real ? "real" : "normal"}
        ayuda="Se escribe la cantidad, no un «sí»: obliga a mirar lo que se va a mover. Pegar está desactivado."
      />

      {enviar.error ? <ErrorApiVista error={enviar.error} prefijo="La orden no salió:" /> : null}

      <Boton
        variante={real ? "real" : "primario"}
        className="w-full"
        disabled={estado.tipo !== "puede" || enviar.enCurso}
        onClick={() => void enviar.ejecutar()}
      >
        {enviar.enCurso ? "Enviando a Binance…" : `${verbo} ${formatoCantidad(cantidad)} ${moneda}`}
      </Boton>
    </div>
  );
}

/**
 * Confirmar una orden de Binance (docs/panel-v2.md, 4.3): resumen, confirmacion tecleada y
 * resultado. El boton se activa SOLO cuando `POST /api/ordenes/comprobar` dice `puede`.
 */
export function HojaConfirmar({
  accion,
  modo,
  onCerrar,
  onTerminado,
}: {
  accion: Accion | null;
  modo: ModoPanel | null;
  onCerrar: () => void;
  onTerminado: () => void;
}) {
  const [ocupada, setOcupada] = useState(false);
  return (
    <Hoja
      abierta={accion !== null}
      onCerrar={onCerrar}
      cerrable={!ocupada}
      titulo={accion?.titulo ?? ""}
      bajada={accion?.explicacion}
    >
      {accion ? (
        <Contenido
          key={accion.id}
          accion={accion}
          modo={modo}
          onOcupada={setOcupada}
          onTerminar={() => {
            onTerminado();
            onCerrar();
          }}
        />
      ) : null}
    </Hoja>
  );
}
