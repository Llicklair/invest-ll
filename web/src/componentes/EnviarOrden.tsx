"use client";

import { useEffect, useState } from "react";

import { api, comoErrorApi, pedir, type ErrorApi } from "@/api/cliente";
import type { EstadoEnvio } from "@/api/tipos";
import { useEstado } from "@/contexto/estado";
import { useAccion, useRetardado } from "@/lib/consulta";

import { Aviso, Boton, CampoTexto, Cargando, ErrorApiVista, Nota, Seccion, Selector } from "./ui";

const PARES_POR_DEFECTO = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"];

interface Comprobacion {
  /** Para que entrada se pidio: si el operador ha seguido tecleando, ya no vale. */
  cantidad: string;
  escrito: string;
  resultado: EstadoEnvio | null;
  error: ErrorApi | null;
}

/**
 * Enviar UNA orden, con la misma confirmacion que el terminal. El boton no decide nada: se
 * habilita SOLO cuando `POST /api/ordenes/comprobar` dice `puede: true` para la cantidad y lo
 * tecleado ahora mismo, y mientras no, se ensena su `motivo`. Un clic distraido no mueve dinero.
 */
export function EnviarOrden({ alEnviar }: { alEnviar?: () => void }) {
  const { estado, error: errorEstado } = useEstado();
  const modo = estado?.modo ?? null;
  const [par, setPar] = useState(PARES_POR_DEFECTO[0] ?? "BTC/USDT");
  const [lado, setLado] = useState<"buy" | "sell">("buy");
  const [cantidad, setCantidad] = useState("0.001");
  const [escrito, setEscrito] = useState("");
  const [comprobacion, setComprobacion] = useState<Comprobacion | null>(null);

  // Se comprueba cuando el operador deja de teclear; la clave es texto para que sea estable.
  const claveEntrada = useRetardado(JSON.stringify([cantidad.trim(), escrito]), 250);
  const envia = modo?.envia_ordenes ?? false;

  useEffect(() => {
    if (!envia) return;
    const [c = "", e = ""] = JSON.parse(claveEntrada) as string[];
    const entrada = { cantidad: c, escrito: e };
    let vigente = true;
    pedir(api.POST("/api/ordenes/comprobar", { body: { cantidad: entrada.cantidad || "0", escrito: entrada.escrito } })).then(
      (resultado) => {
        if (vigente) setComprobacion({ ...entrada, resultado, error: null });
      },
      (e: unknown) => {
        if (vigente) setComprobacion({ ...entrada, resultado: null, error: comoErrorApi(e) });
      },
    );
    return () => {
      vigente = false;
    };
  }, [claveEntrada, envia]);

  const enviar = useAccion(async () => {
    const r = await pedir(api.POST("/api/ordenes", { body: { par, lado, cantidad: cantidad.trim(), escrito } }));
    // La confirmacion vale para UNA orden: para otra, hay que volver a teclearla.
    setEscrito("");
    alEnviar?.();
    return r;
  });

  if (!modo) {
    return (
      <Seccion titulo="Enviar una orden" id="enviar-orden">
        {errorEstado ? (
          <Aviso tipo="critico">No se sabe el modo de operación: no se ofrece enviar nada hasta que la API responda.</Aviso>
        ) : (
          <Cargando texto="Leyendo el modo de operación…" />
        )}
      </Seccion>
    );
  }

  if (!modo.envia_ordenes) {
    return (
      <Seccion titulo="Enviar una orden" id="enviar-orden">
        <Nota>
          Modo simulación: el panel no puede enviar nada. Para operar en la red de pruebas, arranca el panel con{" "}
          <code className="font-mono">INVEST_LL_MODE=testnet</code> y sus credenciales.
        </Nota>
      </Seccion>
    );
  }

  const vigente =
    comprobacion !== null && comprobacion.cantidad === cantidad.trim() && comprobacion.escrito === escrito;
  const puede = vigente && comprobacion.resultado?.puede === true;
  const motivo = !vigente
    ? "Comprobando lo tecleado con la API…"
    : comprobacion.error
      ? null
      : (comprobacion.resultado?.motivo ?? null);
  const textoBoton = `Enviar ${lado.toUpperCase()} ${cantidad.trim() || "?"} ${par}`;

  return (
    <Seccion titulo="Enviar una orden" id="enviar-orden">
      {modo.es_real ? (
        <Aviso tipo="critico">
          <strong>MODO REAL: lo que envíes desde aquí mueve DINERO DE VERDAD.</strong> Cada orden sigue pidiendo su
          confirmación.
        </Aviso>
      ) : (
        <Aviso tipo="aviso">
          Red de pruebas: las órdenes salen de verdad al exchange, con dinero ficticio. Los precios de la red de pruebas
          no son los del mercado real.
        </Aviso>
      )}
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr]">
        <Selector etiqueta="Par" value={par} onChange={(e) => setPar(e.target.value)}>
          {PARES_POR_DEFECTO.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </Selector>
        <Selector etiqueta="Lado" value={lado} onChange={(e) => setLado(e.target.value === "sell" ? "sell" : "buy")}>
          <option value="buy">buy (compra)</option>
          <option value="sell">sell (venta)</option>
        </Selector>
        <CampoTexto
          etiqueta="Cantidad"
          value={cantidad}
          onChange={(e) => setCantidad(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          className="cifras"
        />
      </div>
      <CampoTexto
        etiqueta={`Escribe la cantidad exacta (${cantidad.trim() || "?"}) para confirmar`}
        ayuda="Se escribe el número, no un «sí»: obliga a mirar lo que se va a mover. Pegar está desactivado: tecléala."
        value={escrito}
        onChange={(e) => setEscrito(e.target.value)}
        onPaste={(e) => e.preventDefault()}
        onDrop={(e) => e.preventDefault()}
        inputMode="decimal"
        autoComplete="off"
        spellCheck={false}
        className="max-w-md"
      />
      {vigente && comprobacion.error ? (
        <ErrorApiVista error={comprobacion.error} prefijo="No se pudo comprobar si se puede enviar:" />
      ) : null}
      {motivo ? (
        <p className="text-sm text-tinta-2" aria-live="polite">
          {motivo}
        </p>
      ) : null}
      <Boton
        variante={modo.es_real ? "peligro" : "primario"}
        disabled={!puede || enviar.enCurso}
        onClick={() => void enviar.ejecutar()}
      >
        {enviar.enCurso ? "Enviando…" : textoBoton}
      </Boton>
      {enviar.error ? <ErrorApiVista error={enviar.error} prefijo="La orden no salió:" /> : null}
      {enviar.resultado ? (
        <div className="space-y-1.5">
          <Aviso
            tipo={
              enviar.resultado.estado === "unknown" ? "critico" : enviar.resultado.necesita_atencion ? "aviso" : "info"
            }
            vivo
          >
            {enviar.resultado.descripcion}
          </Aviso>
          <Nota>
            Registrada con el modo «{enviar.resultado.modo}» dentro. Ese campo es lo que permite demostrar después en qué
            modo salió.
          </Nota>
        </div>
      ) : null}
    </Seccion>
  );
}
