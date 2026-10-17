// postbuild: corrige los ficheros de segmentos del export estatico en Windows.
//
// Next 16.3.8 escribe un fichero por segmento de cada pagina para que el router los precargue,
// con nombre `__next.<segmento>.<segmento>.txt`. Para formarlo reemplaza "/" por "." en la ruta
// relativa del segmento (next/dist/export/index.js -> convertSegmentPathToStaticExportFilename),
// pero en Windows esa ruta viene con "\" y sale un DIRECTORIO: out/mercado/__next.mercado/__PAGE__.txt.
// El navegador pide out/mercado/__next.mercado.__PAGE__.txt, recibe un 404 por cada enlace y
// navega por el camino lento. Aqui se aplanan esos directorios al nombre que pide el cliente.
// En Linux/macOS no hay nada que aplanar y el script no hace nada.
import { readdir, rename, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "out");

async function ficheros(dir) {
  const salida = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const ruta = path.join(dir, e.name);
    if (e.isDirectory()) salida.push(...(await ficheros(ruta)));
    else salida.push(ruta);
  }
  return salida;
}

async function recorrer(dir) {
  let movidos = 0;
  for (const e of await readdir(dir, { withFileTypes: true })) {
    if (!e.isDirectory() || e.name === "_next") continue;
    const ruta = path.join(dir, e.name);
    if (e.name.startsWith("__next.")) {
      for (const f of await ficheros(ruta)) {
        const relativo = path.relative(ruta, f).split(path.sep).join(".");
        await rename(f, path.join(dir, `${e.name}.${relativo}`));
        movidos += 1;
      }
      await rm(ruta, { recursive: true, force: true });
    } else {
      movidos += await recorrer(ruta);
    }
  }
  return movidos;
}

try {
  await stat(raiz);
} catch {
  console.error(`aplanar-segmentos: no existe ${raiz}; ¿ha fallado next build?`);
  process.exit(1);
}
const movidos = await recorrer(raiz);
console.log(`aplanar-segmentos: ${movidos} fichero(s) de segmento con el nombre que pide el router`);
