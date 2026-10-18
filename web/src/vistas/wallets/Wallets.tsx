"use client";

import { ChevronDown, LoaderCircle, ShieldCheck, Trash2, Wallet } from "lucide-react";
import { useEffect, useState } from "react";

import { api, pedir } from "@/api/cliente";
import type { components } from "@/api/esquema";
import { Aviso, Boton, Chip, ErrorApiVista, Esqueleto, Tarjeta } from "@/componentes/ui";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoCantidad } from "@/lib/decimal";
import { horaSegundos } from "@/lib/vivo";

type S = components["schemas"];
type RedHl = "pruebas" | "real";

/** Lo mínimo de EIP-1193 que se usa: pedir cosas a la wallet. */
interface Proveedor {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
}

/** Una wallet del navegador, como la anuncia EIP-6963 (MetaMask, Rabby, Coinbase Wallet…). */
interface WalletNavegador {
  uuid: string;
  nombre: string;
  icono: string | null;
  proveedor: Proveedor;
}

interface Anuncio {
  info: { uuid: string; name: string; icon: string; rdns: string };
  provider: Proveedor;
}

/**
 * Las wallets instaladas en este navegador (EIP-6963: cada una se anuncia sola al pedírselo) y,
 * si ninguna se anuncia, `window.ethereum` de las de antes.
 */
function useWalletsNavegador(): WalletNavegador[] | null {
  const [lista, setLista] = useState<WalletNavegador[] | null>(null);
  useEffect(() => {
    const vistas = new Map<string, WalletNavegador>();
    const alAnunciar = (e: Event) => {
      const d = (e as CustomEvent<Anuncio>).detail;
      if (!d?.info?.uuid || vistas.has(d.info.uuid)) return;
      vistas.set(d.info.uuid, { uuid: d.info.uuid, nombre: d.info.name, icono: d.info.icon || null, proveedor: d.provider });
      setLista([...vistas.values()]);
    };
    window.addEventListener("eip6963:announceProvider", alAnunciar);
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    // Con los datos de ejemplo (`npm run dev:mock`), una wallet falsa; en un `next build` ni se compila.
    if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK === "1") {
      void import("@mocks/wallets").then((m) => m.instalarWalletFalsa());
    }
    // Si en un momento nadie se ha anunciado: la de siempre (window.ethereum) o ninguna.
    const t = window.setTimeout(() => {
      if (vistas.size) return;
      const viejo = (window as unknown as { ethereum?: Proveedor }).ethereum;
      setLista(viejo ? [{ uuid: "window.ethereum", nombre: "Wallet del navegador", icono: null, proveedor: viejo }] : []);
    }, 600);
    return () => {
      window.removeEventListener("eip6963:announceProvider", alAnunciar);
      window.clearTimeout(t);
    };
  }, []);
  return lista;
}

/** "Cancelaste…" si la persona dijo que no en la wallet (código 4001); el texto de la wallet si no. */
function textoErrorWallet(e: unknown): string {
  const err = e as { code?: number; message?: string } | null;
  if (err?.code === 4001) return "Cancelaste en la wallet: no se ha hecho nada.";
  return `La wallet dijo: ${err?.message ?? String(e)}`;
}

const corta = (d: string) => `${d.slice(0, 6)}…${d.slice(-4)}`;

// -- Conectar -----------------------------------------------------------------------------------------

