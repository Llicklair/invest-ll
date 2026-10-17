"use client";

import Link from "next/link";
import { useState } from "react";

import { api, pedir } from "@/api/cliente";
import { ConfirmacionTecleada, useComprobacionOrden } from "@/componentes/ConfirmacionTecleada";
import { Boton, CampoTexto, ErrorApiVista, Segmentado, Selector } from "@/componentes/ui";
import { useModo } from "@/contexto/modo";
import { useAccion } from "@/lib/consulta";
import { normalizarTecleo } from "@/lib/importe";

import { Resultado } from "./HojaConfirmar";

const PARES = [
  { par: "BTC/USDT", nombre: "Bitcoin" },
  { par: "ETH/USDT", nombre: "Ethereum" },
  { par: "SOL/USDT", nombre: "Solana" },
  { par: "BNB/USDT", nombre: "BNB" },
];

/**
 * Una orden a mano, para quien sabe lo que hace (plegada en "Avanzado"). La misma confirmacion
 * que en el terminal: el boton se habilita SOLO cuando la API dice que se puede con lo tecleado.
 */
export function OrdenManual({ alEnviar }: { alEnviar: () => void }) {
  const { modo } = useModo();
  const [par, setPar] = useState(PARES[0]?.par ?? "BTC/USDT");
  const [lado, setLado] = useState<"buy" | "sell">("buy");
  const [cantidadTxt, setCantidadTxt] = useState("0.001");
  const [escrito, setEscrito] = useState("");
  const cantidad = normalizarTecleo(cantidadTxt);
  const envia = modo === "pruebas" || modo === "real";
  const { estado, escritoNormal } = useComprobacionOrden(cantidad, escrito, envia);

  const enviar = useAccion(async () => {
    const r = await pedir(api.POST("/api/ordenes", { body: { par, lado, cantidad, escrito: escritoNormal } }));
    // La confirmacion vale para UNA orden: para otra, hay que volver a teclearla.
    setEscrito("");
    alEnviar();
    return r;
  });

  if (!envia) {
    return (
      <p className="text-[0.9375rem] text-tinta-suave">
        {modo === null
          ? "No se sabe en qué modo está el panel: no se ofrece enviar nada hasta que la API responda."
          : "En simulación el panel no envía nada."}{" "}
        <Link href="/conexiones/" className="font-semibold text-marca underline underline-offset-4">
          Conectar Binance
        </Link>
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-[1fr_auto_1fr] sm:items-end">
        <Selector etiqueta="Qué" value={par} onChange={(e) => setPar(e.target.value)}>
          {PARES.map((p) => (
            <option key={p.par} value={p.par}>
              {p.nombre} ({p.par})
            </option>
          ))}
        </Selector>
        <Segmentado
          etiqueta="Comprar o vender"
          opciones={[
            { valor: "buy", texto: "Comprar" },
            { valor: "sell", texto: "Vender" },
          ]}
          valor={lado}
          onCambio={(v) => setLado(v === "sell" ? "sell" : "buy")}
        />
        <CampoTexto
          etiqueta="Cantidad"
          value={cantidadTxt}
          onChange={(e) => setCantidadTxt(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          className="cifras"
        />
      </div>
      <ConfirmacionTecleada
        esperado={cantidad || "?"}
        valor={escrito}
        onCambio={setEscrito}
        estado={estado}
        tono={modo === "real" ? "real" : "normal"}
      />
      {enviar.error ? <ErrorApiVista error={enviar.error} prefijo="La orden no salió:" /> : null}
      <Boton
        variante={modo === "real" ? "real" : "secundario"}
        disabled={estado.tipo !== "puede" || enviar.enCurso}
        onClick={() => void enviar.ejecutar()}
      >
        {enviar.enCurso ? "Enviando…" : `${lado === "buy" ? "Comprar" : "Vender"} ${cantidad || "?"} ${par.split("/")[0] ?? ""}`}
      </Boton>
      {enviar.resultado ? <Resultado r={enviar.resultado} modo={modo} /> : null}
    </div>
  );
}
