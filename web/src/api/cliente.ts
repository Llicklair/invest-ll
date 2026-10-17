/**
 * El cliente de la API, tipado desde el contrato. Nada mas habla con el servidor.
 *
 * - Base: `NEXT_PUBLIC_API_BASE` (en desarrollo, `http://localhost:8601`); vacia en produccion,
 *   porque la propia API sirve este frontend: mismo origen.
 * - Errores: la API los manda como `{"detail": "..."}` y el texto se le ensena al operador TAL
 *   CUAL. Se convierten en `ErrorApi` para que ninguna pantalla pueda ignorarlos sin querer.
 * - `NEXT_PUBLIC_MOCK=1` (solo con `npm run dev`) cambia la red por las respuestas de ejemplo de
 *   `web/mocks/`. En un `next build` la condicion es falsa en tiempo de compilacion y ese codigo
 *   ni se incluye: el modo de ejemplo nunca puede ser el modo por defecto.
 */
import createClient from "openapi-fetch";

import type { paths } from "./esquema";

export const API_BASE: string = process.env.NEXT_PUBLIC_API_BASE ?? "";

export const MODO_EJEMPLO: boolean =
  process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK === "1";

let fetchPropio: ((peticion: Request) => Promise<Response>) | undefined;
if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK === "1") {
  fetchPropio = async (peticion) => (await import("@mocks/simulador")).responder(peticion);
}

export const api = createClient<paths>({
  baseUrl: API_BASE,
  ...(fetchPropio ? { fetch: fetchPropio } : {}),
});

/** URL absoluta (o relativa al origen) de una ruta de la API, para iframes y enlaces. */
export function urlApi(ruta: `/api/${string}`): string {
  return `${API_BASE}${ruta}`;
}

export class ErrorApi extends Error {
  /** Codigo HTTP; `null` si ni siquiera se pudo hablar con la API. */
  readonly estado: number | null;
  readonly detalle: string;

  constructor(estado: number | null, detalle: string) {
    super(detalle);
    this.name = "ErrorApi";
    this.estado = estado;
    this.detalle = detalle;
  }
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null;
}

/**
 * El texto de un error de la API. Los errores del dominio llegan como `{"detail": "texto"}`;
 * los de validacion de FastAPI, como `{"detail": [{loc, msg}, ...]}`. Se respetan los textos.
 */
export function textoDeError(cuerpo: unknown, respuesta?: Response): string {
  if (typeof cuerpo === "string" && cuerpo.trim() !== "") return cuerpo;
  if (esObjeto(cuerpo)) {
    const detalle = cuerpo.detail;
    if (typeof detalle === "string") return detalle;
    if (Array.isArray(detalle)) {
      const lineas = detalle.map((d: unknown) => {
        if (!esObjeto(d)) return String(d);
        const donde = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
        const msg = typeof d.msg === "string" ? d.msg : JSON.stringify(d);
        return donde ? `${donde}: ${msg}` : msg;
      });
      if (lineas.length) return lineas.join("\n");
    }
  }
  if (respuesta) return `La API respondió ${respuesta.status} ${respuesta.statusText} sin explicación.`;
  return "Error desconocido de la API.";
}

/**
 * Un plazo para las rutas lentas en frio (`GET /api/estrategias` tarda ~25 s la primera vez tras
 * arrancar la API; `recomendar`, ~6 s). Se pasa como `signal` a la peticion.
 */
export const PLAZO_LENTO_MS = 60_000;

export function conPlazo(ms = PLAZO_LENTO_MS): { signal: AbortSignal } {
  return { signal: AbortSignal.timeout(ms) };
}

function errorDeRed(error: unknown): ErrorApi {
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return new ErrorApi(null, `La API no ha respondido en ${Math.round(PLAZO_LENTO_MS / 1000)} s. Puede que siga calculando: vuelve a intentarlo en un momento.`);
  }
  const motivo = error instanceof Error ? error.message : String(error);
  const donde = API_BASE ? ` en ${API_BASE}` : "";
  return new ErrorApi(null, `No se pudo hablar con la API${donde}: ${motivo}`);
}

export function comoErrorApi(error: unknown): ErrorApi {
  return error instanceof ErrorApi ? error : errorDeRed(error);
}

interface RespuestaCliente<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Espera una respuesta con cuerpo y la devuelve, o lanza `ErrorApi` con el `detail` de la API. */
export async function pedir<T>(promesa: Promise<RespuestaCliente<T>>): Promise<T> {
  let r: RespuestaCliente<T>;
  try {
    r = await promesa;
  } catch (error) {
    throw errorDeRed(error);
  }
  if (!r.response.ok) throw new ErrorApi(r.response.status, textoDeError(r.error, r.response));
  if (r.data === undefined) throw new ErrorApi(r.response.status, "La API respondió sin cuerpo.");
  return r.data;
}

/** Para las rutas que responden 204 (pausar, desarmar...): solo importa que no haya error. */
export async function pedirSinCuerpo(promesa: Promise<RespuestaCliente<unknown>>): Promise<void> {
  let r: RespuestaCliente<unknown>;
  try {
    r = await promesa;
  } catch (error) {
    throw errorDeRed(error);
  }
  if (!r.response.ok) throw new ErrorApi(r.response.status, textoDeError(r.error, r.response));
}
