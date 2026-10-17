"use client";

import { useState, type FormEvent } from "react";

import { api, pedir } from "@/api/cliente";
import type { Accion } from "@/api/tipos";
import { Hoja } from "@/componentes/Hoja";
import { Aviso, Boton, CampoTexto, Codigo, ErrorApiVista } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";
import { formatoImporte } from "@/lib/decimal";
import { euros, hoyLocal } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";

function Formulario({ accion: a, onTerminar }: { accion: Accion; onTerminar: () => void }) {
  // Cantidad y precio NO se rellenan: la referencia es del fondo de EE.UU. y lo que se compra
  // desde Espana es su version europea, con otro precio. Apuntar la referencia seria apuntar un
  // dato falso en el registro; se ensena como ejemplo.
  const [cantidad, setCantidad] = useState("");
  const [precio, setPrecio] = useState("");
  const [comision, setComision] = useState("0");
  const [fecha, setFecha] = useState(hoyLocal);
  const [intentado, setIntentado] = useState(false);

  const c = leerImporte(cantidad);
  const p = leerImporte(precio);
  const k = leerImporte(comision === "" ? "0" : comision);
  const errores = {
    cantidad: c === null || Number(c) <= 0 ? "Escribe cuántas participaciones compraste (más que 0)." : null,
    precio: p === null || Number(p) <= 0 ? "Escribe el precio por participación que te cobró tu bróker." : null,
    comision: k === null ? "Escribe la comisión, o 0 si no hubo." : null,
  };
  const valido = !errores.cantidad && !errores.precio && !errores.comision && fecha !== "";

  const anotar = useAccion(async () =>
    pedir(
      api.POST("/api/plan/hoy/{accion_id}/hecho", {
        params: { path: { accion_id: a.id } },
        body: { cantidad: c ?? "0", precio: p ?? "0", comision: k ?? "0", fecha },
      }),
    ),
  );

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    setIntentado(true);
    if (valido) void anotar.ejecutar();
  };

  if (anotar.resultado) {
    return (
      <div className="space-y-6">
        <Aviso tipo="hecho" vivo titulo="Anotado en tu registro">
          Tu compra de {a.activo.toLowerCase()} ya cuenta en tu cartera y en tu plan (movimiento{" "}
          <Codigo>{anotar.resultado.activity_id}</Codigo>).
        </Aviso>
        <Boton variante="primario" className="w-full" onClick={onTerminar}>
          Volver a Qué toca hoy
        </Boton>
      </div>
    );
  }

  return (
    <form onSubmit={enviar} noValidate className="space-y-5">
      <p className="rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] leading-relaxed text-tinta">
        Esto solo lo apunta en tu registro: <strong className="font-semibold">no compra nada</strong>. Pon los datos de tu
        compra tal como te los da tu bróker.
      </p>
      <CampoTexto
        etiqueta="Participaciones que compraste"
        ayuda="Las que te diga tu bróker. Pueden tener decimales."
        placeholder="p. ej. 1,5"
        value={cantidad}
        onChange={(e) => setCantidad(e.target.value)}
        inputMode="decimal"
        autoComplete="off"
        error={intentado ? errores.cantidad : null}
      />
      <CampoTexto
        etiqueta="Precio por participación"
        ayuda="El de tu fondo, en euros, tal como te lo da tu bróker."
        value={precio}
        onChange={(e) => setPrecio(e.target.value)}
        inputMode="decimal"
        autoComplete="off"
        sufijo="€"
        error={intentado ? errores.precio : null}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto
          etiqueta="Comisión"
          value={comision}
          onChange={(e) => setComision(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          sufijo="€"
          error={intentado ? errores.comision : null}
        />
        <CampoTexto etiqueta="Fecha de la compra" type="date" max={hoyLocal()} value={fecha} onChange={(e) => setFecha(e.target.value)} required />
      </div>
      {c && p && !errores.cantidad && !errores.precio ? (
        <p className="cifras text-[0.9375rem] text-tinta-suave" aria-live="polite">
          Lo que anotas: {formatoImporte(c, { decimales: 4 }).replace(/,?0+$/, "")} participaciones a {euros(p)} cada una.
        </p>
      ) : null}
      {anotar.error ? <ErrorApiVista error={anotar.error} prefijo="No se anotó:" /> : null}
      <Boton type="submit" variante="primario" className="w-full" disabled={anotar.enCurso}>
        {anotar.enCurso ? "Anotando…" : "Anotar mi compra"}
      </Boton>
    </form>
  );
}

/** "Ya lo he comprado": anotar en tu registro una compra hecha en tu broker (docs/panel-v2.md, 4.3). */
export function HojaYaComprado({
  accion,
  onCerrar,
  onTerminado,
}: {
  accion: Accion | null;
  onCerrar: () => void;
  onTerminado: () => void;
}) {
  return (
    <Hoja
      abierta={accion !== null}
      onCerrar={onCerrar}
      titulo="Anotar tu compra"
      bajada={accion ? `${accion.titulo}. ${accion.equivalente ? `Lo que buscabas: ${accion.equivalente}.` : ""}` : undefined}
    >
      {accion ? (
        <Formulario
          key={accion.id}
          accion={accion}
          onTerminar={() => {
            onTerminado();
            onCerrar();
          }}
        />
      ) : null}
    </Hoja>
  );
}
