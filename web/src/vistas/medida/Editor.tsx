"use client";

import { CircleCheck, CircleX } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { DetalleEstrategia, EsquemaEstrategia } from "@/api/tipos";
import { Boton, CampoTexto, Cargando, ErrorApiVista, TextoPlano } from "@/componentes/ui";
import { useAccion } from "@/lib/consulta";

type Lectura = { ok: true; definicion: Record<string, unknown> } | { ok: false; motivo: string };

/** Lee el JSON y, si no vale, dice donde (linea y columna), en llano. */
function leer(texto: string): Lectura {
  if (!texto.trim()) return { ok: false, motivo: "Está vacío." };
  try {
    const v: unknown = JSON.parse(texto);
    if (typeof v !== "object" || v === null || Array.isArray(v)) return { ok: false, motivo: "Tiene que ser un objeto: empieza por { y acaba por }." };
    return { ok: true, definicion: v as Record<string, unknown> };
  } catch (e) {
    const mensaje = e instanceof Error ? e.message : String(e);
    const pos = /position (\d+)/.exec(mensaje);
    if (pos) {
      const hasta = texto.slice(0, Number(pos[1]));
      const linea = hasta.split("\n").length;
      const columna = hasta.length - hasta.lastIndexOf("\n");
      return { ok: false, motivo: `No es JSON válido: algo falla en la línea ${linea}, columna ${columna} (una coma o unas comillas, casi siempre).` };
    }
    return { ok: false, motivo: "No es JSON válido: revisa comas, comillas y llaves." };
  }
}

/**
 * El editor avanzado: la estrategia en su formato cerrado (JSON), para quien quiera tocarla a mano.
 * Aqui solo se comprueba que es JSON; si la estrategia vale lo decide la API al guardar (422 en
 * llano), que es la unica que conoce el formato. Guardar crea una version nueva: las pruebas de
 * antes eran de la anterior.
 */
export function EditorEstrategia({
  inicial,
  id,
  version,
  onGuardada,
}: {
  inicial: string;
  /** Si se da, se guarda como nueva version de esa estrategia. */
  id?: string;
  version?: number;
  onGuardada: (d: DetalleEstrategia) => void;
}) {
  const [texto, setTexto] = useState(inicial);
  const [nota, setNota] = useState("");
  const base = useId();
  const lectura = useMemo(() => leer(texto), [texto]);
  const cambiado = texto !== inicial;
  const guardar = useAccion(async () => {
    if (!lectura.ok) return null;
    const d = await pedir(api.POST("/api/medida", { body: { definicion: lectura.definicion, autor: "marcos", nota: nota.trim(), id: id ?? null } }));
    setNota("");
    onGuardada(d);
    return d;
  });
  const esquema = useAccion(() => pedir(api.GET("/api/medida/esquema")));
  const formato: EsquemaEstrategia | null = esquema.resultado;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${base}-json`} className="text-[0.9375rem] font-medium text-tinta">
          La estrategia en su formato (JSON)
        </label>
        <textarea
          id={`${base}-json`}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          rows={18}
          aria-invalid={lectura.ok ? undefined : true}
          aria-describedby={`${base}-estado`}
          className="w-full rounded-xl border border-linea-control/70 bg-superficie px-3.5 py-3 font-mono text-[0.8125rem] leading-relaxed text-tinta aria-[invalid=true]:border-real"
        />
        <p id={`${base}-estado`} className="flex items-start gap-2 text-sm" aria-live="polite">
          {lectura.ok ? (
            <>
              <CircleCheck aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-sube-texto" />
              <span className="text-tinta-suave">Es JSON válido. Si la estrategia vale, lo dice la API al guardar.</span>
            </>
          ) : (
            <>
              <CircleX aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-real-tinta" />
              <span className="font-medium text-real-tinta">{lectura.motivo}</span>
            </>
          )}
        </p>
      </div>
      <CampoTexto
        etiqueta="Qué cambia (se guarda con la versión)"
        value={nota}
        onChange={(e) => setNota(e.target.value)}
        placeholder={id ? "Por ejemplo: stop del 6 % en vez del 8 %" : "Por ejemplo: primera versión"}
        maxLength={200}
      />
      {guardar.error ? <ErrorApiVista error={guardar.error} prefijo="No se guardó:" /> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Boton onClick={() => void guardar.ejecutar()} disabled={!lectura.ok || guardar.enCurso || (id !== undefined && !cambiado)}>
          {guardar.enCurso ? "Validando y guardando…" : id ? `Guardar como versión ${(version ?? 0) + 1}` : "Validar y guardar"}
        </Boton>
        {cambiado ? (
          <button type="button" onClick={() => setTexto(inicial)} className="inline-flex min-h-11 items-center text-sm font-semibold text-marca underline-offset-4 hover:underline">
            Deshacer mis cambios
          </button>
        ) : null}
      </div>
      <div className="border-t border-linea pt-4">
        {!formato ? (
          <button
            type="button"
            onClick={() => void esquema.ejecutar()}
            disabled={esquema.enCurso}
            className="inline-flex min-h-11 items-center text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline"
          >
            Ver el formato y un ejemplo
          </button>
        ) : null}
        {esquema.enCurso ? <Cargando texto="Leyendo el formato…" /> : null}
        {esquema.error ? <ErrorApiVista error={esquema.error} /> : null}
        {formato ? (
          <div className="space-y-3">
            <p className="text-[0.9375rem] leading-relaxed text-tinta">{formato.explicacion}</p>
            {formato.ejemplos[0] ? (
              <>
                <p className="text-sm font-semibold text-tinta">Un ejemplo</p>
                <TextoPlano className="max-h-80 overflow-y-auto">{JSON.stringify(formato.ejemplos[0], null, 2)}</TextoPlano>
                {!id ? (
                  <Boton tamano="compacto" onClick={() => setTexto(JSON.stringify(formato.ejemplos[0], null, 2))}>
                    Empezar desde este ejemplo
                  </Boton>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
