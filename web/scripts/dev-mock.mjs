// `npm run dev:mock`: el servidor de desarrollo con las respuestas de ejemplo de web/mocks/ en vez
// de la API. Solo para mirar las pantallas sin backend; `next build` nunca lo incluye.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const next = require.resolve("next/dist/bin/next");
const puerto = process.env.PORT ?? "3000";

const hijo = spawn(process.execPath, [next, "dev", "--port", puerto], {
  stdio: "inherit",
  env: { ...process.env, NEXT_PUBLIC_MOCK: "1" },
});
hijo.on("exit", (codigo) => process.exit(codigo ?? 0));
for (const senal of ["SIGINT", "SIGTERM"]) process.on(senal, () => hijo.kill(senal));
