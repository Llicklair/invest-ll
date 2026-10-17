"use client";

import { CircleCheck, CircleDashed, Keyboard } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { api, comoErrorApi, pedir, type ErrorApi } from "@/api/cliente";
import { normalizarTecleo } from "@/lib/importe";
import { useRetardado } from "@/lib/consulta";

import { clases } from "./ui";

export type EstadoTecleo =
  | { tipo: "vacio" }
  | { tipo: "comprobando" }
  | { tipo: "puede" }
  | { tipo: "no"; motivo: string | null }
  | { tipo: "error"; error: ErrorApi };

/**
 * La confirmacion del Principio I: se escribe la cifra (o "DINERO REAL"), no un "si". Pegar y
 * arrastrar estan desactivados: hay que mirarla y teclearla. El boton que confirma NO lo decide
 * este componente: lo decide quien lo usa con `estado` (para las ordenes, la API).
 */
export function ConfirmacionTecleada({
  esperado,
  valor,
  onCambio,
  estado,
  etiqueta,
  ayuda,
  tono = "normal",
  mayusculas = false,
}: {
  /** Lo que hay que escribir, tal cual se ensena. */
  esperado: string;
  valor: string;
  onCambio: (v: string) => void;
  estado: EstadoTecleo;
  etiqueta?: string;
  ayuda?: string;
  tono?: "normal" | "real";
  /** Para "DINERO REAL": teclado en mayusculas en el movil. */
  mayusculas?: boolean;
}) {
  const id = useId();
  const idEstado = `${id}-estado`;
  const idAyuda = `${id}-ayuda`;
  const vacio = valor.trim() === "";

  let linea: string;
  let Icono = CircleDashed;
  let color = "text-tinta-suave";
  switch (estado.tipo) {
    case "vacio":
      linea = "Todavía no has escrito nada.";
      Icono = Keyboard;
      break;
    case "comprobando":
      linea = "Comprobando lo que has escrito…";
      break;
    case "puede":
      linea = "Coincide. Ya puedes confirmar.";
      Icono = CircleCheck;
      color = "text-sube-texto";
      break;
    case "no":
      linea = estado.motivo ?? "Todavía no coincide.";
      color = vacio ? "text-tinta-suave" : "text-tinta";
      break;
    case "error":
      linea = `No se pudo comprobar: ${estado.error.detalle}`;
      color = "text-real-tinta";
      break;
  }

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-[0.9375rem] font-medium text-tinta">
        {etiqueta ?? (
          <>
            Escribe <span className="tecleo rounded-md bg-superficie-2 px-1.5 py-0.5 font-semibold">{esperado}</span> para
            confirmar
          </>
        )}
      </label>
      <input
        id={id}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        onPaste={(e) => e.preventDefault()}
        onDrop={(e) => e.preventDefault()}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize={mayusculas ? "characters" : "off"}
        spellCheck={false}
        inputMode={mayusculas ? "text" : "decimal"}
        aria-describedby={`${idEstado}${ayuda ? ` ${idAyuda}` : ""}`}
        placeholder={esperado}
        className={clases(
          "tecleo min-h-14 w-full rounded-xl border-2 bg-superficie px-4 text-xl text-tinta placeholder:text-tinta-suave/35",
          tono === "real" ? "border-real/60" : "border-linea-control/70",
          estado.tipo === "puede" && "border-sube",
        )}
      />
      <p id={idEstado} className={clases("flex items-start gap-2 text-sm", color)} aria-live="polite">
        <Icono aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
        {linea}
      </p>
      {ayuda ? (
        <p id={idAyuda} className="text-sm text-tinta-suave">
          {ayuda}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Pregunta a la API si con esta cantidad y lo tecleado AHORA se puede enviar la orden
 * (`POST /api/ordenes/comprobar`). Una respuesta de una entrada anterior no vale: si se sigue
 * tecleando, vuelve a "comprobando". La coma decimal del movil se pasa a punto antes de enviar.
 */
export function useComprobacionOrden(cantidad: string, escrito: string, activa: boolean): { estado: EstadoTecleo; escritoNormal: string } {
  const escritoNormal = normalizarTecleo(escrito);
  const clave = useRetardado(JSON.stringify([cantidad, escritoNormal]), 250);
  const [resultado, setResultado] = useState<{ clave: string; estado: EstadoTecleo } | null>(null);

  useEffect(() => {
    if (!activa) return;
    const [c = "", e = ""] = JSON.parse(clave) as string[];
    if (e.trim() === "") return;
    let vigente = true;
    pedir(api.POST("/api/ordenes/comprobar", { body: { cantidad: c || "0", escrito: e } })).then(
      (r) => {
        if (vigente) setResultado({ clave, estado: r.puede ? { tipo: "puede" } : { tipo: "no", motivo: r.motivo } });
      },
      (err: unknown) => {
        if (vigente) setResultado({ clave, estado: { tipo: "error", error: comoErrorApi(err) } });
      },
    );
    return () => {
      vigente = false;
    };
  }, [clave, activa]);

  const actual = JSON.stringify([cantidad, escritoNormal]);
  let estado: EstadoTecleo;
  if (escritoNormal.trim() === "") estado = { tipo: "vacio" };
  else if (!resultado || resultado.clave !== actual) estado = { tipo: "comprobando" };
  else estado = resultado.estado;
  return { estado, escritoNormal };
}
