import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

import type { Celda, Tabla } from "@/api/tipos";
import { esSoloDia, fecha, momento, noEsCero, numero, porcentaje, signo, SIN_DATO } from "@/lib/formato";

import { clases } from "./ui";

/**
 * Caja de una tabla densa: hace scroll por dentro (en el movil la pagina no se desplaza de lado)
 * y se puede recorrer con el teclado.
 */
export function MarcoTabla({
  etiqueta,
  children,
  altoMaximo,
}: {
  etiqueta: string;
  children: ReactNode;
  altoMaximo?: number;
}) {
  return (
    <div
      role="region"
      aria-label={etiqueta}
      tabIndex={0}
      // `relative`: los textos sr-only de las celdas son absolutos; sin un ancestro posicionado
      // escaparian del recorte y ensancharian la pagina en el movil.
      className="relative overflow-auto rounded-md border border-linea bg-superficie"
      style={altoMaximo ? { maxHeight: altoMaximo } : undefined}
    >
      <table className="tabla-densa cifras w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Th({
  children,
  numerica = false,
  className,
  ...resto
}: ThHTMLAttributes<HTMLTableCellElement> & { numerica?: boolean }) {
  return (
    <th
      scope="col"
      className={clases(
        "border-b border-linea px-2.5 py-1.5 text-xs font-semibold whitespace-nowrap text-tinta-suave",
        numerica ? "text-right" : "text-left",
        className,
      )}
      {...resto}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  numerica = false,
  className,
  ...resto
}: TdHTMLAttributes<HTMLTableCellElement> & { numerica?: boolean }) {
  return (
    <td
      className={clases("border-b border-linea px-2.5 py-1 whitespace-nowrap", numerica && "text-right", className)}
      {...resto}
    >
      {children}
    </td>
  );
}

/**
 * Celda de variacion: la UNICA que lleva color (verde sube, rojo baja), y siempre con signo, asi
 * que el color nunca es lo unico que lo dice. `null` es "no hay historico suficiente", no un 0%.
 */
export function TdVariacion({
  valor,
  texto,
  className,
}: {
  valor: number | null | undefined;
  /** Texto ya formateado; por defecto, porcentaje con un decimal. */
  texto?: string;
  className?: string;
}) {
  const visible = texto ?? porcentaje(valor, 1);
  // Lo que se ve manda: un "0,00 %" es neutro aunque el dato fuera 0,0001.
  const s = signo(valor) === null ? null : noEsCero(visible) ? signo(valor) : 0;
  return (
    <Td
      numerica
      className={clases(
        s === 1 && "text-sube",
        s === -1 && "text-baja",
        s === null && "text-tinta-suave",
        className,
      )}
    >
      {s === null ? (
        <>
          <span aria-hidden="true">{SIN_DATO}</span>
          <span className="sr-only">sin histórico suficiente</span>
        </>
      ) : (
        visible
      )}
    </Td>
  );
}

function celdaComoTexto(valor: Celda): string {
  if (valor === null) return SIN_DATO;
  if (typeof valor === "boolean") return valor ? "sí" : "no";
  if (typeof valor === "number") return Number.isInteger(valor) ? numero(valor, 0) : numero(valor, Math.abs(valor) < 1 ? 3 : 2);
  if (/^\d{4}-\d{2}-\d{2}T/.test(valor)) return esSoloDia(valor) ? fecha(valor) : momento(valor);
  return valor;
}

/** Una `Tabla` generica del contrato (metricas, registro de operaciones...), tal cual llega. */
export function TablaContrato({ tabla, etiqueta, altoMaximo }: { tabla: Tabla; etiqueta: string; altoMaximo?: number }) {
  const numericas = tabla.columnas.map((_, i) => tabla.filas.some((f) => typeof f[i] === "number"));
  return (
    <MarcoTabla etiqueta={etiqueta} altoMaximo={altoMaximo}>
      <thead>
        <tr>
          {tabla.columnas.map((c, i) => (
            <Th key={c} numerica={numericas[i]}>
              {c}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {tabla.filas.map((fila, i) => (
          <tr key={i}>
            {fila.map((celda, j) => (
              <Td key={j} numerica={numericas[j]}>
                {celdaComoTexto(celda)}
              </Td>
            ))}
          </tr>
        ))}
        {tabla.filas.length === 0 ? (
          <tr>
            <Td colSpan={tabla.columnas.length} className="text-tinta-suave">
              Sin filas.
            </Td>
          </tr>
        ) : null}
      </tbody>
    </MarcoTabla>
  );
}
