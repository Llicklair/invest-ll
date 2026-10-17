"use client";

import { ChartLine, Compass, HandCoins, House, LayoutGrid, Microscope, Settings, Wallet, type LucideIcon } from "lucide-react";
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
export const PRINCIPAL: readonly Destino[] = [
  { ruta: "/", texto: "Inicio", icono: House },
  { ruta: "/estrategias/", texto: "Estrategias", icono: Compass },
  { ruta: "/invertir/", texto: "Invertir", icono: HandCoins },
  { ruta: "/cartera/", texto: "Cartera", icono: Wallet },
];

/** "Más": lo que no es el camino principal. */
export const MAS: readonly (Destino & { bajada: string })[] = [
  { ruta: "/mercado/", texto: "Mercado", icono: ChartLine, bajada: "Cómo van el oro, la bolsa o el bitcoin, con su fecha" },
  { ruta: "/laboratorio/", texto: "Laboratorio", icono: Microscope, bajada: "Para quien sabe: pruebas, investigación y alertas" },
  { ruta: "/ajustes/", texto: "Ajustes", icono: Settings, bajada: "Conexión con Binance, tema y datos" },
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

function EnlaceLateral({ d, activa }: { d: Destino; activa: boolean }) {
  const Icono = d.icono;
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

function BarraLateral({ ruta }: { ruta: string }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-linea bg-fondo px-4 pt-7 pb-6 lg:flex">
      <div className="px-2">
        <Logo />
        <div className="mt-4">
          <PildoraModo />
        </div>
      </div>
      <nav aria-label="Secciones" className="mt-8 flex-1 overflow-y-auto">
        <ul className="space-y-1">
          {PRINCIPAL.map((d) => (
            <EnlaceLateral key={d.ruta} d={d} activa={esActiva(ruta, d.ruta)} />
          ))}
        </ul>
        <p className="mt-8 mb-2 px-3 text-xs font-semibold tracking-wider text-tinta-suave uppercase">Más</p>
        <ul className="space-y-1">
          {MAS.map((d) => (
            <EnlaceLateral key={d.ruta} d={d} activa={esActiva(ruta, d.ruta)} />
          ))}
        </ul>
      </nav>
      <p className="px-3 text-xs leading-relaxed text-tinta-suave">
        Un sistema que no puede mentirte sobre sus propios resultados.
      </p>
    </aside>
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

function BarraInferior({ ruta }: { ruta: string }) {
  const destinos: Destino[] = [...PRINCIPAL, { ruta: "/mas/", texto: "Más", icono: LayoutGrid }];
  const enMas = ["/mas/", ...MAS.map((m) => m.ruta)].some((r) => normalizar(ruta).startsWith(r));
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
      <BarraLateral ruta={ruta} />
      <CabeceraMovil />
      <div className="lg:pl-64">
        <main id="contenido" className="relleno-barra-inferior mx-auto max-w-[1120px] px-4 pt-6 sm:px-6 lg:px-12 lg:pt-12">
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
