"use client";

import { Bot, ChartCandlestick, ChartLine, Compass, HandCoins, House, LayoutGrid, Microscope, Settings, Wallet, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { API_BASE, MODO_EJEMPLO } from "@/api/cliente";
import { useModo } from "@/contexto/modo";
import { useGuardado } from "@/lib/almacen";

import { PildoraModo } from "./PildoraModo";
import { Pregunta } from "./Pregunta";
import { Aviso, clases } from "./ui";

interface Destino {
  ruta: string;
  texto: string;
  icono: LucideIcon;
}

/** Las cuatro secciones del camino (docs/panel-v2.md, seccion 3), en el orden en que se usan. */
export const PRINCIPAL: readonly (Destino & { bajada: string })[] = [
  { ruta: "/", texto: "Inicio", icono: House, bajada: "Tu dinero hoy y qué toca hacer" },
  { ruta: "/estrategias/", texto: "Estrategias", icono: Compass, bajada: "Cómo invertir, sin jerga" },
  { ruta: "/invertir/", texto: "Invertir", icono: HandCoins, bajada: "Qué toca hoy, en Binance y en tu bróker" },
  { ruta: "/cartera/", texto: "Cartera", icono: Wallet, bajada: "Lo que tienes, lo que vendiste y tus movimientos" },
];

/**
 * Panel v3 (docs/panel-v3-vivo.md, seccion 4): en vivo y con dinero ficticio. Van DESPUES del
 * camino de Laura (quien no sabe empieza por Estrategias) y juntas, con su rotulo, para quien ya
 * juega. Bots antes que Operar: mirar a un bot frente a "solo mantener" es el paso suave;
 * comprar y vender a mano, el mas activo.
 */
export const EN_VIVO: readonly (Destino & { bajada: string })[] = [
  { ruta: "/bots/", texto: "Bots", icono: Bot, bajada: "Bots que operan solos, en vivo, frente a solo mantener" },
  { ruta: "/operar/", texto: "Operar", icono: ChartCandlestick, bajada: "Compra y vende a precios en vivo de Hyperliquid" },
];

/**
 * La barra inferior del movil tiene 5 huecos: Inicio y Estrategias (la puerta de quien no sabe),
 * Bots y Operar (la de quien ya juega) y "Más". Invertir y Cartera pasan a "Más" en el movil
 * porque Inicio ya lleva a los dos ("Qué toca hacer" y "Tu dinero hoy").
 */
const BARRA_MOVIL: readonly string[] = ["/", "/estrategias/", "/bots/", "/operar/"];

/** "Más": lo que no es el camino principal. */
export const MAS: readonly (Destino & { bajada: string })[] = [
  { ruta: "/mercado/", texto: "Mercado", icono: ChartLine, bajada: "Cómo van el oro, la bolsa o el bitcoin, con su fecha" },
  { ruta: "/laboratorio/", texto: "Laboratorio", icono: Microscope, bajada: "Para quien sabe: pruebas, investigación y alertas" },
  { ruta: "/ajustes/", texto: "Ajustes", icono: Settings, bajada: "Exchanges, el conector con Claude, tema y datos" },
];

function normalizar(ruta: string): string {
  return ruta.endsWith("/") ? ruta : `${ruta}/`;
}

function esActiva(actual: string, destino: string): boolean {
  const a = normalizar(actual);
  return destino === "/" ? a === "/" : a.startsWith(destino);
}

function Logo() {
  return (
    <Link href="/" className="inline-flex min-h-11 items-center gap-2.5 rounded-lg" aria-label="INVEST LL, ir a Inicio">
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" className="shrink-0">
        <rect width="30" height="30" rx="9" fill="var(--marca)" />
        <path d="M7 19.5 12 14l4 3.5 7-8" fill="none" stroke="var(--marca-tinta)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="23" cy="9.5" r="1.8" fill="var(--destaque)" />
      </svg>
      <span className="titular text-[1.1875rem] font-semibold tracking-tight text-tinta">INVEST LL</span>
    </Link>
  );
}

function EnlaceLateral({ d, activa, compacta }: { d: Destino; activa: boolean; compacta: boolean }) {
  const Icono = d.icono;
  if (compacta) {
    return (
      <li>
        <Link
          href={d.ruta}
          aria-current={activa ? "page" : undefined}
          className={clases(
            "flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[0.6875rem] leading-tight transition-colors",
            activa ? "bg-superficie font-semibold text-tinta shadow-suave" : "text-tinta-suave hover:bg-superficie-2 hover:text-tinta",
          )}
        >
          <Icono aria-hidden="true" className={clases("h-5 w-5", activa ? "text-marca" : undefined)} strokeWidth={1.75} />
          {d.texto}
        </Link>
      </li>
    );
  }
  return (
    <li>
      <Link
        href={d.ruta}
        aria-current={activa ? "page" : undefined}
        className={clases(
          "flex min-h-11 items-center gap-3 rounded-xl px-3 text-[0.9375rem] transition-colors",
          activa ? "bg-superficie font-semibold text-tinta shadow-suave" : "text-tinta-suave hover:bg-superficie-2 hover:text-tinta",
        )}
      >
        <Icono aria-hidden="true" className={clases("h-5 w-5", activa ? "text-marca" : undefined)} strokeWidth={1.75} />
        {d.texto}
      </Link>
    </li>
  );
}

function Grupo({ titulo, compacta, children }: { titulo: string; compacta: boolean; children: ReactNode }) {
  if (compacta) {
    return (
      <>
        <p className="sr-only">{titulo}</p>
        <hr className="mx-3 my-3 border-0 border-t border-linea" aria-hidden="true" />
        <ul className="space-y-1">{children}</ul>
      </>
    );
  }
  return (
    <>
      <p className="mt-7 mb-2 px-3 text-xs font-semibold tracking-wider text-tinta-suave uppercase">{titulo}</p>
      <ul className="space-y-1">{children}</ul>
    </>
  );
}

/**
 * La barra lateral. En Operar se estrecha a un carril de iconos con su palabra debajo: la
 * pantalla de exchange necesita el ancho para el grafico, el libro y el boleto a la vez.
 */
function BarraLateral({ ruta, compacta }: { ruta: string; compacta: boolean }) {
  return (
    <aside
      className={clases(
        "fixed inset-y-0 left-0 z-20 hidden flex-col border-r border-linea bg-fondo pt-7 pb-6 lg:flex",
        compacta ? "w-[5.5rem] px-2 pt-5" : "w-64 px-4",
      )}
    >
      <div className={compacta ? "flex flex-col items-center gap-3" : "px-2"}>
        {compacta ? <LogoCompacto /> : <Logo />}
        <div className={compacta ? undefined : "mt-4"}>
          <PildoraModo compacta={compacta} />
        </div>
      </div>
      <nav aria-label="Secciones" className={clases("flex-1 overflow-y-auto", compacta ? "mt-4" : "mt-8")}>
        <ul className="space-y-1">
          {PRINCIPAL.map((d) => (
            <EnlaceLateral key={d.ruta} d={d} activa={esActiva(ruta, d.ruta)} compacta={compacta} />
          ))}
        </ul>
        <Grupo titulo="En vivo · dinero ficticio" compacta={compacta}>
          {EN_VIVO.map((d) => (
            <EnlaceLateral key={d.ruta} d={d} activa={esActiva(ruta, d.ruta)} compacta={compacta} />
          ))}
        </Grupo>
        <Grupo titulo="Más" compacta={compacta}>
          {MAS.map((d) => (
            <EnlaceLateral key={d.ruta} d={d} activa={esActiva(ruta, d.ruta)} compacta={compacta} />
          ))}
        </Grupo>
      </nav>
      {compacta ? null : (
        <p className="px-3 text-xs leading-relaxed text-tinta-suave">Un sistema que no puede mentirte sobre sus propios resultados.</p>
      )}
    </aside>
  );
}

function LogoCompacto() {
  return (
    <Link href="/" className="inline-flex h-11 w-11 items-center justify-center rounded-lg" aria-label="INVEST LL, ir a Inicio">
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
        <rect width="30" height="30" rx="9" fill="var(--marca)" />
        <path d="M7 19.5 12 14l4 3.5 7-8" fill="none" stroke="var(--marca-tinta)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="23" cy="9.5" r="1.8" fill="var(--destaque)" />
      </svg>
    </Link>
  );
}

function CabeceraMovil() {
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-linea bg-fondo/90 px-4 backdrop-blur-md lg:hidden">
      <Logo />
      <PildoraModo />
    </header>
  );
}