function ConectarWallet({ navegador, onConectada, otra }: { navegador: WalletNavegador[] | null; onConectada: () => void; otra: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const conectar = useAccion(async (w: WalletNavegador) => {
    setError(null);
    let cuentas: unknown;
    try {
      cuentas = await w.proveedor.request({ method: "eth_requestAccounts" });
    } catch (e) {
      setError(textoErrorWallet(e));
      return null;
    }
    const direccion = Array.isArray(cuentas) ? String(cuentas[0] ?? "") : "";
    if (!direccion) {
      setError("La wallet no dio ninguna cuenta.");
      return null;
    }
    const r = await pedir(api.POST("/api/wallets", { body: { direccion, nombre: w.nombre } }));
    onConectada();
    return r;
  });

  if (navegador === null) return <Esqueleto className="h-12" />;
  if (!navegador.length) {
    return (
      <Aviso tipo="info" titulo="No hay ninguna wallet en este navegador">
        Una wallet (como MetaMask) es una extensión del navegador que guarda tus cuentas de cripto. Instálala desde{" "}
        <a href="https://metamask.io/download/" target="_blank" rel="noreferrer" className="font-semibold underline underline-offset-4">
          metamask.io
        </a>{" "}
        (u otra: Rabby, Coinbase Wallet…), crea o importa tu cuenta y recarga esta página.
      </Aviso>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {navegador.map((w) => (
          <Boton key={w.uuid} onClick={() => void conectar.ejecutar(w)} disabled={conectar.enCurso}>
            {w.icono ? (
              // El icono lo da la propia wallet (un data URI de EIP-6963): next/image no aplica.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={w.icono} alt="" className="h-5 w-5 rounded" />
            ) : (
              <Wallet aria-hidden="true" className="h-5 w-5" />
            )}
            {otra ? `Conectar otra cuenta de ${w.nombre}` : `Conectar ${w.nombre}`}
          </Boton>
        ))}
      </div>
      {error ? <p className="text-sm font-medium text-baja-texto">{error}</p> : null}
      {conectar.error ? <ErrorApiVista error={conectar.error} /> : null}
    </div>
  );
}

// -- Saldos -------------------------------------------------------------------------------------------

function Saldos({ direccion }: { direccion: string }) {
  const s = useConsulta(`wallet-saldos:${direccion}`, () => pedir(api.GET("/api/wallets/{direccion}/saldos", { params: { path: { direccion } } })));
  if (s.error) return <ErrorApiVista error={s.error} reintentar={s.recargar} />;
  if (!s.datos) return <Esqueleto className="h-24" />;
  const d = s.datos;
  return (
    <div className="space-y-3">
      <p className="text-sm text-tinta">
        En total, unos <strong className="cifras">{formatoCantidad(d.total_usd)} USD</strong>
        <span className="text-tinta-suave">
          {" "}
          · leído a las {horaSegundos(d.at)}
          {d.sin_precio ? " · lo que no tiene precio no cuenta" : ""}
        </span>
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {d.cadenas.map((c) => (
          <div key={c.cadena} className="rounded-xl border border-linea px-3 py-2">
            <p className="text-sm font-semibold text-tinta">{c.nombre}</p>
            {c.error ? (
              <p className="text-sm text-baja-texto">{c.error}</p>
            ) : c.saldos.length ? (
              <ul className="text-sm">
                {c.saldos.map((x) => (
                  <li key={x.simbolo} className="flex justify-between gap-2">
                    <span className="text-tinta">{x.simbolo}</span>
                    <span className="cifras text-tinta">
                      {formatoCantidad(x.cantidad)}
                      <span className="text-tinta-suave">{x.valor_usd !== null ? ` · ${formatoCantidad(x.valor_usd)} USD` : " · sin precio"}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-tinta-suave">Nada.</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// -- La wallet agente de Hyperliquid ---------------------------------------------------------------

function AgenteHyperliquid({ w, navegador, onCambio }: { w: S["WalletConectada"]; navegador: WalletNavegador[]; onCambio: () => void }) {
  const [paso, setPaso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const autorizar = useAccion(async (red: RedHl) => {
    setError(null);
    // La wallet que tiene esa cuenta (sin pedir permiso otra vez si ya lo dio).
    let proveedor: Proveedor | null = null;
    for (const n of navegador) {
      try {
        const cuentas = await n.proveedor.request({ method: "eth_accounts" });
        if (Array.isArray(cuentas) && cuentas.some((c) => String(c).toLowerCase() === w.direccion.toLowerCase())) {
          proveedor = n.proveedor;
          break;
        }
      } catch {
        // esa wallet no deja preguntar: se prueba la siguiente
      }
    }
    if (!proveedor) {
      setError(`Ninguna wallet de este navegador tiene abierta la cuenta ${corta(w.direccion)}: ábrela en tu wallet y vuelve a probar.`);
      return null;
    }
    try {
      setPaso("Leyendo en qué cadena está tu wallet…");
      const chain = Number.parseInt(String(await proveedor.request({ method: "eth_chainId" })), 16);
      setPaso("Preparando la autorización…");
      const p = await pedir(api.POST("/api/wallets/{direccion}/hyperliquid/preparar", { params: { path: { direccion: w.direccion } }, body: { red, chain_id: chain } }));
      setPaso("Firma «ApproveAgent» en tu wallet (no cuesta nada: no es una transacción)…");
      let firma: unknown;
      try {
        firma = await proveedor.request({ method: "eth_signTypedData_v4", params: [w.direccion, JSON.stringify(p.datos_tipados)] });
      } catch (e) {
        setError(textoErrorWallet(e));
        return null;
      }
      setPaso("Enviando la autorización a Hyperliquid…");
      const r = await pedir(
        api.POST("/api/wallets/{direccion}/hyperliquid/confirmar", { params: { path: { direccion: w.direccion } }, body: { red, nonce: p.nonce, firma: String(firma) } }),
      );
      if (red === "pruebas") {
        setPaso("Probando la conexión con la red de pruebas…");
        await pedir(api.POST("/api/conexiones/{exchange}/activar", { params: { path: { exchange: "hyperliquid" } }, body: { red: "pruebas" } }));
      }
      onCambio();
      return r;
    } finally {
      setPaso(null);
    }
  });
  const hecho = autorizar.resultado;
  return (
    <div className="space-y-3 rounded-xl bg-superficie-2 p-4">
      <p className="flex items-start gap-2 text-[0.9375rem] text-tinta">
        <ShieldCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-marca" />
        <span>
          <strong className="font-semibold">Operar en Hyperliquid con esta wallet.</strong> Firmas una vez y el panel opera con una wallet agente que{" "}
          <strong className="font-semibold">no puede retirar ni mover tus fondos</strong>. Su clave se queda en este equipo.
        </span>
      </p>
      <div className="flex flex-wrap gap-2">
        <Boton tamano="compacto" variante="primario" disabled={autorizar.enCurso} onClick={() => void autorizar.ejecutar("pruebas")}>
          {w.agente_hyperliquid.includes("pruebas") ? "Volver a autorizar en pruebas" : "Autorizar en la red de pruebas"}
        </Boton>
        <Boton tamano="compacto" variante="real" disabled={autorizar.enCurso} onClick={() => void autorizar.ejecutar("real")}>
          {w.agente_hyperliquid.includes("real") ? "Volver a autorizar con dinero real" : "Autorizar con dinero real"}
        </Boton>
      </div>
      <p className="text-sm text-tinta-suave">
        Empieza por la red de pruebas: necesita USDC de pruebas en tu cuenta de la red de pruebas de Hyperliquid. Para quitar el agente también en Hyperliquid:
        app.hyperliquid.xyz → API.
      </p>
      {paso ? (
        <p className="flex items-center gap-2 text-sm font-medium text-tinta" role="status">
          <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />
          {paso}
        </p>
      ) : null}
      {error ? <p className="text-sm font-medium text-baja-texto">{error}</p> : null}
      {autorizar.error ? <ErrorApiVista error={autorizar.error} /> : null}
      {hecho ? (
        <Aviso tipo="hecho" vivo>
          {hecho.texto}
        </Aviso>
      ) : null}
    </div>
  );
}

// -- La sección -----------------------------------------------------------------------------------------

function TarjetaWallet({ w, navegador, onCambio }: { w: S["WalletConectada"]; navegador: WalletNavegador[]; onCambio: () => void }) {
  const [abierta, setAbierta] = useState(false);
  const quitar = useAccion(async () => {
    await pedir(api.DELETE("/api/wallets/{direccion}", { params: { path: { direccion: w.direccion } } }));
    onCambio();
    return true;
  });
  return (
    <Tarjeta className="space-y-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-semibold text-tinta">
            {w.nombre}
            <code className="font-mono text-sm font-normal text-tinta-suave" title={w.direccion}>
              {corta(w.direccion)}
            </code>
            {w.agente_hyperliquid.map((r) => (
              <Chip key={r} tono={r === "real" ? "real" : "pruebas"}>
                Hyperliquid · {r === "real" ? "dinero real" : "pruebas"}
              </Chip>
            ))}
          </p>
          <p className="text-sm text-tinta-suave">Solo la dirección: el panel no tiene ni pide la clave de tu wallet.</p>
        </div>
        <div className="flex gap-2">
          <Boton tamano="compacto" variante="fantasma" onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}>
            <ChevronDown aria-hidden="true" className={abierta ? "h-4 w-4 rotate-180" : "h-4 w-4"} />
            {abierta ? "Cerrar" : "Saldos y Hyperliquid"}
          </Boton>
          <Boton tamano="compacto" variante="fantasma" disabled={quitar.enCurso} onClick={() => void quitar.ejecutar()} title="Quitarla del panel (y la clave del agente de este equipo)">
            <Trash2 aria-hidden="true" className="h-4 w-4" />
            Desconectar
          </Boton>
        </div>
      </div>
      {quitar.error ? <ErrorApiVista error={quitar.error} /> : null}
      {abierta ? (
        <div className="space-y-4">
          <Saldos direccion={w.direccion} />
          <AgenteHyperliquid w={w} navegador={navegador} onCambio={onCambio} />
        </div>
      ) : null}
    </Tarjeta>
  );
}

/**
 * Wallets (docs/panel-v5.md §5), dentro de Conexiones: conectar la wallet del navegador (solo su
 * dirección), ver lo que tiene en Ethereum, Arbitrum, Base y Hyperliquid, y autorizar con ella la
 * wallet agente para operar en Hyperliquid sin que el panel pueda retirar tus fondos.
 */
export function Wallets() {
  const navegador = useWalletsNavegador();
  const [vuelta, setVuelta] = useState(0);
  const lista = useConsulta(`wallets:${vuelta}`, () => pedir(api.GET("/api/wallets")));
  const recargar = () => setVuelta((v) => v + 1);
  return (
    <section id="wallets" aria-labelledby="titulo-wallets" className="space-y-3">
      <h3 id="titulo-wallets" className="flex items-center gap-2 text-base font-semibold text-tinta">
        <Wallet aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
        Wallets
      </h3>
      <p className="text-[0.9375rem] text-tinta-suave">
        MetaMask, Rabby, Coinbase Wallet, Phantom… Conectar es darle al panel tu dirección pública para ver tus saldos; para operar en Hyperliquid, una firma
        que autoriza a una wallet agente que no puede retirar.
      </p>
      {lista.error ? <ErrorApiVista error={lista.error} reintentar={lista.recargar} /> : null}
      {lista.datos?.wallets.map((w) => (
        <TarjetaWallet key={w.direccion} w={w} navegador={navegador ?? []} onCambio={recargar} />
      ))}
      <ConectarWallet navegador={navegador} onConectada={recargar} otra={(lista.datos?.wallets.length ?? 0) > 0} />
    </section>
  );
}
