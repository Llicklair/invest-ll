import { Fragment, type ReactNode } from "react";

import { clases } from "./ui";

/**
 * Markdown de las respuestas de Claude, sin HTML: se convierte a elementos de React a mano (nunca
 * `dangerouslySetInnerHTML`), asi que un texto que traiga etiquetas se ve como texto. Lo que
 * entiende: parrafos, listas (- y 1.), tablas, citas, bloques de codigo, encabezados (como
 * parrafos destacados: no rompen el esquema de titulos de la pagina), **negrita**, *cursiva*,
 * `codigo` y enlaces http(s).
 */
export function Markdown({ texto, className }: { texto: string; className?: string }) {
  return <div className={clases("space-y-3 [overflow-wrap:anywhere]", className)}>{bloques(texto.replace(/\r\n/g, "\n"))}</div>;
}

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\s\n][^*\n]*\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))/g;

function enLinea(texto: string, clave = ""): ReactNode[] {
  const partes = texto.split(INLINE);
  return partes.map((p, i) => {
    const k = `${clave}-${i}`;
    if (i % 2 === 0) return <Fragment key={k}>{p}</Fragment>;
    if (p.startsWith("`")) {
      return (
        <code key={k} className="rounded-md bg-superficie px-1.5 py-0.5 font-mono text-[0.85em] text-tinta">
          {p.slice(1, -1)}
        </code>
      );
    }
    if (p.startsWith("**") || p.startsWith("__")) {
      return (
        <strong key={k} className="font-semibold">
          {enLinea(p.slice(2, -2), k)}
        </strong>
      );
    }
    if (p.startsWith("[")) {
      const m = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(p);
      if (m) {
        return (
          <a key={k} href={m[2]} target="_blank" rel="noopener noreferrer" className="font-semibold text-marca underline underline-offset-4">
            {m[1]}
            <span className="sr-only"> (se abre en otra pestaña)</span>
          </a>
        );
      }
    }
    if (p.startsWith("*")) return <em key={k}>{enLinea(p.slice(1, -1), k)}</em>;
    return <Fragment key={k}>{p}</Fragment>;
  });
}

function conSaltos(lineas: string[], clave: string): ReactNode[] {
  return lineas.flatMap((l, i) => (i === 0 ? enLinea(l, `${clave}-${i}`) : [<br key={`${clave}-br-${i}`} />, ...enLinea(l, `${clave}-${i}`)]));
}

function celdas(linea: string): string[] {
  return linea
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

function bloques(texto: string): ReactNode[] {
  const lineas = texto.split("\n");
  const salida: ReactNode[] = [];
  let i = 0;
  let n = 0;
  const clave = () => `b${n++}`;
  while (i < lineas.length) {
    const linea = lineas[i] ?? "";
    if (linea.trim() === "") {
      i++;
      continue;
    }
    if (linea.trimStart().startsWith("```")) {
      const codigo: string[] = [];
      i++;
      while (i < lineas.length && !(lineas[i] ?? "").trimStart().startsWith("```")) codigo.push(lineas[i++] ?? "");
      i++;
      salida.push(
        <pre key={clave()} className="overflow-x-auto rounded-xl bg-superficie p-3 font-mono text-[0.8125rem] leading-relaxed text-tinta">
          <code>{codigo.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    const encabezado = /^(#{1,6})\s+(.*)$/.exec(linea);
    if (encabezado) {
      salida.push(
        <p key={clave()} className="pt-1 font-semibold text-tinta">
          {enLinea(encabezado[2] ?? "", `h${n}`)}
        </p>,
      );
      i++;
      continue;
    }
    if (linea.trimStart().startsWith("|") && (lineas[i + 1] ?? "").includes("-") && /^\s*\|?[\s:|-]+\|?\s*$/.test(lineas[i + 1] ?? "")) {
      const cabecera = celdas(linea);
      i += 2;
      const filas: string[][] = [];
      while (i < lineas.length && (lineas[i] ?? "").trimStart().startsWith("|")) filas.push(celdas(lineas[i++] ?? ""));
      const k = clave();
      salida.push(
        <div key={k} className="relative overflow-x-auto rounded-xl border border-linea bg-superficie">
          <table className="cifras w-full text-sm">
            <thead>
              <tr className="bg-superficie-2 text-left">
                {cabecera.map((c, j) => (
                  <th key={j} scope="col" className={clases("px-3 py-2 font-semibold text-tinta", j > 0 && "text-right")}>
                    {enLinea(c, `${k}-c${j}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((f, r) => (
                <tr key={r} className="border-t border-linea">
                  {f.map((c, j) =>
                    j === 0 ? (
                      <th key={j} scope="row" className="px-3 py-2 text-left font-normal text-tinta-suave">
                        {enLinea(c, `${k}-${r}-${j}`)}
                      </th>
                    ) : (
                      <td key={j} className="px-3 py-2 text-right text-tinta">
                        {enLinea(c, `${k}-${r}-${j}`)}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(linea) || /^\s*\d+[.)]\s+/.test(linea)) {
      const ordenada = /^\s*\d+[.)]\s+/.test(linea);
      const items: string[] = [];
      while (i < lineas.length && (ordenada ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/).test(lineas[i] ?? "")) {
        items.push((lineas[i] ?? "").replace(ordenada ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/, ""));
        i++;
      }
      const k = clave();
      const Lista = ordenada ? "ol" : "ul";
      salida.push(
        <Lista key={k} className={clases("space-y-1 pl-5", ordenada ? "list-decimal" : "list-disc", "marker:text-tinta-suave")}>
          {items.map((it, j) => (
            <li key={j}>{enLinea(it, `${k}-${j}`)}</li>
          ))}
        </Lista>,
      );
      continue;
    }
    if (linea.trimStart().startsWith(">")) {
      const cita: string[] = [];
      while (i < lineas.length && (lineas[i] ?? "").trimStart().startsWith(">")) cita.push((lineas[i++] ?? "").replace(/^\s*>\s?/, ""));
      const k = clave();
      salida.push(
        <blockquote key={k} className="border-l-2 border-linea-control pl-3 text-tinta-suave">
          {conSaltos(cita, k)}
        </blockquote>,
      );
      continue;
    }
    const parrafo: string[] = [];
    while (i < lineas.length && (lineas[i] ?? "").trim() !== "" && !/^(#{1,6}\s|```|\s*[-*]\s+|\s*\d+[.)]\s+|\s*\||\s*>)/.test(lineas[i] ?? "")) parrafo.push(lineas[i++] ?? "");
    if (!parrafo.length) {
      // Una linea que parecia otra cosa y no lo era (p. ej. "|" suelto): va como texto.
      parrafo.push(lineas[i++] ?? "");
    }
    const k = clave();
    salida.push(<p key={k}>{conSaltos(parrafo, k)}</p>);
  }
  return salida;
}
