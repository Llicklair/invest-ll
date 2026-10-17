import { clases } from "./ui";

const PALABRAS = ["Tranquila", "Suave", "Moderada", "Movida", "Muy movida"] as const;
const COLORES = ["var(--riesgo-1)", "var(--riesgo-2)", "var(--riesgo-3)", "var(--riesgo-4)", "var(--riesgo-5)"] as const;

/**
 * Riesgo de 1 a 5 en cinco segmentos y SIEMPRE con su palabra: el color y el numero de
 * segmentos acompanan, la palabra es lo que se lee. Los rellenos llevan el color del nivel; los
 * vacios, la linea neutra (2 px de hueco entre ellos, como pide la skill dataviz).
 */
export function MedidorRiesgo({
  nivel,
  texto,
  className,
  compacto = false,
}: {
  nivel: number;
  /** La palabra que manda la API; si no llega, la de la escala. */
  texto?: string;
  className?: string;
  compacto?: boolean;
}) {
  const n = Math.min(5, Math.max(1, Math.round(nivel)));
  const palabra = texto ?? PALABRAS[n - 1];
  const color = COLORES[n - 1];
  return (
    <div className={clases("flex items-center gap-2.5", className)}>
      <span className="flex gap-[3px]" aria-hidden="true">
        {COLORES.map((_, i) => (
          <span
            key={i}
            className={clases("rounded-full", compacto ? "h-1.5 w-3.5" : "h-2 w-5")}
            style={{ background: i < n ? color : "var(--linea)" }}
          />
        ))}
      </span>
      <span className={clases("font-medium text-tinta", compacto ? "text-sm" : "text-[0.9375rem]")}>
        {palabra}
        <span className="sr-only">: riesgo {n} de 5</span>
      </span>
    </div>
  );
}
