/**
 * Una wallet falsa para `npm run dev:mock` (docs/panel-v5.md §5): se anuncia por EIP-6963 como
 * "MetaMask (ejemplo)" y contesta a lo que pide la sección Wallets (cuentas, cadena, firmar).
 * La firma es de mentira: con los datos de ejemplo nada sale a Hyperliquid. En un `next build`
 * esto ni se empaqueta (solo lo importa la rama de desarrollo con datos de ejemplo).
 */
import type { components } from "@/api/esquema";

type S = components["schemas"];

export const DIRECCION_EJEMPLO = "0x5A0b54D5dc17e0AadC383d2db43B0a0D3E029c4c";

const ICONO =
  "data:image/svg+xml;base64," +
  btoa('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#f6851b"/><path d="M9 11l7 5 7-5-2 10H11z" fill="#fff"/></svg>');

let instalada = false;

export function instalarWalletFalsa(): void {
  if (instalada) return;
  instalada = true;
  const proveedor = {
    async request({ method }: { method: string; params?: unknown[] }): Promise<unknown> {
      await new Promise((r) => setTimeout(r, 400));
      switch (method) {
        case "eth_requestAccounts":
        case "eth_accounts":
          return [DIRECCION_EJEMPLO.toLowerCase()];
        case "eth_chainId":
          return "0xa4b1";
        case "eth_signTypedData_v4":
          return `0x${"1b".repeat(65)}`;
        default:
          throw Object.assign(new Error(`método no soportado en el ejemplo: ${method}`), { code: 4200 });
      }
    },
  };
  const anunciar = () =>
    window.dispatchEvent(
      new CustomEvent("eip6963:announceProvider", {
        detail: Object.freeze({ info: { uuid: "ejemplo-metamask", name: "MetaMask (ejemplo)", icon: ICONO, rdns: "io.metamask.ejemplo" }, provider: proveedor }),
      }),
    );
  window.addEventListener("eip6963:requestProvider", anunciar);
  anunciar();
}

// -- La API de wallets, de ejemplo ----------------------------------------------------------------

interface WalletMock {
  direccion: string;
  nombre: string;
  conectada: string;
  agente: ("pruebas" | "real")[];
}

const wallets: WalletMock[] = [];

function json(datos: unknown, status = 200): Response {
  return new Response(JSON.stringify(datos), { status, headers: { "content-type": "application/json" } });
}

function fallo(status: number, detail: string): Response {
  return json({ detail }, status);
}

export function esRutaWallets(ruta: string): boolean {
  return /^\/api\/wallets(\/|$)/.test(ruta);
}

function aContrato(w: WalletMock): S["WalletConectada"] {
  return { direccion: w.direccion, nombre: w.nombre, conectada: w.conectada, agente_hyperliquid: w.agente };
}

export async function responderWallets(peticion: Request, url: URL): Promise<Response> {
  const ruta = url.pathname;
  const metodo = peticion.method.toUpperCase();
  await new Promise((r) => setTimeout(r, 150));
  if (metodo === "GET" && ruta === "/api/wallets") return json({ wallets: wallets.map(aContrato) } satisfies S["Wallets"]);
  if (metodo === "POST" && ruta === "/api/wallets") {
    const cuerpo = (await peticion.json()) as { direccion?: string; nombre?: string };
    if (!/^0x[0-9a-fA-F]{40}$/.test(cuerpo.direccion ?? "")) return fallo(422, "Eso no es una dirección de wallet (0x y 40 caracteres).");
    const direccion = DIRECCION_EJEMPLO;
    if (!wallets.some((w) => w.direccion === direccion)) wallets.push({ direccion, nombre: cuerpo.nombre ?? "Wallet", conectada: new Date().toISOString(), agente: [] });
    return json(aContrato(wallets.find((w) => w.direccion === direccion) as WalletMock) satisfies S["WalletConectada"], 201);
  }
  const m = /^\/api\/wallets\/([^/]+)(\/saldos|\/hyperliquid\/preparar|\/hyperliquid\/confirmar)?$/.exec(ruta);
  const w = m ? wallets.find((x) => x.direccion.toLowerCase() === decodeURIComponent(m[1] ?? "").toLowerCase()) : undefined;
  if (!m || !w) return fallo(404, "No hay ninguna wallet así conectada.");
  const resto = m[2] ?? "";
  if (metodo === "DELETE" && resto === "") {
    wallets.splice(wallets.indexOf(w), 1);
    return new Response(null, { status: 204 });
  }
  if (metodo === "GET" && resto === "/saldos") {
    return json({
      direccion: w.direccion,
      cadenas: [
        { cadena: "ethereum", nombre: "Ethereum", saldos: [{ simbolo: "ETH", cantidad: "0.42", valor_usd: "1003.80" }], error: null },
        { cadena: "arbitrum", nombre: "Arbitrum", saldos: [{ simbolo: "USDC", cantidad: "250", valor_usd: "250.00" }], error: null },
        { cadena: "base", nombre: "Base", saldos: [], error: "No se pudo leer Base: se cortó (ejemplo)." },
        { cadena: "hyperliquid", nombre: "Hyperliquid", saldos: [{ simbolo: "USDC", cantidad: "120", valor_usd: "120.00" }, { simbolo: "HYPE", cantidad: "3", valor_usd: "237.37" }], error: null },
      ],
      total_usd: "1611.17",
      sin_precio: false,
      at: new Date().toISOString(),
    } satisfies S["SaldosWallet"]);
  }
  if (metodo === "POST" && resto === "/hyperliquid/preparar") {
    return json({
      datos_tipados: { domain: { name: "HyperliquidSignTransaction" }, primaryType: "HyperliquidTransaction:ApproveAgent", message: {} },
      agente: "0x9d3f0000000000000000000000000000000071a2",
      nonce: Date.now(),
      texto: "Tu wallet te pedirá firmar «ApproveAgent» (ejemplo).",
    } satisfies S["AgentePreparado"]);
  }
  if (metodo === "POST" && resto === "/hyperliquid/confirmar") {
    const cuerpo = (await peticion.json()) as { red?: "pruebas" | "real" };
    const red = cuerpo.red === "real" ? "real" : "pruebas";
    if (!w.agente.includes(red)) w.agente.push(red);
    return json({
      red,
      agente: "0x9d3f0000000000000000000000000000000071a2",
      texto: `Hyperliquid aceptó la wallet agente: ya está guardada en este equipo. ${red === "pruebas" ? "Ahora actívala para probar la conexión." : "Para operar con dinero real, actívala en Hyperliquid (Conexiones)."}`,
    } satisfies S["AgenteConectado"]);
  }
  return fallo(404, "Ruta de wallets de ejemplo no encontrada.");
}
