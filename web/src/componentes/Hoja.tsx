"use client";

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { clases } from "./ui";

/**
 * Una hoja: lateral en escritorio (>= 1024 px) e inferior en movil. Es un <dialog> nativo con
 * showModal(), asi que el navegador ya hace lo dificil: atrapa el foco dentro, deja inerte el
 * resto de la pagina, cierra con Escape y devuelve el foco al boton que la abrio.
 *
 * Mientras se puede, se monta solo abierta: el contenido (formularios, graficas) nace y muere con
 * ella y no arrastra estado de la vez anterior.
 */
export function Hoja({
  abierta,
  onCerrar,
  titulo,
  bajada,
  children,
  pie,
  ancho = "normal",
  cerrable = true,
}: {
  abierta: boolean;
  onCerrar: () => void;
  titulo: ReactNode;
  bajada?: ReactNode;
  children: ReactNode;
  /** Botones fijos abajo (la accion principal de la hoja). */
  pie?: ReactNode;
  ancho?: "normal" | "ancho";
  /** false mientras hay algo en curso que no se debe abandonar a medias (una orden enviandose). */
  cerrable?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();
  const cerrarRef = useRef(onCerrar);
  const cerrableRef = useRef(cerrable);

  useEffect(() => {
    cerrarRef.current = onCerrar;
    cerrableRef.current = cerrable;
  });

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (abierta && !d.open) {
      d.showModal();
      // El foco empieza en el titulo (lo lee el lector de pantalla), no en la X de cerrar.
      d.querySelector<HTMLElement>("[data-titulo-hoja]")?.focus();
    }
    if (!abierta && d.open) d.close();
  }, [abierta]);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const alCancelar = (e: Event) => {
      e.preventDefault();
      if (cerrableRef.current) cerrarRef.current();
    };
    // Chrome cierra a la fuerza con un segundo Escape aunque se cancele el primero: si el dialogo
    // se cierra por su cuenta, se avisa para que el estado de React no diga que sigue abierto.
    const alCerrar = () => cerrarRef.current();
    d.addEventListener("cancel", alCancelar);
    d.addEventListener("close", alCerrar);
    return () => {
      d.removeEventListener("cancel", alCancelar);
      d.removeEventListener("close", alCerrar);
    };
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitulo}
      className="hoja fixed inset-0 h-full w-full overflow-hidden"
      onMouseDown={(e) => {
        // Pinchar en el velo (fuera del panel) cierra; dentro, nada.
        if (e.target === e.currentTarget && cerrable) onCerrar();
      }}
    >
      {abierta ? (
        <div className="flex h-full w-full items-end justify-center lg:items-stretch lg:justify-end" onMouseDown={(e) => {
          if (e.target === e.currentTarget && cerrable) onCerrar();
        }}>
          <div
            className={clases(
              "hoja-panel flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-3xl bg-superficie shadow-alta lg:h-full lg:max-h-none lg:rounded-none lg:rounded-l-3xl",
              ancho === "ancho" ? "lg:w-[min(820px,92vw)]" : "lg:w-[min(560px,92vw)]",
            )}
          >
            <div className="flex justify-center pt-2.5 lg:hidden" aria-hidden="true">
              <span className="h-1.5 w-10 rounded-full bg-linea" />
            </div>
            <header className="flex items-start gap-3 border-b border-linea px-5 pt-3 pb-4 lg:px-8 lg:pt-7">
              <div className="min-w-0 flex-1">
                <h2 id={idTitulo} data-titulo-hoja tabIndex={-1} className="titular outline-none text-[1.375rem] leading-snug font-semibold text-tinta lg:text-[1.625rem]">
                  {titulo}
                </h2>
                {bajada ? <p className="mt-1 text-[0.9375rem] leading-relaxed text-tinta-suave">{bajada}</p> : null}
              </div>
              <button
                type="button"
                onClick={onCerrar}
                disabled={!cerrable}
                aria-label="Cerrar"
                className="-mr-2 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-tinta-suave hover:bg-superficie-2 hover:text-tinta disabled:opacity-40"
              >
                <X aria-hidden="true" className="h-5 w-5" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 lg:px-8 lg:py-6">{children}</div>
            {pie ? (
              <footer className="border-t border-linea bg-superficie px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] lg:px-8">
                {pie}
              </footer>
            ) : null}
          </div>
        </div>
      ) : null}
    </dialog>
  );
}

/** Los nombres de la spec: es la misma hoja, que se coloca sola segun el ancho. */
export const HojaLateral = Hoja;
export const HojaInferior = Hoja;
