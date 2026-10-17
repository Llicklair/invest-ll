import type { NextConfig } from "next";

// El panel se exporta como ficheros estaticos (`out/`) y lo sirve la propia API en `/`:
// un solo proceso y un solo puerto. Por eso no hay rutas de servidor ni server actions --
// todo se pide desde el navegador a `/api`. `trailingSlash` hace que cada pestana salga como
// `out/<ruta>/index.html`, que es lo que sirve `StaticFiles(html=True)`.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  // `next dev` escribiria AGENTS.md/CLAUDE.md en web/ al detectar un agente: el repo ya tiene
  // sus propias instrucciones y no queremos ficheros generados sin commitear.
  agentRules: false,
};

export default config;
