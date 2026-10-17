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
export type FilaOrden = S["FilaOrden"];
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
/** Las reglas de "Una estrategia sobre un activo" (Laboratorio), no las del catalogo v2. */
export type EstrategiaUnActivo = PeticionUnActivo["estrategia"];
export type Celda = Tabla["filas"][number][number];

// -- Panel v2 (schemas_v2.py) -------------------------------------------------------------------

export type Accion = S["Accion"];
export type AccionHecha = S["AccionHecha"];
export type CambioModo = S["CambioModo"];
export type Catalogo = S["Catalogo"];
export type Cerrojo = S["Cerrojo"];
export type Conexion = S["Conexion"];
export type EstadoRed = S["EstadoRed"];
export type Estrategia = S["Estrategia"];
export type Evidencia = S["Evidencia"];
export type Historico = S["Historico"];
export type Hoy = S["Hoy"];
export type Inicio = S["Inicio"];
export type MiniMercado = S["MiniMercado"];
export type ModoDisponible = S["ModoDisponible"];
export type Movimiento = S["Movimiento"];
export type Movimientos = S["Movimientos"];
export type NuevasClaves = S["NuevasClaves"];
export type NuevoPlan = S["NuevoPlan"];
export type Parte = S["Parte"];
export type ParteDelPlan = S["ParteDelPlan-Input"];
export type ParteResumen = S["ParteResumen"];
export type Patrimonio = S["Patrimonio"];
export type Perfil = S["Perfil"];
export type PeticionSimulacion = S["PeticionSimulacion"];
export type Plan = S["Plan"];
export type PlanGuardado = S["PlanGuardado"];
export type PruebaConexion = S["PruebaConexion"];
export type PuntoSimulado = S["PuntoSimulado"];
export type Recomendacion = S["Recomendacion"];
export type ResultadoSimulado = S["ResultadoSimulado"];
export type Saldo = S["Saldo"];
export type SaldoMoneda = S["SaldoMoneda"];
export type Simulacion = S["Simulacion"];

// -- Contrato v2.1 -------------------------------------------------------------------------------

export type EstadoDatos = S["EstadoDatos"];
export type FuenteDatos = S["FuenteDatos"];
export type PasoDatos = S["PasoDatos"];
export type TrabajoDatos = S["TrabajoDatos"];
export type PorcentajeEstrategia = S["PorcentajeEstrategia"];
export type TipoMovimiento = NuevoMovimiento["tipo"];

export type ModoPanel = Conexion["modo"];
export type Red = EstadoRed["red"];
export type Horizonte = Perfil["horizonte"];
export type AnteCaida = Perfil["ante_caida"];
export type QuiereCripto = Perfil["cripto"];

// -- Panel v3: en vivo (schemas_v3.py, docs/panel-v3-vivo.md) --------------------------------------

export type EstadoVivo = S["EstadoVivo"];
export type MonedaVivo = S["MonedaVivo"];
export type Monedas = S["Monedas"];
export type NivelLibro = S["NivelLibro"];
export type LibroVivo = S["LibroVivo"];
export type OperacionMercado = S["OperacionMercado"];
export type Operaciones = S["Operaciones"];
export type VelaVivo = S["VelaVivo"];
export type Velas = S["Velas"];

export type PosicionPractica = S["PosicionPractica"];
export type OrdenPractica = S["OrdenPractica"];
export type EjecucionPractica = S["EjecucionPractica"];
export type CuentaPractica = S["CuentaPractica"];
export type NuevaOrdenPractica = S["NuevaOrdenPractica"];
export type ResultadoPractica = S["ResultadoPractica"];
export type ReinicioPractica = S["ReinicioPractica"];
export type LadoPractica = NuevaOrdenPractica["lado"];
export type TipoOrden = NuevaOrdenPractica["tipo"];

export type EvidenciaBot = S["EvidenciaBot"];
export type ParametroBot = S["ParametroBot"];
export type PlantillaBot = S["PlantillaBot"];
export type Plantillas = S["Plantillas"];
export type NuevoBot = S["NuevoBot"];
export type PuntoBot = S["PuntoBot"];
export type ResumenBot = S["ResumenBot"];
export type Bots = S["Bots"];
export type OperacionBot = S["OperacionBot"];
export type EventoBot = S["EventoBot"];
export type DetalleBot = S["DetalleBot"];
export type EstadoBot = ResumenBot["estado"];

// -- Panel v4: bots reales, varios exchanges y estrategias a medida (schemas_v3/v4) ----------------

/** ficticio · pruebas · real (el modo de CADA bot; el del panel es `ModoPanel`). */
export type ModoBot = ResumenBot["modo"];
/** Los limites como llegan de la API (importes en cadena). */
export type LimitesBot = S["LimitesBot-Output"];
/** Los limites como se envian (la API acepta importes en cadena o numero; aqui, cadena). */
export type LimitesBotEntrada = S["LimitesBot-Input"];
export type ConsumoLimites = S["ConsumoLimites"];
export type EstadoReal = S["EstadoReal"];
export type ActivarReal = S["ActivarReal"];
export type CambioLimites = S["CambioLimites"];
export type ParadaGeneral = S["ParadaGeneral"];
export type LimiteDiario = S["LimiteDiario"];

export type CampoClave = S["CampoClave"];
export type ExchangeDisponible = S["ExchangeDisponible"];
export type EstadoRedExchange = S["EstadoRedExchange"];
export type EstadoExchange = S["EstadoExchange"];
export type ActivoExchange = EstadoExchange["activo"];
export type RedExchange = EstadoRedExchange["red"];
export type ConfigMcp = S["ConfigMcp"];
export type Conexiones = S["Conexiones"];
export type ClavesExchange = S["ClavesExchange"];
export type PruebaExchange = S["PruebaExchange"];
export type ActivarExchange = S["ActivarExchange"];
export type MercadoExchange = S["MercadoExchange"];
export type MercadosExchange = S["MercadosExchange"];

export type ResultadoPrueba = S["ResultadoPrueba"];
export type ResumenEstrategia = S["ResumenEstrategia"];
/** La biblioteca de estrategias a medida (`GET /api/medida`); no confundir con el catalogo v2. */
export type EstrategiasMedida = S["Estrategias"];
export type EstadoEstrategia = ResumenEstrategia["estado"];
export type AutorEstrategia = ResumenEstrategia["autor"];
export type VersionEstrategia = S["VersionEstrategia"];
export type DetalleEstrategia = S["DetalleEstrategia"];
export type NuevaEstrategia = S["NuevaEstrategia"];
export type PeticionPruebaEstrategia = S["PeticionPruebaEstrategia"];
export type EsquemaEstrategia = S["EsquemaEstrategia"];
export type PeticionDiseno = S["PeticionDiseno"];
export type MensajeDiseno = S["MensajeDiseno"];
export type RespuestaDiseno = S["RespuestaDiseno"];

/**
 * Los eventos de `GET /api/vivo/stream` (docs/panel-v3-vivo.md, seccion 5). El OpenAPI no puede
 * describir un text/event-stream, asi que el reparto evento -> modelo se escribe aqui, pero cada
 * `data` es un tipo GENERADO: si un modelo cambia, el compilador lo dice igual que en REST.
 */
export interface EventosVivo {
  monedas: Monedas;
  libro: LibroVivo;
  /** Las operaciones NUEVAS desde el evento anterior (la mas reciente primero). */
  operaciones: OperacionMercado[];
  vela: VelaVivo;
  cuenta: CuentaPractica;
  bots: Bots;
  estado: EstadoVivo;
}
export type CanalVivo = keyof EventosVivo;
