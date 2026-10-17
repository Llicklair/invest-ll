"use client";

import { TriangleAlert, Check, ChevronRight, Copy, Info, OctagonAlert, RotateCw } from "lucide-react";
import Link from "next/link";
import {
  Fragment,
  useEffect,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type ComponentProps,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import type { ErrorApi } from "@/api/cliente";

/**
 * Las piezas basicas del panel v2 (docs/panel-v2.md, seccion 8): tarjetas de radio 16 con
 * sombra muy suave, botones de 48 px y un solo primario relleno por pantalla, espacio en
 * multiplos de 8. Los nombres de antes (Aviso, Seccion, Metrica...) se conservan para que el
 * Laboratorio siga funcionando con el estilo nuevo.
 */
export function clases(...partes: (string | false | null | undefined)[]): string {
  return partes.filter(Boolean).join(" ");
}

// -- Superficies --------------------------------------------------------------------------------

export function Tarjeta({
  children,
  className,
  como = "div",
  ...resto
}: {
  children: ReactNode;
  className?: string;
  como?: "div" | "section" | "article" | "li";
} & Omit<ComponentProps<"div">, "children" | "className" | "ref">) {
  // Las cuatro etiquetas aceptan los mismos atributos de HTML que un div.
  const Como = como as "div";
  return (
    <Como className={clases("rounded-tarjeta border border-linea bg-superficie shadow-suave", className)} {...resto}>
      {children}
    </Como>
  );
}

/** Encabezado de pagina: titular en Fraunces y una frase que dice para que sirve. */
export function Encabezado({
  titulo,
  bajada,
  accion,
  antetitulo,
}: {
  titulo: ReactNode;
  bajada?: ReactNode;
  accion?: ReactNode;
  antetitulo?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-2xl">
        {antetitulo ? <p className="mb-2 text-sm font-medium text-tinta-suave">{antetitulo}</p> : null}
        <h1 className="titular text-[2rem] leading-tight font-semibold text-tinta lg:text-[2.5rem]">{titulo}</h1>
        {bajada ? <p className="mt-2 text-base leading-relaxed text-tinta-suave lg:text-lg">{bajada}</p> : null}
      </div>
      {accion}
    </header>
  );
}

// -- Avisos -------------------------------------------------------------------------------------

export type TipoAviso = "critico" | "aviso" | "info" | "hecho";

const ESTILO_AVISO: Record<TipoAviso, string> = {
  critico: "bg-real-suave text-real-tinta border-real/40",
  aviso: "bg-pruebas-suave text-pruebas-tinta border-pruebas/40",
  info: "bg-marca-suave text-marca border-marca/20",
  hecho: "bg-sube-suave text-sube-texto border-sube/30",
};

const ETIQUETA_AVISO: Record<TipoAviso, string> = {
  critico: "Importante",
  aviso: "Atención",
  info: "Nota",
  hecho: "Hecho",
};

const ICONO_AVISO = { critico: OctagonAlert, aviso: TriangleAlert, info: Info, hecho: Check } as const;

/**
 * Un aviso con icono y etiqueta (para lectores de pantalla): el color nunca es lo unico que
 * dice que tipo de aviso es.
 */
export function Aviso({
  tipo,
  children,
  className,
  vivo = false,
  titulo,
}: {
  tipo: TipoAviso;
  children?: ReactNode;
  className?: string;
  /** Anunciarlo al aparecer (resultado de una accion). */
  vivo?: boolean;
  titulo?: ReactNode;
}) {
  const Icono = ICONO_AVISO[tipo];
  return (
    <div
      className={clases("flex gap-3 rounded-xl border px-4 py-3 text-[0.9375rem] leading-relaxed", ESTILO_AVISO[tipo], className)}
      role={vivo ? (tipo === "critico" ? "alert" : "status") : undefined}
    >
      <Icono aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" strokeWidth={1.75} />
      {/* Un aviso puede traer una URL o un simbolo largo sin espacios: se parte donde haga falta
          en vez de ensanchar la pagina (en el movil la llevaba a 600 px). */}
      <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
        <span className="sr-only">{ETIQUETA_AVISO[tipo]}: </span>
        {titulo ? <p className="font-semibold">{titulo}</p> : null}
        {children ? <div className={titulo ? "mt-0.5" : undefined}>{children}</div> : null}
      </div>
    </div>
  );
}

/**
 * El error de la API, con su `detail` tal cual (contrato v2.1: siempre un texto en llano), y un
 * reintento si se puede. El codigo HTTP no es para quien usa el panel: va en un atributo, para
 * quien lo depure.
 */
export function ErrorApiVista({
  error,
  prefijo,
  className,
  reintentar,
}: {
  error: ErrorApi;
  prefijo?: string;
  className?: string;
  reintentar?: () => void;
}) {
  return (
    <div data-http={error.estado ?? "sin-respuesta"} className={className}>
      <Aviso tipo="critico" vivo>
        {prefijo ? <span className="font-semibold">{prefijo} </span> : null}
        {/* Los `comandos` entre comillas invertidas (p. ej. `claude login`) se ven como codigo. */}
        <span className="whitespace-pre-wrap">
          <TextoApi texto={error.detalle} />
        </span>
        {reintentar ? (
          <button
            type="button"
            onClick={reintentar}
            className="mt-2 flex min-h-11 items-center gap-1.5 font-semibold underline underline-offset-4"
          >
            <RotateCw aria-hidden="true" className="h-4 w-4" /> Volver a intentarlo
          </button>
        ) : null}
      </Aviso>
    </div>
  );
}

// -- Texto --------------------------------------------------------------------------------------

export function Nota({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={clases("text-sm leading-relaxed text-tinta-suave", className)}>{children}</p>;
}

export function Codigo({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-md bg-superficie-2 px-1.5 py-0.5 font-mono text-[0.85em] break-words text-tinta">
      {children}
    </code>
  );
}

/**
 * Un texto de la API con `comandos` entre comillas invertidas. Solo se interpreta eso (nunca
 * HTML); si las comillas no casan, va tal cual.
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
        "overflow-x-auto rounded-xl border border-linea bg-superficie-2 p-4 font-mono text-[0.8rem] leading-relaxed break-words whitespace-pre-wrap text-tinta",
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
      <TextoPlano className="pr-28">{texto}</TextoPlano>
      <button
        type="button"
        className="absolute top-2 right-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-linea bg-superficie px-3 text-sm text-tinta-suave hover:text-tinta"
        onClick={() => {
          navigator.clipboard?.writeText(texto).then(
            () => setCopiado(true),
            () => setCopiado(false),
          );
        }}
      >
        {copiado ? <Check aria-hidden="true" className="h-4 w-4" /> : <Copy aria-hidden="true" className="h-4 w-4" />}
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
  bajada,
}: {
  titulo: ReactNode;
  children: ReactNode;
  nivel?: 2 | 3;
  accion?: ReactNode;
  className?: string;
  id?: string;
  bajada?: ReactNode;
}) {
  const Encab = nivel === 2 ? "h2" : "h3";
  const idTitulo = id ? `${id}-titulo` : undefined;
  return (
    <section className={clases("scroll-mt-24 space-y-4", className)} aria-labelledby={idTitulo} id={id}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <Encab
            id={idTitulo}
            className={
              nivel === 2
                ? "titular text-[1.375rem] leading-snug font-semibold text-tinta lg:text-2xl"
                : "text-base font-semibold text-tinta"
            }
          >
            {titulo}
          </Encab>
          {bajada ? <p className="mt-1 text-[0.9375rem] leading-relaxed text-tinta-suave">{bajada}</p> : null}
        </div>
        {accion}
      </div>
      {children}
    </section>
  );
}

export function Separador() {
  return <hr className="my-10 border-0 border-t border-linea" />;
}

/** Plegable accesible (details/summary nativo): para lo secundario o avanzado. */
export function Desplegable({
  resumen,
  children,
  abierto,
  className,
}: {
  resumen: ReactNode;
  children: ReactNode;
  abierto?: boolean;
  className?: string;
}) {
  return (
    <details className={clases("group rounded-tarjeta border border-linea bg-superficie", className)} open={abierto}>
      <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-tarjeta px-4 py-3 text-[0.9375rem] font-medium text-tinta select-none hover:bg-superficie-2 [&::-webkit-details-marker]:hidden">
        <ChevronRight
          aria-hidden="true"
          className="h-4 w-4 shrink-0 text-tinta-suave transition-transform group-open:rotate-90"
        />
        <span className="min-w-0 flex-1">{resumen}</span>
      </summary>
      <div className="space-y-4 border-t border-linea p-4">{children}</div>
    </details>
  );
}

/** Una cifra con su etiqueta (Laboratorio). */
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
    <div className="rounded-xl border border-linea bg-superficie px-4 py-3">
      <div className="text-sm text-tinta-suave">{etiqueta}</div>
      <div className="mt-1 text-xl font-semibold text-tinta">{valor}</div>
      {detalle ? <div className="mt-1 text-sm text-tinta-suave">{detalle}</div> : null}
    </div>
  );
}

