import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { clases } from "./ui";

/**
 * Un estado vacio que es BUENO, no triste: "no toca hacer nada" es lo normal la mayor parte del
 * tiempo y se dice con calma (docs/panel-v2.md, principio 6). Sin ilustraciones ni confeti.
 */
export function EstadoVacio({
  icono: Icono,
  titulo,
  children,
  accion,
  tono = "calma",
  className,
}: {
  icono: LucideIcon;
  titulo: ReactNode;
  children?: ReactNode;
  accion?: ReactNode;
  /** "calma": todo en orden. "neutro": falta algo por hacer (sin plan, sin datos). */
  tono?: "calma" | "neutro";
  className?: string;
}) {
  return (
    <div
      className={clases(
        "flex flex-col items-start gap-4 rounded-tarjeta border px-6 py-7 sm:flex-row sm:items-center sm:gap-5",
        tono === "calma" ? "border-sube/20 bg-sube-suave/60" : "border-linea bg-superficie",
        className,
      )}
    >
      <span
        className={clases(
          "flex h-12 w-12 shrink-0 items-center justify-center rounded-full",
          tono === "calma" ? "bg-superficie text-sube-texto" : "bg-marca-suave text-marca",
        )}
        aria-hidden="true"
      >
        <Icono className="h-6 w-6" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="titular text-xl font-semibold text-tinta">{titulo}</p>
        {children ? <div className="mt-1 text-[0.9375rem] leading-relaxed text-tinta-suave">{children}</div> : null}
      </div>
      {accion ? <div className="shrink-0">{accion}</div> : null}
    </div>
  );
}
