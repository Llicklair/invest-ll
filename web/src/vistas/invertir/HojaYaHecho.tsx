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

/** Lo que cambia entre anotar una compra y una venta del broker: las palabras, no los campos. */
const TEXTOS = {
  buy: {
    titulo: "Anotar tu compra",
    no: "no compra nada",
    cantidad: "Participaciones que compraste",
    faltaCantidad: "Escribe cuántas participaciones compraste (más que 0).",
    ayudaPrecio: "El de tu fondo, en euros, tal como te lo da tu bróker.",
    faltaPrecio: "Escribe el precio por participación que te cobró tu bróker.",
    fecha: "Fecha de la compra",
    resumen: "pagas",
    boton: "Anotar mi compra",
  },
  sell: {
    titulo: "Anotar tu venta",
    no: "no vende nada",
    cantidad: "Participaciones que vendiste",
    faltaCantidad: "Escribe cuántas participaciones vendiste (más que 0).",
    ayudaPrecio: "Al que vendiste, en euros, tal como te lo da tu bróker.",
    faltaPrecio: "Escribe el precio por participación al que vendiste.",
    fecha: "Fecha de la venta",
    resumen: "cobras",
    boton: "Anotar mi venta",
  },
} as const;

function Formulario({ accion: a, onTerminar }: { accion: Accion; onTerminar: () => void }) {
  // Cantidad y precio NO se rellenan: la referencia es del fondo de EE.UU. y lo que se compra
  // desde Espana es su version europea, con otro precio. Apuntar la referencia seria apuntar un
  // dato falso en el registro; se ensena como ejemplo.
  const t = TEXTOS[a.lado];
  const [cantidad, setCantidad] = useState("");
  const [precio, setPrecio] = useState("");
  const [comision, setComision] = useState("0");
  const [fecha, setFecha] = useState(hoyLocal);
  const [intentado, setIntentado] = useState(false);

  const c = leerImporte(cantidad);
  const p = leerImporte(precio);
  const k = leerImporte(comision === "" ? "0" : comision);
  const errores = {
    cantidad: c === null || Number(c) <= 0 ? t.faltaCantidad : null,
    precio: p === null || Number(p) <= 0 ? t.faltaPrecio : null,
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
          {a.lado === "sell" ? (
            <>
              Tu venta de {a.activo.toLowerCase()} ya cuenta en tu cartera y en tu plan (movimiento{" "}
              <Codigo>{anotar.resultado.activity_id}</Codigo>). Lo que cobraste queda sin invertir en tu bróker hasta que
              compres lo que dice tu lista de la compra.
            </>
          ) : (
            <>
              Tu compra de {a.activo.toLowerCase()} ya cuenta en tu cartera y en tu plan (movimiento{" "}
              <Codigo>{anotar.resultado.activity_id}</Codigo>).
            </>
          )}
        </Aviso>
        <Boton variante="primario" className="w-full" onClick={onTerminar}>
          Volver a Qué toca hoy
        </Boton>
      </div>
    );
  }

  const importe = c && p && !errores.cantidad && !errores.precio ? (Number(c) * Number(p)).toFixed(2) : null;
  return (
    <form onSubmit={enviar} noValidate className="space-y-5">
      <p className="rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] leading-relaxed text-tinta">
        Esto solo lo apunta en tu registro: <strong className="font-semibold">{t.no}</strong>. Pon los datos de tu{" "}
        {a.lado === "sell" ? "venta" : "compra"} tal como te los da tu bróker.
      </p>
      <CampoTexto
        etiqueta={t.cantidad}
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
        ayuda={t.ayudaPrecio}
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
        <CampoTexto etiqueta={t.fecha} type="date" max={hoyLocal()} value={fecha} onChange={(e) => setFecha(e.target.value)} required />
      </div>
      {c && p && importe ? (
        <p className="cifras text-[0.9375rem] text-tinta-suave" aria-live="polite">
          Lo que anotas: {formatoImporte(c, { decimales: 4 }).replace(/,?0+$/, "")} participaciones a {euros(p)} cada una (
          {t.resumen} {euros(importe)}).
        </p>
      ) : null}
      {anotar.error ? <ErrorApiVista error={anotar.error} prefijo="No se anotó:" /> : null}
      <Boton type="submit" variante="primario" className="w-full" disabled={anotar.enCurso}>
        {anotar.enCurso ? "Anotando…" : t.boton}
      </Boton>
    </form>
  );
}

/**
 * "Ya lo he comprado" y "Ya lo he vendido": anotar en tu registro lo que hiciste en tu broker
 * siguiendo tu plan (docs/panel-v2.md, 4.3 y 7). Las dos van a `POST /api/plan/hoy/{id}/hecho`.
 */
export function HojaYaHecho({
  accion,
  onCerrar,
  onTerminado,
}: {
  accion: Accion | null;
  onCerrar: () => void;
  onTerminado: () => void;
}) {
  const venta = accion?.lado === "sell";
  const lo = accion?.equivalente ? `${venta ? "Lo que vendes: el que compraste como" : "Lo que buscabas:"} ${accion.equivalente}.` : "";
  return (
    <Hoja
      abierta={accion !== null}
      onCerrar={onCerrar}
      titulo={venta ? TEXTOS.sell.titulo : TEXTOS.buy.titulo}
      bajada={accion ? `${accion.titulo}. ${lo}` : undefined}
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
