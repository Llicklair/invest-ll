/**
 * Los escenarios del modo de ejemplo (`?escenario=` en la URL). Fichero aparte y sin dependencias
 * para que Ajustes pueda listarlos sin cargar el simulador entero (y solo en `npm run dev:mock`).
 */
export const ESCENARIOS = [
  "primera-vez",
  "con-plan",
  "nada-que-hacer",
  "pruebas",
  "listo-para-real",
  "real",
  "entorno",
  "fallo-red",
  "sin-datos",
  "pausa",
  "vacio",
  "modo-roto",
  "en-frio",
  "datos-viejos",
  "datos-actualizando",
  "vender",
  // Panel v3 (Operar y Bots, en vivo). Los de antes se ven en vivo como "con-bots".
  "con-bots",
  "sin-bots",
  "cuenta-vacia",
  "desconectado",
  "intermitente",
  "sin-stream",
  // Panel v4 (varios exchanges, estrategias a medida, bots reales).
  "bots-reales",
  "parado-todo",
  "sin-conexiones",
  "sin-claude",
] as const;
export type Escenario = (typeof ESCENARIOS)[number];

export const DESCRIPCION_ESCENARIOS: Record<Escenario, string> = {
  "primera-vez": "Sin plan ni movimientos: la bienvenida y el asistente",
  "con-plan": "Plan guardado, simulación, tres compras por hacer",
  "nada-que-hacer": "Plan guardado y nada que hacer hoy",
  pruebas: "Modo pruebas con claves; falta la orden de prueba",
  "listo-para-real": "Pruebas hechas y claves reales guardadas: se puede activar el dinero real",
  real: "Dinero real activado",
  entorno: "El modo y las claves los fija el entorno",
  "fallo-red": "Pruebas; la orden se envía y se pierde la conexión",
  "sin-datos": "Faltan los datos de Binance y el precio de un activo",
  pausa: "Plan guardado con la pausa de compras activa",
  vacio: "Todo vacío (también Laboratorio)",
  "modo-roto": "La API no sabe en qué modo está",
  "en-frio": "Primera vez tras arrancar la API: las estrategias tardan en calcularse",
  "datos-viejos": "Los precios tienen más de dos semanas; al actualizar, los fondos fallan",
  "datos-actualizando": "Una actualización de los datos en marcha, paso a paso",
  vender: "Prudente con freno: toca vender en tu bróker un fondo que lleva meses bajando (v2.2)",
  "con-bots": "En vivo: cuenta de práctica con posiciones y órdenes, y cinco bots (uno parado, uno con error)",
  "sin-bots": "En vivo: cuenta de práctica con historial y ningún bot desplegado",
  "cuenta-vacia": "En vivo: cuenta de práctica recién empezada (10.000 USDC) y sin bots",
  desconectado: "En vivo: el panel no recibe datos de Hyperliquid; los precios se quedan quietos",
  intermitente: "En vivo: el stream se corta cada ~20 s y se reconecta solo",
  "sin-stream": "En vivo: no hay stream (como la API de antes); el panel pregunta cada pocos segundos",
  "bots-reales": "v4: dos bots con dinero real en Binance (uno con los límites a medio gastar, otro pausado por un estado desconocido), uno en pruebas, estrategias a medida y una conversación con Claude",
  "parado-todo": "v4: se acaba de pulsar «Parar todo lo real»: los reales parados y cómo reanudar",
  "sin-conexiones": "v4: ningún exchange conectado ni ninguna estrategia a medida: el primer paso",
  "sin-claude": "v4: el programa claude no está instalado: diseñar con Claude responde 422",
};

const CLAVE = "invest-ll.mock.escenario";

function esEscenario(v: string): v is Escenario {
  return (ESCENARIOS as readonly string[]).includes(v);
}

/**
 * El escenario vigente: el de `?escenario=` si viene en la URL (y se recuerda en la pestana), o
 * el recordado, o `porDefecto`. Lo comparten el simulador REST y el stream simulado.
 */
export function escenarioActual(porDefecto: Escenario = "con-plan"): Escenario {
  try {
    let pedido = new URLSearchParams(window.location.search).get("escenario");
    if (pedido === "simulacion") pedido = porDefecto;
    const guardado = window.sessionStorage.getItem(CLAVE);
    if (pedido && esEscenario(pedido) && pedido !== guardado) {
      window.sessionStorage.setItem(CLAVE, pedido);
      window.dispatchEvent(new CustomEvent("invest-ll-almacen", { detail: CLAVE }));
    }
    const vigente = window.sessionStorage.getItem(CLAVE) ?? porDefecto;
    return esEscenario(vigente) ? vigente : porDefecto;
  } catch {
    return porDefecto;
  }
}
