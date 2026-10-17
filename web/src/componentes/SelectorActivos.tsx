"use client";

import { useId } from "react";

import type { Activo } from "@/api/tipos";

import { clases } from "./ui";

/**
 * Seleccion multiple de activos (lo que en Streamlit era `st.multiselect`), agrupada en bolsa y
 * cripto. Con `maximo`, al llegar al tope se bloquean los demas y se dice por que.
 */
export function SelectorActivos({
  etiqueta,
  activos,
  seleccion,
  onCambio,
  maximo,
  motivoMaximo,
  usarEtiqueta = false,
}: {
  etiqueta: string;
  activos: readonly Activo[];
  seleccion: readonly string[];
  onCambio: (ids: string[]) => void;
  maximo?: number;
  motivoMaximo?: string;
  /** Mostrar `label` (con el intervalo) en vez del simbolo. */
  usarEtiqueta?: boolean;
}) {
  const id = useId();
  const lleno = maximo !== undefined && seleccion.length >= maximo;
  const grupos: [string, Activo[]][] = [
    ["Bolsa", activos.filter((a) => !a.is_crypto)],
    ["Cripto", activos.filter((a) => a.is_crypto)],
  ];

  const alternar = (activoId: string) => {
    if (seleccion.includes(activoId)) onCambio(seleccion.filter((x) => x !== activoId));
    else if (!lleno) onCambio([...seleccion, activoId]);
  };

  return (
    <fieldset className="min-w-0 space-y-2" aria-describedby={`${id}-estado`}>
      <legend className="text-sm font-medium text-tinta">{etiqueta}</legend>
      {grupos.map(([nombre, lista]) =>
        lista.length ? (
          <div key={nombre} className="flex flex-wrap items-center gap-1.5">
            <span className="w-12 text-xs text-tinta-suave">{nombre}</span>
            {lista.map((a) => {
              const marcado = seleccion.includes(a.id);
              const bloqueado = !marcado && lleno;
              return (
                <label
                  key={a.id}
                  title={`${a.label} · ${a.provider} · ${a.desde} a ${a.hasta}`}
                  className={clases(
                    "inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-full border px-3.5 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-foco",
                    marcado ? "border-marca bg-marca-suave font-semibold text-tinta" : "border-linea bg-superficie text-tinta-suave",
                    bloqueado && "cursor-not-allowed opacity-50",
                  )}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={marcado}
                    disabled={bloqueado}
                    onChange={() => alternar(a.id)}
                  />
                  <span aria-hidden="true">{marcado ? "✓" : "+"}</span>
                  {usarEtiqueta ? a.label : a.symbol}
                </label>
              );
            })}
          </div>
        ) : null,
      )}
      <p id={`${id}-estado`} className="text-xs text-tinta-suave">
        {seleccion.length} elegido(s){maximo !== undefined ? ` de un máximo de ${maximo}` : ""}.
        {lleno && motivoMaximo ? ` ${motivoMaximo}` : ""}
      </p>
    </fieldset>
  );
}
