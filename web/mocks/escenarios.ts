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
};
