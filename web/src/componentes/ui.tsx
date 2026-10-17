"use client";

import {
  Fragment,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import type { ErrorApi } from "@/api/cliente";

function clases(...partes: (string | false | null | undefined)[]): string {
  return partes.filter(Boolean).join(" ");
}

export { clases };

// -- Iconos (forma distinta por tipo: el color nunca va solo) ------------------------------------

function IconoAviso() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" fill="none">
      <path d="M10 2.5 18.5 17h-17L10 2.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M10 8v4.2M10 14.6v.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconoCritico() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" fill="none">
      <path
        d="M6.7 2h6.6L18 6.7v6.6L13.3 18H6.7L2 13.3V6.7L6.7 2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M10 5.8v5M10 13.6v.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconoInfo() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" fill="none">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 9v5M10 6.2v.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconoHecho() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" fill="none">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="m6.2 10.2 2.6 2.6 5-5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// -- Avisos -------------------------------------------------------------------------------------

export type TipoAviso = "critico" | "aviso" | "info" | "hecho";

const ESTILO_AVISO: Record<TipoAviso, string> = {
  critico: "bg-critico-fondo text-critico-tinta border-critico-borde",
  aviso: "bg-aviso-fondo text-aviso-tinta border-aviso-borde",
  info: "bg-info-fondo text-info-tinta border-info-borde",
  hecho: "bg-ok-fondo text-ok-tinta border-ok-borde",
};

const ETIQUETA_AVISO: Record<TipoAviso, string> = {
  critico: "Importante",
  aviso: "Atención",
  info: "Nota",
  hecho: "Hecho",
};

/**
 * Un aviso con icono y etiqueta (para lectores de pantalla): el color nunca es lo unico que
 * dice que tipo de aviso es.
 */
export function Aviso({
  tipo,
  children,
  className,
  vivo = false,
}: {
  tipo: TipoAviso;
  children: ReactNode;
  className?: string;
  /** Anunciarlo al aparecer (resultado de una accion). */
  vivo?: boolean;
}) {
  const Icono = { critico: IconoCritico, aviso: IconoAviso, info: IconoInfo, hecho: IconoHecho }[tipo];
  return (
    <div
      className={clases(
        "flex gap-2.5 rounded-md border-l-4 px-3 py-2.5 text-sm leading-relaxed",
        ESTILO_AVISO[tipo],
        className,
      )}
      role={vivo ? (tipo === "critico" ? "alert" : "status") : undefined}
    >
      <Icono />
      <div className="min-w-0 flex-1">
        <span className="sr-only">{ETIQUETA_AVISO[tipo]}: </span>
        {children}
      </div>
    </div>
  );
}

/** El error de la API, con su `detail` tal cual. */
export function ErrorApiVista({
  error,
  prefijo,
  className,
}: {
  error: ErrorApi;
  prefijo?: string;
  className?: string;
}) {
  return (
    <Aviso tipo="critico" vivo className={className}>
      {prefijo ? <span className="font-semibold">{prefijo} </span> : null}
      <span className="whitespace-pre-wrap break-words">{error.detalle}</span>
      <span className="ml-2 text-xs opacity-80">
        {error.estado === null ? "(sin respuesta de la API)" : `(HTTP ${error.estado})`}
      </span>
    </Aviso>
  );
}

// -- Texto --------------------------------------------------------------------------------------

/** Lo que en Streamlit era `st.caption`: explicacion en tinta secundaria. */
export function Nota({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={clases("text-sm leading-relaxed text-tinta-2", className)}>{children}</p>;
}

export function Codigo({ children }: { children: ReactNode }) {
  return (
    <code className="rounded bg-superficie-2 px-1 py-0.5 font-mono text-[0.85em] text-tinta">
      {children}
    </code>
  );
}

/**
 * Un texto de la API con `comandos` entre comillas invertidas, que el panel de Streamlit pintaba
 * como Markdown. Solo se interpreta eso (nunca HTML); si las comillas no casan, va tal cual.
 */
export function TextoApi({ texto }: { texto: string }) {
  const partes = texto.split("`");
  if (partes.length < 3 || partes.length % 2 === 0) return <>{texto}</>;
  return (
    <>
      {partes.map((p, i) => (i % 2 === 1 ? <Codigo key={i}>{p}</Codigo> : <Fragment key={i}>{p}</Fragment>))}
    </>
  );
}

/** Texto preformateado (informes de texto, comandos). Hace saltar las lineas largas. */
export function TextoPlano({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <pre
      className={clases(
        "overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-borde bg-superficie p-3 font-mono text-[0.8rem] leading-relaxed text-tinta",
        className,
      )}
    >
      {children}
    </pre>
  );
}

/** Comandos para copiar y ejecutar fuera del panel. */
export function BloqueComandos({ lineas }: { lineas: string[] }) {
  const [copiado, setCopiado] = useState(false);
  const texto = lineas.join("\n");
  return (
    <div className="relative">
      <TextoPlano className="pr-24">{texto}</TextoPlano>
      <button
        type="button"
        className="absolute top-2 right-2 rounded border border-borde bg-superficie-2 px-2 py-1 text-xs text-tinta-2 hover:bg-superficie-3"
        onClick={() => {
          navigator.clipboard?.writeText(texto).then(
            () => setCopiado(true),
            () => setCopiado(false),
          );
        }}
      >
        {copiado ? "Copiado" : "Copiar"}
      </button>
    </div>
  );
}

// -- Estructura ----------------------------------------------------------------------------------

export function Seccion({
  titulo,
  children,
  nivel = 2,
  accion,
  className,
  id,
}: {
  titulo: ReactNode;
  children: ReactNode;
  nivel?: 2 | 3;
  accion?: ReactNode;
  className?: string;
  id?: string;
}) {
  const Encabezado = nivel === 2 ? "h2" : "h3";
  return (
    <section className={clases("space-y-3", className)} aria-labelledby={id}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Encabezado
          id={id}
          className={nivel === 2 ? "text-lg font-semibold text-tinta" : "text-base font-semibold text-tinta"}
        >
          {titulo}
        </Encabezado>
        {accion}
      </div>
      {children}
    </section>
  );
}

export function Separador() {
  return <hr className="my-8 border-0 border-t border-borde" />;
}

export function Desplegable({
  resumen,
  children,
  abierto,
}: {
  resumen: ReactNode;
  children: ReactNode;
  abierto?: boolean;
}) {
  return (
    <details className="group rounded-md border border-borde bg-superficie" open={abierto}>
      <summary className="cursor-pointer list-none rounded-md px-3 py-2 text-sm font-medium text-tinta select-none hover:bg-superficie-2">
        <span className="mr-2 inline-block text-tinta-3 transition-transform group-open:rotate-90" aria-hidden="true">
          ▸
        </span>
        {resumen}
      </summary>
      <div className="space-y-3 border-t border-borde p-3">{children}</div>
    </details>
  );
}

/** Una cifra con su etiqueta (stat tile): cifras proporcionales, no tabulares. */
export function Metrica({
  etiqueta,
  valor,
  detalle,
}: {
  etiqueta: ReactNode;
  valor: ReactNode;
  detalle?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-borde bg-superficie px-3 py-2.5">
      <div className="text-xs text-tinta-2">{etiqueta}</div>
      <div className="mt-0.5 text-xl font-semibold text-tinta">{valor}</div>
      {detalle ? <div className="mt-0.5 text-xs text-tinta-2">{detalle}</div> : null}
    </div>
  );
}

export function FilaMetricas({ children, columnas = 4 }: { children: ReactNode; columnas?: 2 | 3 | 4 }) {
  const grid = { 2: "grid-cols-2", 3: "grid-cols-1 sm:grid-cols-3", 4: "grid-cols-2 lg:grid-cols-4" }[columnas];
  return <div className={clases("grid gap-2", grid)}>{children}</div>;
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-tinta-2" role="status" aria-live="polite">
      <span
        className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-eje border-t-acento"
        aria-hidden="true"
      />
      {texto}
    </p>
  );
}

// -- Controles -----------------------------------------------------------------------------------

type Variante = "primario" | "secundario" | "peligro";

const ESTILO_BOTON: Record<Variante, string> = {
  primario: "bg-acento text-acento-tinta hover:bg-acento-hover border-transparent",
  secundario: "bg-superficie text-tinta border-borde hover:bg-superficie-2",
  peligro: "bg-peligro text-white hover:bg-peligro-hover border-transparent",
};

export function Boton({
  variante = "secundario",
  className,
  type = "button",
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante }) {
  return (
    <button
      type={type}
      className={clases(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3.5 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        ESTILO_BOTON[variante],
        className,
      )}
      {...resto}
    />
  );
}

const ESTILO_ENTRADA =
  "w-full rounded-md border border-borde bg-superficie px-2.5 py-1.5 text-sm text-tinta placeholder:text-tinta-3 disabled:opacity-60 aria-[invalid=true]:border-critico-borde";

export function CampoTexto({
  etiqueta,
  ayuda,
  error,
  className,
  ...resto
}: InputHTMLAttributes<HTMLInputElement> & { etiqueta: ReactNode; ayuda?: ReactNode; error?: string | null }) {
  const id = useId();
  const idAyuda = `${id}-ayuda`;
  const idError = `${id}-error`;
  const describe = [ayuda ? idAyuda : null, error ? idError : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={clases("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-medium text-tinta">
        {etiqueta}
      </label>
      <input id={id} className={ESTILO_ENTRADA} aria-describedby={describe} aria-invalid={error ? true : undefined} {...resto} />
      {ayuda ? (
        <p id={idAyuda} className="text-xs text-tinta-2">
          {ayuda}
        </p>
      ) : null}
      {error ? (
        <p id={idError} className="text-xs text-critico-tinta">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function Selector({
  etiqueta,
  ayuda,
  className,
  children,
  ...resto
}: SelectHTMLAttributes<HTMLSelectElement> & { etiqueta: ReactNode; ayuda?: ReactNode }) {
  const id = useId();
  return (
    <div className={clases("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-medium text-tinta">
        {etiqueta}
      </label>
      <select id={id} className={ESTILO_ENTRADA} aria-describedby={ayuda ? `${id}-ayuda` : undefined} {...resto}>
        {children}
      </select>
      {ayuda ? (
        <p id={`${id}-ayuda`} className="text-xs text-tinta-2">
          {ayuda}
        </p>
      ) : null}
    </div>
  );
}

/** Un deslizador con su valor a la vista (lo que en Streamlit era `st.slider`). */
export function Deslizador({
  etiqueta,
  valor,
  min,
  max,
  paso,
  formato,
  onCambio,
  className,
}: {
  etiqueta: ReactNode;
  valor: number;
  min: number;
  max: number;
  paso: number;
  formato?: (v: number) => string;
  onCambio: (v: number) => void;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={clases("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="flex justify-between gap-2 text-sm font-medium text-tinta">
        <span>{etiqueta}</span>
        <output htmlFor={id} className="cifras text-tinta-2">
          {formato ? formato(valor) : valor}
        </output>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={paso}
        value={valor}
        onChange={(e) => onCambio(Number(e.target.value))}
        className="w-full accent-[var(--acento)]"
      />
    </div>
  );
}

/** Grupo de opciones excluyentes como control segmentado (radio accesible). */
export function Segmentado<V extends string>({
  etiqueta,
  opciones,
  valor,
  onCambio,
  ocultarEtiqueta = false,
}: {
  etiqueta: string;
  opciones: readonly { valor: V; texto: string }[];
  valor: V;
  onCambio: (v: V) => void;
  ocultarEtiqueta?: boolean;
}) {
  const nombre = useId();
  return (
    <fieldset className="min-w-0">
      <legend className={ocultarEtiqueta ? "sr-only" : "mb-1 text-sm font-medium text-tinta"}>{etiqueta}</legend>
      <div className="flex flex-wrap gap-1 rounded-md border border-borde bg-superficie-2 p-1">
        {opciones.map((o) => {
          const activo = o.valor === valor;
          return (
            <label
              key={o.valor}
              className={clases(
                "cursor-pointer rounded px-3 py-1 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-foco",
                activo ? "bg-superficie font-semibold text-tinta shadow-sm" : "text-tinta-2 hover:text-tinta",
              )}
            >
              <input
                type="radio"
                name={nombre}
                value={o.valor}
                checked={activo}
                onChange={() => onCambio(o.valor)}
                className="sr-only"
              />
              {o.texto}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
