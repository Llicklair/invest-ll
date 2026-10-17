"use client";

import { ClipboardList } from "lucide-react";
import { useEffect } from "react";

import { api, pedir } from "@/api/cliente";
import { Asistente } from "@/componentes/Asistente";
import { CargandoLento, Encabezado, ErrorApiVista, Tarjeta } from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAncla } from "@/lib/ancla";
import { useConsulta } from "@/lib/consulta";

import { Cuestionario } from "./Cuestionario";
import { useCatalogo } from "./datos";
import { perfilDe, useRecorrido, type Recorrido } from "./estado";
import { Propuesta, type PartePrecargada } from "./Propuesta";
import { TuPlan, borradorDe } from "./TuPlan";

const PASOS = ["Cuéntanos", "Te proponemos", "Tu plan"] as const;

/** Mirar todas sin responder: con unos numeros de ejemplo a la vista (y editables), no en blanco. */
function aCatalogo(r: Recorrido): Partial<Recorrido> {
  return {
    via: "catalogo",
    paso: 1,
    respuestas: { ...r.respuestas, inicial: r.respuestas.inicial || "1.000", mensual: r.respuestas.mensual || "100" },
  };
}

function quitarAncla() {
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}

/**
 * Mi plan (antes Estrategias → Para tu plan): ¿como invierto a largo plazo? Un asistente en tres
 * pasos (docs/panel-v2.md, 4.2; docs/panel-v5.md, seccion 2). El recorrido
 * se guarda en la pestana; `#catalogo` entra a mirar todas sin responder y `#plan` abre tu plan
 * para cambiarlo.
 */
export function Estrategias() {
  const { versionDatos } = useEstado();
  const [r, cambiar] = useRecorrido();
  const [ancla] = useAncla();
  const catalogo = useCatalogo();
  const plan = useConsulta(`plan:${versionDatos}`, () => pedir(api.GET("/api/plan")));
  const planActual = plan.datos?.plan ?? null;

  // Entradas por ancla: desde la bienvenida ("Ya se lo que quiero") o desde "Cambiar mi plan".
  useEffect(() => {
    if (ancla === "catalogo") {
      cambiar(aCatalogo);
      quitarAncla();
    } else if (ancla === "plan" && (plan.datos || plan.error)) {
      cambiar({ paso: 2, precarga: plan.datos?.plan?.partes ?? [], entrada: Date.now() });
      quitarAncla();
    }
  }, [ancla, plan.datos, plan.error, cambiar]);

  const perfil = r.via === "perfil" ? perfilDe(r.respuestas) : null;
  // Si se recarga en el paso 2 sin respuestas completas, se vuelve a las preguntas.
  const paso = r.paso === 1 && r.via === "perfil" && !perfil ? 0 : r.paso;

  const irAlPlan = (partes: PartePrecargada[]) => {
    cambiar({ paso: 2, precarga: partes, entrada: Date.now() });
    window.scrollTo({ top: 0 });
  };

  const partesParaPlan = r.precarga ?? planActual?.partes ?? [];

  return (
    <div>
      <Encabezado
        titulo="Mi plan"
        bajada="Tu inversión a largo plazo: cinco preguntas, una propuesta explicada y tu plan."
      />

      {planActual && paso !== 2 ? (
        <Tarjeta className="mb-8 flex flex-wrap items-center justify-between gap-4 p-5">
          <p className="flex items-center gap-3 text-[0.9375rem] text-tinta">
            <ClipboardList aria-hidden="true" className="h-5 w-5 text-marca" strokeWidth={1.75} />
            Ya tienes un plan guardado. Puedes volver a responder o cambiarlo directamente.
          </p>
          <button
            type="button"
            onClick={() => irAlPlan(planActual.partes)}
            className="inline-flex min-h-11 items-center font-semibold text-marca underline-offset-4 hover:underline"
          >
            Ver o cambiar mi plan
          </button>
        </Tarjeta>
      ) : null}

      <Asistente
        etiqueta="Pasos para elegir estrategia"
        pasos={PASOS}
        actual={paso}
        alcanzado={r.alcanzado}
        onIr={(i) => cambiar({ paso: i as 0 | 1 | 2 })}
      >
        {paso === 0 ? (
          <Cuestionario
            respuestas={r.respuestas}
            onCambio={(respuestas) => cambiar({ respuestas })}
            onTerminar={() => {
              cambiar({ paso: 1, via: "perfil" });
              window.scrollTo({ top: 0 });
            }}
            onCatalogo={() => {
              cambiar(aCatalogo);
              window.scrollTo({ top: 0 });
            }}
          />
        ) : null}

        {paso === 1 ? (
          <>
            {r.via === "catalogo" ? (
              <p className="mb-6 text-[0.9375rem] text-tinta-suave">
                Estás mirando sin responder.{" "}
                <button
                  type="button"
                  onClick={() => cambiar({ paso: 0, via: "perfil" })}
                  className="inline-flex min-h-11 items-center font-semibold text-marca underline-offset-4 hover:underline"
                >
                  Responder las cinco preguntas
                </button>
              </p>
            ) : null}
            <Propuesta
              perfil={perfil}
              respuestas={r.respuestas}
              onRespuestas={(respuestas) => cambiar({ respuestas })}
              desdeAnio={r.desdeAnio}
              onAnio={(desdeAnio) => cambiar({ desdeAnio })}
              onSeguir={irAlPlan}
            />
          </>
        ) : null}

        {paso === 2 ? (
          catalogo.error ? (
            <ErrorApiVista error={catalogo.error} reintentar={catalogo.recargar} />
          ) : plan.error ? (
            <ErrorApiVista error={plan.error} prefijo="No se pudo leer tu plan:" reintentar={plan.recargar} />
          ) : !catalogo.datos || !plan.datos ? (
            <CargandoLento
              texto="Cargando tu plan…"
              lento="Calculando las estrategias con los datos descargados… la primera vez tarda unos segundos."
            />
          ) : (
            <TuPlan
              key={r.entrada}
              estrategias={catalogo.datos.estrategias}
              inicial={{ ...borradorDe(catalogo.datos.estrategias, partesParaPlan), dia: planActual?.dia_del_mes ?? 1 }}
              planActual={planActual}
              onBorrado={() => {
                cambiar({ paso: 0, alcanzado: 0, precarga: null, entrada: Date.now() });
              }}
            />
          )
        ) : null}
      </Asistente>
    </div>
  );
}