export function FilaMetricas({ children, columnas = 4 }: { children: ReactNode; columnas?: 2 | 3 | 4 }) {
  const grid = { 2: "grid-cols-2", 3: "grid-cols-1 sm:grid-cols-3", 4: "grid-cols-2 lg:grid-cols-4" }[columnas];
  return <div className={clases("grid gap-3", grid)}>{children}</div>;
}

export function Cargando({ texto = "Cargando…", className }: { texto?: string; className?: string }) {
  return (
    <p className={clases("flex items-center gap-2.5 text-[0.9375rem] text-tinta-suave", className)} role="status" aria-live="polite">
      <span
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-linea border-t-marca"
        aria-hidden="true"
      />
      {texto}
    </p>
  );
}

/**
 * Una carga que puede tardar (las estrategias se calculan en frio la primera vez: ~25 s). Al
 * principio es un "Cargando" normal; si pasa de unos segundos, explica por que y cuenta el tiempo,
 * para que no parezca colgado.
 */
export function CargandoLento({
  texto,
  lento,
  className,
  tras = 3,
}: {
  texto: string;
  /** Lo que se dice cuando ya esta tardando. */
  lento: string;
  className?: string;
  tras?: number;
}) {
  const [inicio] = useState(() => Date.now());
  const [ahora, setAhora] = useState(inicio);
  useEffect(() => {
    const t = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const segundos = Math.round((ahora - inicio) / 1000);
  if (segundos < tras) return <Cargando texto={texto} className={className} />;
  return (
    <div className={clases("rounded-xl bg-superficie-2 px-4 py-4", className)} role="status" aria-live="polite">
      <Cargando texto={lento} />
      <p className="mt-1 pl-[26px] text-sm text-tinta-suave">Lleva {segundos} s.</p>
    </div>
  );
}

/** Bloques grises con la forma de lo que va a llegar (solo en la primera carga, nunca al recargar). */
export function Esqueleto({ className }: { className?: string }) {
  return <div aria-hidden="true" className={clases("animate-pulse rounded-xl bg-superficie-2", className)} />;
}

export function Chip({
  children,
  tono = "neutro",
  className,
  icono,
}: {
  children: ReactNode;
  tono?: "neutro" | "marca" | "destaque" | "sube" | "baja" | "pruebas" | "real";
  className?: string;
  icono?: ReactNode;
}) {
  const estilo = {
    neutro: "bg-superficie-2 text-tinta-suave",
    marca: "bg-marca-suave text-marca",
    destaque: "bg-destaque-suave text-destaque-tinta",
    sube: "bg-sube-suave text-sube-texto",
    baja: "bg-baja-suave text-baja-texto",
    pruebas: "bg-pruebas-suave text-pruebas-tinta",
    real: "bg-real-suave text-real-tinta",
  }[tono];
  return (
    <span
      className={clases(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.8125rem] leading-none font-medium whitespace-nowrap",
        estilo,
        className,
      )}
    >
      {icono}
      {children}
    </span>
  );
}

// -- Botones -------------------------------------------------------------------------------------

type Variante = "primario" | "secundario" | "peligro" | "fantasma" | "real";
type Tamano = "normal" | "compacto";

const ESTILO_BOTON: Record<Variante, string> = {
  primario: "bg-marca text-marca-tinta hover:bg-marca-hover border-transparent shadow-sm",
  secundario: "bg-superficie text-tinta border-linea-control/60 hover:bg-superficie-2",
  peligro: "bg-superficie text-real-tinta border-real/50 hover:bg-real-suave",
  fantasma: "bg-transparent text-marca border-transparent hover:bg-marca-suave",
  real: "bg-real text-real-boton-tinta hover:bg-real-hover border-transparent shadow-sm",
};

const TAMANO_BOTON: Record<Tamano, string> = {
  normal: "min-h-12 px-5 text-[0.9375rem]",
  compacto: "min-h-11 px-4 text-sm",
};

export function estiloBoton(variante: Variante = "secundario", tamano: Tamano = "normal", className?: string): string {
  return clases(
    "inline-flex items-center justify-center gap-2 rounded-xl border font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-45",
    ESTILO_BOTON[variante],
    TAMANO_BOTON[tamano],
    className,
  );
}

export function Boton({
  variante = "secundario",
  tamano = "normal",
  className,
  type = "button",
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; tamano?: Tamano }) {
  return <button type={type} className={estiloBoton(variante, tamano, className)} {...resto} />;
}

/** Un enlace con aspecto de boton (navegar no es una accion: sigue siendo un <a>). */
export function BotonEnlace({
  href,
  variante = "secundario",
  tamano = "normal",
  className,
  children,
}: {
  href: string;
  variante?: Variante;
  tamano?: Tamano;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={estiloBoton(variante, tamano, className)}>
      {children}
    </Link>
  );
}

/** Enlace de texto con flecha: "Ver todo →". */
export function EnlaceFlecha({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link
      href={href}
      className={clases(
        "inline-flex min-h-11 items-center gap-1 text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline",
        className,
      )}
    >
      {children}
      <ChevronRight aria-hidden="true" className="h-4 w-4" />
    </Link>
  );
}

// -- Campos --------------------------------------------------------------------------------------

export const ESTILO_ENTRADA =
  "w-full min-h-12 rounded-xl border border-linea-control/70 bg-superficie px-3.5 py-2 text-base text-tinta placeholder:text-tinta-suave/70 disabled:opacity-60 aria-[invalid=true]:border-real hover:border-linea-control";

export function CampoTexto({
  etiqueta,
  ayuda,
  error,
  className,
  sufijo,
  ...resto
}: InputHTMLAttributes<HTMLInputElement> & {
  etiqueta: ReactNode;
  ayuda?: ReactNode;
  error?: string | null;
  sufijo?: ReactNode;
}) {
  const id = useId();
  const idAyuda = `${id}-ayuda`;
  const idError = `${id}-error`;
  const describe = [ayuda ? idAyuda : null, error ? idError : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={clases("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-[0.9375rem] font-medium text-tinta">
        {etiqueta}
      </label>
      <div className="relative">
        <input
          id={id}
          className={clases(ESTILO_ENTRADA, sufijo ? "pr-12" : undefined)}
          aria-describedby={describe}
          aria-invalid={error ? true : undefined}
          {...resto}
        />
        {sufijo ? (
          <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-tinta-suave" aria-hidden="true">
            {sufijo}
          </span>
        ) : null}
      </div>
      {ayuda ? (
        <p id={idAyuda} className="text-sm text-tinta-suave">
          {ayuda}
        </p>
      ) : null}
      {error ? (
        <p id={idError} className="text-sm font-medium text-real-tinta">
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
    <div className={clases("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-[0.9375rem] font-medium text-tinta">
        {etiqueta}
      </label>
      <select id={id} className={ESTILO_ENTRADA} aria-describedby={ayuda ? `${id}-ayuda` : undefined} {...resto}>
        {children}
      </select>
      {ayuda ? (
        <p id={`${id}-ayuda`} className="text-sm text-tinta-suave">
          {ayuda}
        </p>
      ) : null}
    </div>
  );
}

/** Un deslizador con su valor a la vista. */
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
    <div className={clases("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="flex justify-between gap-2 text-[0.9375rem] font-medium text-tinta">
        <span>{etiqueta}</span>
        <output htmlFor={id} className="cifras text-tinta-suave">
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
        className="h-11 w-full accent-[var(--marca)]"
      />
    </div>
  );
}

/** Grupo de opciones excluyentes como control segmentado (radios nativos: flechas del teclado). */
export function Segmentado<V extends string>({
  etiqueta,
  opciones,
  valor,
  onCambio,
  ocultarEtiqueta = false,
  className,
  repartido = false,
}: {
  etiqueta: string;
  opciones: readonly { valor: V; texto: string }[];
  valor: V;
  onCambio: (v: V) => void;
  ocultarEtiqueta?: boolean;
  className?: string;
  /** Todas las opciones en una fila de columnas iguales (p. ej. los anos): no se parten en dos lineas. */
  repartido?: boolean;
}) {
  const nombre = useId();
  return (
    <fieldset className={clases("min-w-0", className)}>
      <legend className={ocultarEtiqueta ? "sr-only" : "mb-2 text-[0.9375rem] font-medium text-tinta"}>{etiqueta}</legend>
      <div
        className={clases("gap-1 rounded-xl bg-superficie-2 p-1", repartido ? "grid w-full max-w-xl" : "inline-flex max-w-full flex-wrap")}
        style={repartido ? { gridTemplateColumns: `repeat(${opciones.length}, minmax(0, 1fr))` } : undefined}
      >
        {opciones.map((o) => {
          const activo = o.valor === valor;
          return (
            <label
              key={o.valor}
              className={clases(
                "inline-flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-3.5 max-sm:px-2 text-[0.9375rem] has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foco",
                activo ? "bg-superficie font-semibold text-tinta shadow-sm ring-1 ring-linea-control/30" : "text-tinta-suave hover:text-tinta",
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
