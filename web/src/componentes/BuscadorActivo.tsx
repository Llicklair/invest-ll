"use client";

import { Check, Search } from "lucide-react";
import { useId, useState, type KeyboardEvent } from "react";

import { enLaMoneda } from "@/lib/nombres";

import { ESTILO_ENTRADA, clases } from "./ui";

export interface OpcionActivo {
  simbolo: string;
  /** Nombre llano: "Bitcoin", "Bolsa de EE.UU.". */
  nombre: string;
  /** Moneda de su precio ("USD", "USDT", "EUR"); "" si no se sabe (uno escrito a mano). */
  moneda: string;
  cripto: boolean;
}

const MAXIMO = 8;

function normal(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/**
 * Elegir un activo por su nombre llano ("oro", "bitcoin", "bolsa") en vez de teclear su simbolo.
 * Es un combobox accesible (patron de la ARIA APG): el campo filtra, las flechas recorren la
 * lista, Intro elige y Escape la cierra. La lista va en el flujo, no flotando: dentro de una hoja
 * con scroll no se corta ni tapa nada. Si lo que buscas no esta, se puede usar tal cual.
 */
export function BuscadorActivo({
  etiqueta,
  ayuda,
  opciones,
  valor,
  onCambio,
}: {
  etiqueta: string;
  ayuda?: string;
  opciones: readonly OpcionActivo[];
  valor: OpcionActivo | null;
  onCambio: (o: OpcionActivo | null) => void;
}) {
  const id = useId();
  const idLista = `${id}-lista`;
  const idAyuda = `${id}-ayuda`;
  const [texto, setTexto] = useState(valor?.nombre ?? "");
  const [abierto, setAbierto] = useState(false);
  const [activo, setActivo] = useState(0);

  const q = normal(texto);
  const coinciden = (q && !valor ? opciones.filter((o) => normal(`${o.nombre} ${o.simbolo}`).includes(q)) : [...opciones])
    // Primero lo que empieza por lo escrito ("oro" antes que "bonos de largo plazo").
    .sort((a, b) => Number(!normal(a.nombre).startsWith(q)) - Number(!normal(b.nombre).startsWith(q)))
    .slice(0, MAXIMO);
  const exacto = opciones.some((o) => normal(o.simbolo) === q || normal(o.nombre) === q);
  const otro: OpcionActivo | null =
    q && !valor && !exacto
      ? { simbolo: texto.trim().toUpperCase(), nombre: texto.trim().toUpperCase(), moneda: "", cripto: texto.includes("/") }
      : null;
  const lista = otro ? [...coinciden, otro] : coinciden;
  const visible = abierto && lista.length > 0;
  const indice = Math.min(activo, Math.max(0, lista.length - 1));

  const elegir = (o: OpcionActivo) => {
    onCambio(o);
    setTexto(o.nombre);
    setAbierto(false);
  };

  const teclas = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAbierto(true);
      setActivo((i) => Math.min(i + 1, lista.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && visible) {
      e.preventDefault();
      const o = lista[indice];
      if (o) elegir(o);
    } else if (e.key === "Escape" && abierto) {
      // Que el Escape cierre la lista, no la hoja entera.
      e.preventDefault();
      e.stopPropagation();
      setAbierto(false);
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[0.9375rem] font-medium text-tinta">
        {etiqueta}
      </label>
      <div className="relative">
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3.5 h-5 w-5 -translate-y-1/2 text-tinta-suave" />
        <input
          id={id}
          role="combobox"
          aria-expanded={visible}
          aria-controls={idLista}
          aria-autocomplete="list"
          aria-activedescendant={visible ? `${id}-op-${indice}` : undefined}
          aria-describedby={ayuda ? idAyuda : undefined}
          autoComplete="off"
          spellCheck={false}
          value={texto}
          placeholder="Busca: oro, bitcoin, bolsa…"
          onChange={(e) => {
            setTexto(e.target.value);
            setAbierto(true);
            setActivo(0);
            if (valor) onCambio(null);
          }}
          onFocus={(e) => {
            e.currentTarget.select();
            setAbierto(true);
          }}
          onBlur={() => setAbierto(false)}
          onKeyDown={teclas}
          className={clases(ESTILO_ENTRADA, "pl-11")}
        />
      </div>
      {ayuda ? (
        <p id={idAyuda} className="text-sm text-tinta-suave">
          {ayuda}
        </p>
      ) : null}
      <ul
        id={idLista}
        role="listbox"
        aria-label={etiqueta}
        hidden={!visible}
        className="max-h-72 overflow-y-auto rounded-xl border border-linea bg-superficie p-1 shadow-suave"
      >
        {lista.map((o, i) => {
          const elegido = valor?.simbolo === o.simbolo;
          const esOtro = o === otro;
          return (
            <li
              key={`${o.simbolo}-${esOtro ? "otro" : "lista"}`}
              id={`${id}-op-${i}`}
              role="option"
              aria-selected={i === indice}
              // mousedown: que elegir no dispare antes el blur que cierra la lista.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => elegir(o)}
              onMouseEnter={() => setActivo(i)}
              className={clases(
                "flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 py-2",
                i === indice ? "bg-superficie-2" : undefined,
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block text-[0.9375rem] text-tinta [overflow-wrap:anywhere]">
                  {esOtro ? <>Otro: usar «{o.simbolo}» tal cual</> : o.nombre}
                </span>
                <span className="block text-sm text-tinta-suave">
                  {esOtro
                    ? "Para algo que no está en la lista: escríbelo como en tu bróker o en Binance."
                    : `${o.simbolo} · precio ${enLaMoneda(o.moneda)}`}
                </span>
              </span>
              {elegido ? <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-marca" /> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