/** Lo que en el movil vive en "Más": todo lo que no esta en la barra inferior. */
export const EN_MAS_MOVIL: readonly (Destino & { bajada: string })[] = [...PRINCIPAL, ...EN_VIVO].filter((d) => !BARRA_MOVIL.includes(d.ruta));

function BarraInferior({ ruta }: { ruta: string }) {
  const todos = [...PRINCIPAL, ...EN_VIVO];
  const destinos: Destino[] = [
    ...BARRA_MOVIL.map((r) => todos.find((d) => d.ruta === r)).filter((d): d is Destino & { bajada: string } => d !== undefined),
    { ruta: "/mas/", texto: "Más", icono: LayoutGrid },
  ];
  const enMas = ["/mas/", ...EN_MAS_MOVIL.map((m) => m.ruta), ...MAS.map((m) => m.ruta)].some((r) => normalizar(ruta).startsWith(r));
  return (
    <nav
      aria-label="Secciones"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-linea bg-superficie/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
    >
      <ul className="mx-auto flex max-w-lg">
        {destinos.map((d) => {
          const activa = d.ruta === "/mas/" ? enMas : esActiva(ruta, d.ruta);
          const Icono = d.icono;
          return (
            <li key={d.ruta} className="flex-1">
              <Link
                href={d.ruta}
                aria-current={activa ? "page" : undefined}
                className={clases(
                  "flex min-h-16 flex-col items-center justify-center gap-1 text-xs",
                  activa ? "font-semibold text-marca" : "text-tinta-suave",
                )}
              >
                <span
                  className={clases(
                    "flex h-8 w-14 items-center justify-center rounded-full transition-colors",
                    activa && "bg-marca-suave",
                  )}
                >
                  <Icono aria-hidden="true" className="h-5 w-5" strokeWidth={activa ? 2 : 1.75} />
                </span>
                {d.texto}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** En dinero real, una franja fina de color en todo el borde superior (docs/panel-v2.md, 3). */
function FranjaReal() {
  const { modo } = useModo();
  if (modo !== "real") return null;
  return (
    <div className="fixed inset-x-0 top-0 z-50 h-1 bg-real" role="presentation">
      <span className="sr-only">Modo dinero real</span>
    </div>
  );
}

/** Aplica el tema guardado (el script del layout ya lo hizo antes de pintar; esto sigue los cambios). */
function Tema() {
  const [tema] = useGuardado("local", "invest-ll.tema", "sistema");
  useEffect(() => {
    if (tema === "claro") document.documentElement.dataset.theme = "light";
    else if (tema === "oscuro") document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
  }, [tema]);
  return null;
}

function escenarioDeEjemplo(): string {
  try {
    return window.sessionStorage.getItem("invest-ll.mock.escenario") ?? "con-plan";
  } catch {
    return "con-plan";
  }
}

/** Los datos de ejemplo no se pueden confundir con los de verdad: se dice en todas las pantallas. */
function BandaEjemplo() {
  const [escenario] = useGuardado("sesion", "invest-ll.mock.escenario", "con-plan");
  if (!MODO_EJEMPLO) return null;
  return (
    <p className="mb-6 rounded-xl border border-dashed border-linea-control/60 px-4 py-2 text-sm text-tinta-suave">
      <strong className="font-semibold text-tinta">Datos de ejemplo</strong> de <code className="font-mono">web/mocks/</code>, no
      de la API{API_BASE ? ` de ${API_BASE}` : ""}: ninguna cifra es real. Escenario «{escenario || escenarioDeEjemplo()}» ·{" "}
      <Link href="/ajustes/#ejemplo" className="font-medium text-marca underline underline-offset-4">
        cambiar
      </Link>
    </p>
  );
}

function AvisoSinModo() {
  const { modo, error, cargando } = useModo();
  if (modo !== null || !error || cargando) return null;
  return (
    <Aviso tipo="critico" titulo="No se ha podido leer el modo de operación" className="mb-6">
      Este panel no puede decirte si envía órdenes o no, así que no ofrece nada que mueva dinero hasta que la API
      responda.
      <span className="mt-1 block text-sm opacity-90">La API dice: {error.detalle}</span>
    </Aviso>
  );
}

/**
 * El marco de todas las pantallas: barra lateral en escritorio, barra inferior en movil, la
 * pildora del modo siempre arriba y el boton de Pregunta flotando.
 */
export function Marco({ children }: { children: ReactNode }) {
  const ruta = usePathname();
  // Operar es una pantalla de exchange: usa todo el ancho y la barra lateral se estrecha.
  const ancha = normalizar(ruta).startsWith("/operar/");
  useEffect(() => {
    // El boton de Pregunta se recoge en el carril (globals.css): no tapa el boleto ni la cuenta.
    if (ancha) document.body.dataset.ancha = "";
    else delete document.body.dataset.ancha;
  }, [ancha]);
  return (
    <>
      <Tema />
      <FranjaReal />
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-xl focus:bg-superficie focus:px-4 focus:py-3 focus:shadow-alta"
      >
        Saltar al contenido
      </a>
      <BarraLateral ruta={ruta} compacta={ancha} />
      <CabeceraMovil />
      <div className={ancha ? "lg:pl-[5.5rem]" : "lg:pl-64"}>
        <main
          id="contenido"
          className={clases(
            "relleno-barra-inferior mx-auto px-4 pt-6 sm:px-6",
            ancha ? "max-w-[1760px] pt-4 lg:px-5 lg:pt-5" : "max-w-[1120px] lg:px-12 lg:pt-12",
          )}
        >
          <BandaEjemplo />
          <AvisoSinModo />
          {children}
        </main>
      </div>
      <BarraInferior ruta={ruta} />
      <Pregunta />
    </>
  );
}
