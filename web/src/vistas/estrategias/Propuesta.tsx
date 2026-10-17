"use client";

import { ArrowRight, Info, Scale, Sparkles, Umbrella } from "lucide-react";
import { useMemo, useState } from "react";

import { api, conPlazo, pedir } from "@/api/cliente";
import type { Estrategia, Perfil, Recomendacion } from "@/api/tipos";
import { BarraAccion } from "@/componentes/BarraAccion";
import { CampoImporte } from "@/componentes/CampoImporte";
import { GraficaTusNumeros } from "@/componentes/graficas/TusNumeros";
import { colorSerie } from "@/componentes/graficas/comun";
import { QueEsEsto } from "@/componentes/QueEsEsto";
import { TarjetaEstrategia } from "@/componentes/TarjetaEstrategia";
import { Boton, CargandoLento, Chip, ErrorApiVista, Esqueleto, Segmentado, Tarjeta, clases } from "@/componentes/ui";
import { useConsulta, useRetardado } from "@/lib/consulta";
import { euros, eurosNum, fecha, mesYAnio } from "@/lib/formato";
import { leerImporte } from "@/lib/importe";

import { Comparador } from "./Comparador";
import { CLAVE_REPARTO, asignarHuecos, useCatalogo, useSimulaciones } from "./datos";
import { ANIOS, type Respuestas } from "./estado";
import { HojaEstrategia } from "./HojaEstrategia";

export interface PartePrecargada {
  estrategia: string;
  inicial: string;
  mensual: string;
}

const POR_DEFECTO_CATALOGO = ["bolsa-equilibrada", "btc-freno"];

/** "cayeron entre un 10 % y un 80 %", con las cifras de la API (nunca escritas a mano). */
function rangoCaidas(estrategias: readonly Estrategia[]): string {
  const caidas = estrategias.map((e) => e.historico?.peor_caida).filter((x): x is number => typeof x === "number");
  if (!caidas.length) return "todas llegaron a caer bastante";
  const menor = Math.round(Math.abs(Math.max(...caidas)) * 100);
  const mayor = Math.round(Math.abs(Math.min(...caidas)) * 100);
  return menor === mayor ? `cayeron un ${menor} %` : `cayeron entre un ${menor} % y un ${mayor} %`;
}

function TextoAnio({ anio }: { anio: number }) {
  if (anio === 2021) {
    return (
      <>
        Has elegido 2021, justo antes de una caída: fíjate en cuánto cambia el resultado frente a empezar en 2018 o en 2022.
        Por eso se aporta poco a poco.
      </>
    );
  }
  return (
    <>
      Si hubieras empezado en 2021, justo antes de una caída, el resultado sería muy distinto: prueba a cambiar el año. Lo
      que pasó no es una promesa de lo que pasará.
    </>
  );
}

