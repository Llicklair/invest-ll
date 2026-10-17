/**
 * Alias legibles de los tipos generados desde `web/openapi.json` (`npm run tipos`).
 * No se escribe ningun tipo de la API a mano: si el contrato cambia, se regenera y el
 * compilador dice que pantalla hay que tocar.
 */
import type { components } from "./esquema";

type S = components["schemas"];

export type Activo = S["Activo"];
export type Alerta = S["Alerta"];
export type Alertas = S["Alertas"];
export type AnalisisCartera = S["AnalisisCartera"];
export type Cartera = S["Cartera"];
export type Comparacion = S["Comparacion"];
export type ComparacionLLM = S["ComparacionLLM"];
export type CompraPropuesta = S["CompraPropuesta-Output"];
export type ComprobacionTriggers = S["ComprobacionTriggers"];
export type Cotizacion = S["Cotizacion"];
export type Cotizaciones = S["Cotizaciones"];
export type DatosDescargados = S["DatosDescargados"];
export type Disparo = S["Disparo"];
export type Estado = S["Estado"];
export type EstadoEnvio = S["EstadoEnvio"];
export type FilaRendimiento = S["FilaRendimiento"];
export type Informe = S["Informe"];
export type InformeAportaciones = S["InformeAportaciones"];
export type Investigacion = S["Investigacion"];
export type MensajeChat = S["MensajeChat"];
export type Modo = S["Modo"];
export type MovimientoRegistrado = S["MovimientoRegistrado"];
export type NuevoMovimiento = S["NuevoMovimiento"];
export type OpcionesSimular = S["OpcionesSimular"];
export type OrdenesEnviadas = S["OrdenesEnviadas"];
export type PeticionUnActivo = S["PeticionUnActivo"];
export type PosicionAbierta = S["PosicionAbierta"];
export type PosicionRetirada = S["PosicionRetirada"];
export type Propuesta = S["Propuesta"];
export type Punto = S["Punto"];
export type PuntoComparado = S["PuntoComparado"];
export type Rendimiento = S["Rendimiento"];
export type RespuestaChat = S["RespuestaChat"];
export type ResultadoActualizacion = S["ResultadoActualizacion"];
export type ResultadoDescarga = S["ResultadoDescarga"];
export type ResultadoOrden = S["ResultadoOrden"];
export type RegistroPropuesta = S["RegistroPropuesta"];
export type Seguimiento = S["Seguimiento"];
export type Serie = S["Serie"];
export type Tabla = S["Tabla"];
export type TriggerArmado = S["TriggerArmado"];
export type Triggers = S["Triggers"];
export type Investigacion_PruebaAdelante = S["PruebaAdelante"];
export type PesoObjetivo = S["PesoObjetivo"];

/** Ventana de una grafica: el `Tramo` del contrato. */
export type Tramo = Serie["tramo"];
export type Estrategia = PeticionUnActivo["estrategia"];
export type Celda = Tabla["filas"][number][number];