/** La recomendacion: el reparto en grande, una barra con sus dos partes y el porque. */
function TePropomenos({
  rec,
  huecos,
  nombres,
}: {
  rec: Recomendacion;
  huecos: Record<string, number>;
  nombres: Record<string, string>;
}) {
  return (
    <Tarjeta className="overflow-hidden">
      <div className="space-y-5 p-5 sm:p-7">
        <Chip tono="destaque" icono={<Sparkles aria-hidden="true" className="h-3.5 w-3.5" />}>
          Te proponemos
        </Chip>
        <p className="titular text-[1.75rem] leading-tight font-semibold text-tinta sm:text-[2.25rem]">
          {rec.partes.map((p, i) => (
            <span key={p.estrategia}>
              {i > 0 ? <span className="text-tinta-suave"> · </span> : null}
              <span className="whitespace-nowrap">{p.porcentaje} %</span> {p.nombre}
            </span>
          ))}
        </p>
        <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
          {rec.partes.map((p) => (
            <span key={p.estrategia} style={{ width: `${p.porcentaje}%`, background: colorSerie(huecos[p.estrategia] ?? 0) }} />
          ))}
        </div>
        <ul className="grid gap-2 sm:grid-cols-2">
          {rec.partes.map((p) => (
            <li key={p.estrategia} className="rounded-xl bg-superficie-2 px-4 py-3">
              <p className="flex items-center gap-2 text-sm font-semibold text-tinta">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: colorSerie(huecos[p.estrategia] ?? 0) }} aria-hidden="true" />
                {p.nombre}
              </p>
              <p className="cifras mt-1 text-[0.9375rem] text-tinta">
                {euros(p.inicial, { decimales: 0 })} para empezar · {euros(p.mensual, { decimales: 0 })} al mes
              </p>
            </li>
          ))}
        </ul>
      </div>
      <div className="space-y-4 border-t border-linea bg-superficie-2/60 p-5 sm:p-7">
        <div>
          <h3 className="font-semibold text-tinta">Por qué</h3>
          <ul className="mt-2 space-y-2">
            {rec.por_que.map((t) => (
              <li key={t} className="flex gap-2.5 text-[0.9375rem] leading-relaxed text-tinta">
                <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-marca" aria-hidden="true" />
                {t}
              </li>
            ))}
          </ul>
        </div>
        {rec.avisos.map((a) => (
          <p key={a} className="flex gap-2.5 text-[0.9375rem] leading-relaxed text-tinta-suave">
            <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            {a}
          </p>
        ))}
        {rec.alternativas.length ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 pt-1">
            <span className="text-[0.9375rem] text-tinta">También encajan contigo:</span>
            {rec.alternativas.map((c) => (
              <a
                key={c}
                href={`#estrategia-${c}`}
                className="inline-flex min-h-11 items-center px-1 text-[0.9375rem] font-semibold text-marca underline-offset-4 hover:underline"
              >
                {nombres[c] ?? c}
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </Tarjeta>
  );
}

/** "Tus numeros", editables aqui mismo: cambiarlos rehace las cuentas. */
function TusNumeros({ respuestas, onCambio }: { respuestas: Respuestas; onCambio: (r: Respuestas) => void }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:max-w-2xl">
      <CampoImporte
        etiqueta="Para empezar"
        valor={respuestas.inicial}
        onCambio={(v) => onCambio({ ...respuestas, inicial: v })}
        error={respuestas.inicial !== "" && leerImporte(respuestas.inicial) === null ? "Escribe solo el número." : null}
      />
      <CampoImporte
        etiqueta="Cada mes"
        valor={respuestas.mensual}
        onCambio={(v) => onCambio({ ...respuestas, mensual: v })}
        error={respuestas.mensual !== "" && leerImporte(respuestas.mensual) === null ? "Escribe solo el número." : null}
      />
    </div>
  );
}

/**
 * Paso 2 · Te proponemos (docs/panel-v2.md, 4.2): la recomendacion con su porque, la grafica con
 * tus numeros desde el ano que elijas, y todas las estrategias en tarjetas (las recomendadas
 * primero), con el resultado y el peor momento al mismo tamano. Comparar abre una hoja.
 */
export function Propuesta({
  perfil,
  respuestas,
  onRespuestas,
  desdeAnio,
  onAnio,
  onSeguir,
}: {
  perfil: Perfil | null;
  respuestas: Respuestas;
  onRespuestas: (r: Respuestas) => void;
  desdeAnio: number;
  onAnio: (a: number) => void;
  onSeguir: (partes: PartePrecargada[]) => void;
}) {
  const catalogo = useCatalogo();
  // Se recalcula cuando se deja de teclear en "Con tus numeros", no con cada tecla.
  const clavePerfil = useRetardado(perfil ? JSON.stringify(perfil) : null, 450);
  const rec = useConsulta(clavePerfil ? `recomendar:${clavePerfil}` : null, () =>
    pedir(api.POST("/api/estrategias/recomendar", { body: JSON.parse(clavePerfil ?? "{}") as Perfil, ...conPlazo() })),
  );
  const [verIgualmente, setVerIgualmente] = useState(false);
  const [comparando, setComparando] = useState(false);
  const [elegidas, setElegidas] = useState<string[]>([]);
  const [comparadorAbierto, setComparadorAbierto] = useState(false);
  const [hoja, setHoja] = useState<Estrategia | null>(null);

  // Los numeros con los que se simula. Sin cifras (0 y 0), 10.000 € de ejemplo.
  const inicialTxt = leerImporte(respuestas.inicial === "" ? (perfil ? "0" : "1000") : respuestas.inicial) ?? "0";
  const mensualTxt = leerImporte(respuestas.mensual === "" ? (perfil ? "0" : "100") : respuestas.mensual) ?? "0";
  const ejemplo = Number(inicialTxt) === 0 && Number(mensualTxt) === 0;
  const numeros = useRetardado(JSON.stringify(ejemplo ? ["10000", "0"] : [inicialTxt, mensualTxt]), 450);
  const [ini = "0", men = "0"] = JSON.parse(numeros) as string[];

  const todas = useMemo(() => (catalogo.datos?.estrategias ?? []).filter((e) => !e.laboratorio && !e.retirada), [catalogo.datos]);
  const disponibles = todas.filter((e) => e.disponible).map((e) => e.clave);
  const r = rec.datos;
  // La propuesta entera, como una sola curva ("Tu reparto"), si tiene mas de una parte y todas se
  // pueden calcular.
  const reparto =
    r && !r.no_invertir && r.partes.length > 1 && r.partes.every((p) => disponibles.includes(p.estrategia))
      ? r.partes.map((p) => ({ estrategia: p.estrategia, porcentaje: p.porcentaje }))
      : [];
  const sims = useSimulaciones(disponibles, ini, men, desdeAnio, reparto);
  const combinado = reparto.length ? (sims.datos?.get(CLAVE_REPARTO) ?? null) : null;

  const recomendadas = r ? r.partes.map((p) => p.estrategia) : [];
  const enGrafica = (recomendadas.length ? recomendadas : POR_DEFECTO_CATALOGO).filter((c) => disponibles.includes(c));
  const huecosGrafica = asignarHuecos(enGrafica, {});
  const huecosComparar = asignarHuecos(elegidas, huecosGrafica);

  const ordenadas = [...todas].sort((a, b) => {
    const ia = recomendadas.indexOf(a.clave);
    const ib = recomendadas.indexOf(b.clave);
    // Las recomendadas primero; el resto, de la mas tranquila a la mas movida.
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.riesgo - b.riesgo;
  });

  const seguir = () => {
    if (r) {
      onSeguir(r.partes.map((p) => ({ estrategia: p.estrategia, inicial: p.inicial, mensual: p.mensual })));
    } else {
      onSeguir([]);
    }
  };

  if (catalogo.error) return <ErrorApiVista error={catalogo.error} prefijo="No se pudo leer el catálogo:" reintentar={catalogo.recargar} />;
  if (rec.error) return <ErrorApiVista error={rec.error} prefijo="No se pudo calcular la propuesta:" reintentar={rec.recargar} />;
  if (!catalogo.datos || (perfil && !r)) {
    return (
      <div className="space-y-6" aria-busy="true">
        <CargandoLento
          texto={perfil ? "Calculando qué te proponemos…" : "Leyendo las estrategias…"}
          lento="Calculando las estrategias con los datos descargados… la primera vez tarda unos segundos."
        />
        <Esqueleto className="h-64" />
        <Esqueleto className="h-80" />
      </div>
    );
  }

  const bloqueado = r?.no_invertir && !verIgualmente;
  const resultadosGrafica = enGrafica.map((c) => sims.datos?.get(c)).filter((x) => x !== undefined);
  const resultadosComparar = elegidas.map((c) => sims.datos?.get(c)).filter((x) => x !== undefined);

  return (
    <div className="space-y-10 pb-24">
      <div className="max-w-2xl">
        <h2 className="titular text-[1.75rem] leading-tight font-semibold text-tinta lg:text-[2rem]">
          {r?.no_invertir ? "Antes de seguir" : perfil ? "Esto es lo que te proponemos" : "Todas las estrategias"}
        </h2>
        <p className="mt-2 text-[0.9375rem] leading-relaxed text-tinta-suave lg:text-base">
          {perfil
            ? "Sale de tus respuestas con unas reglas fijas, a la vista. Debajo, lo que habría pasado con tus números y todas las alternativas."
            : `${todas.length || "Varias"} formas de invertir, de la más tranquila a la más movida, con lo que habría pasado con unos números de ejemplo. Cámbialos por los tuyos.`}
        </p>
      </div>

      {r?.no_invertir ? (
        <Tarjeta className="space-y-4 p-5 sm:p-7">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-marca-suave text-marca" aria-hidden="true">
            <Umbrella className="h-5 w-5" strokeWidth={1.75} />
          </span>
          <p className="titular text-2xl leading-snug font-semibold text-tinta">Para este dinero, mejor no invertir</p>
          <p className="max-w-2xl text-[0.9375rem] leading-relaxed text-tinta">
            Para dinero que necesitas en menos de 2 años, ninguna de estas estrategias es buena idea: en su peor momento
            {" "}
            {rangoCaidas(todas)}. Una cuenta remunerada o un depósito encajan mejor.
          </p>
          {!verIgualmente ? (
            <Boton variante="secundario" onClick={() => setVerIgualmente(true)}>
              Seguir mirando igualmente
            </Boton>
          ) : null}
        </Tarjeta>
      ) : null}

      {bloqueado ? null : (
        <>
          {r ? (
            <TePropomenos rec={r} huecos={huecosGrafica} nombres={Object.fromEntries(todas.map((e) => [e.clave, e.nombre]))} />
          ) : null}

          <section aria-labelledby="numeros-titulo" className="space-y-5">
            <div>
              <h3 id="numeros-titulo" className="titular text-2xl font-semibold text-tinta">
                Con tus números
              </h3>
              <p className="mt-1 text-[0.9375rem] text-tinta-suave">
                {ejemplo
                  ? "No has puesto cifras: usamos 10.000 € de ejemplo."
                  : "Lo que habrías tenido si hubieras empezado a principios de ese año, poniendo esto:"}
              </p>
            </div>
            <TusNumeros respuestas={respuestas} onCambio={onRespuestas} />
            <Segmentado
              repartido
              etiqueta="Empezar en"
              opciones={ANIOS.map((a) => ({ valor: String(a), texto: String(a) }))}
              valor={String(desdeAnio)}
              onCambio={(v) => onAnio(Number(v))}
            />
            {sims.error ? <ErrorApiVista error={sims.error} prefijo="No se pudieron calcular tus números:" reintentar={sims.recargar} /> : null}
            {resultadosGrafica.length ? (
              <GraficaTusNumeros
                titulo={r ? "Lo que habrías tenido con lo que te proponemos" : "Dos ejemplos: una de bolsa y una de cripto"}
                series={resultadosGrafica.map((x) => ({ resultado: x, hueco: huecosGrafica[x.clave] ?? 0 }))}
                combinado={combinado}
                atenuada={sims.cargando}
                pie={
                  <>
                    Desde el {fecha(resultadosGrafica[0]?.desde)}.{" "}
                    {combinado
                      ? "La línea gruesa es tu reparto: tu dinero repartido como te proponemos. Las de color, cada estrategia con todo tu dinero, por separado."
                      : "Cada línea es una estrategia con todo tu dinero, por separado."}{" "}
                    <TextoAnio anio={desdeAnio} />
                  </>
                }
              />
            ) : sims.cargando ? (
              <Esqueleto className="h-[26rem]" />
            ) : null}
            {combinado ? (
              <div className="grid gap-2 sm:grid-cols-2 lg:max-w-2xl">
                <p className="rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">
                  Con tu reparto <strong className="cifras font-semibold">tendrías {eurosNum(combinado.valor_final)}</strong>
                  <span className="cifras block text-sm text-tinta-suave">Pusiste {eurosNum(combinado.aportado)}</span>
                </p>
                <p className="rounded-xl bg-superficie-2 px-4 py-3 text-[0.9375rem] text-tinta">
                  En el peor momento <strong className="cifras font-semibold">valía {eurosNum(combinado.peor_momento_valor)}</strong>
                  <span className="cifras block text-sm text-tinta-suave">
                    En {mesYAnio(combinado.peor_momento_fecha)}, cuando habías puesto {eurosNum(combinado.peor_momento_aportado)}
                  </span>
                </p>
              </div>
            ) : null}
            {resultadosGrafica.some((x) => x.aviso) ? (
              <p className="text-sm text-tinta-suave">{resultadosGrafica.map((x) => x.aviso).filter(Boolean).join(" ")}</p>
            ) : null}
            <QueEsEsto clave="peor-momento" />
          </section>

          <section aria-labelledby="todas-titulo" className="space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h3 id="todas-titulo" className="titular text-2xl font-semibold text-tinta">
                  {r ? "Todas las estrategias" : "Elige con calma"}
                </h3>
                <p className="mt-1 text-[0.9375rem] text-tinta-suave">
                  {r ? "Las que te proponemos van primero y marcadas." : "De la más tranquila a la más movida."}
                </p>
              </div>
              <Boton
                variante="secundario"
                aria-pressed={comparando}
                onClick={() => {
                  setComparando((c) => !c);
                  if (comparando) setElegidas([]);
                }}
              >
                <Scale aria-hidden="true" className="h-4 w-4" />
                {comparando ? "Dejar de comparar" : "Comparar"}
              </Boton>
            </div>
            {comparando ? (
              <p className="text-[0.9375rem] text-tinta" aria-live="polite">
                Marca entre 2 y 4 estrategias para verlas juntas.
              </p>
            ) : null}
            <div className="grid gap-4 xl:grid-cols-2">
              {ordenadas.map((e) => {
                const parte = r?.partes.find((p) => p.estrategia === e.clave);
                const elegida = elegidas.includes(e.clave);
                return (
                  <TarjetaEstrategia
                    key={e.clave}
                    estrategia={e}
                    simulado={sims.datos?.get(e.clave) ?? null}
                    cargando={sims.cargando}
                    desdeAnio={desdeAnio}
                    ejemplo={ejemplo}
                    recomendada={parte ? parte.porcentaje : null}
                    color={enGrafica.includes(e.clave) ? colorSerie(huecosGrafica[e.clave] ?? 0) : null}
                    comparando={comparando}
                    elegida={elegida}
                    bloqueoComparar={!e.disponible ? "Faltan datos para calcularla" : elegidas.length >= 4 ? "Como mucho cuatro a la vez" : null}
                    onElegir={(si) => setElegidas((xs) => (si ? [...xs, e.clave] : xs.filter((x) => x !== e.clave)))}
                    onVerMas={() => setHoja(e)}
                  />
                );
              })}
            </div>
            {catalogo.datos.nota ? <p className="text-sm text-tinta-suave">{catalogo.datos.nota}</p> : null}
          </section>
        </>
      )}

      {bloqueado ? null : (
      <BarraAccion>
          {comparando ? (
            <>
              <p className="text-[0.9375rem] text-tinta" aria-live="polite">
                <strong className="font-semibold">{elegidas.length}</strong> {elegidas.length === 1 ? "elegida" : "elegidas"}
                <span className="text-tinta-suave"> · de 2 a 4</span>
              </p>
              <Boton variante="primario" disabled={elegidas.length < 2} onClick={() => setComparadorAbierto(true)}>
                Ver la comparación
              </Boton>
            </>
          ) : (
            <>
              <p className={clases("hidden text-[0.9375rem] text-tinta-suave sm:block")}>
                {r ? "¿Te encaja? Ajustas los importes en el siguiente paso." : "Elegirás la estrategia y los importes en el siguiente paso."}
              </p>
              <Boton variante="primario" onClick={seguir} disabled={bloqueado} className="max-sm:flex-1">
                {r ? "Seguir con esta propuesta" : "Hacer mi plan"}
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </Boton>
            </>
          )}
      </BarraAccion>
      )}

      <HojaEstrategia estrategia={hoja} onCerrar={() => setHoja(null)} />
      <Comparador
        abierto={comparadorAbierto}
        onCerrar={() => setComparadorAbierto(false)}
        resultados={resultadosComparar}
        huecos={huecosComparar}
        desdeAnio={desdeAnio}
        onAnio={onAnio}
        cargando={sims.cargando}
        error={sims.error}
        ejemplo={ejemplo}
      />
    </div>
  );
}
