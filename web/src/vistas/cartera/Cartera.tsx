"use client";

import { useState, type FormEvent } from "react";

import { api, pedir } from "@/api/cliente";
import type { NuevoMovimiento } from "@/api/tipos";
import { EnviarOrden } from "@/componentes/EnviarOrden";
import { MarcoTabla, Td, Th } from "@/componentes/tabla";
import {
  Aviso,
  Boton,
  CampoTexto,
  Cargando,
  Codigo,
  Desplegable,
  ErrorApiVista,
  FilaMetricas,
  Metrica,
  Nota,
  Seccion,
  Selector,
  Separador,
  TextoApi,
  TextoPlano,
} from "@/componentes/ui";
import { useEstado } from "@/contexto/estado";
import { useAccion, useConsulta } from "@/lib/consulta";
import { formatoCantidad, formatoImporte } from "@/lib/decimal";
import { fecha, hoyLocal, momento } from "@/lib/formato";

type TipoMovimiento = NuevoMovimiento["tipo"];

/**
 * Registrar es contabilidad: escribe en el ledger lo que ya hiciste. NO envia ninguna orden, y el
 * formulario lo dice en su titulo.
 */
function RegistrarMovimiento({ alRegistrar }: { alRegistrar: () => void }) {
  const [tipo, setTipo] = useState<TipoMovimiento>("compra");
  const [simbolo, setSimbolo] = useState("");
  const [dia, setDia] = useState(hoyLocal);
  const [cantidad, setCantidad] = useState("");
  const [precio, setPrecio] = useState("");
  const [comision, setComision] = useState("0");
  const conActivo = tipo === "compra" || tipo === "venta";

  const registrar = useAccion(async (movimiento: NuevoMovimiento) => {
    const r = await pedir(api.POST("/api/cartera/movimientos", { body: movimiento }));
    setSimbolo("");
    setCantidad("");
    setPrecio("");
    setComision("0");
    alRegistrar();
    return r;
  });

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    void registrar.ejecutar({
      tipo,
      fecha: dia,
      cantidad: cantidad.trim(),
      comision: comision.trim() || "0",
      ...(conActivo ? { simbolo: simbolo.trim().toUpperCase(), precio: precio.trim() } : {}),
    });
  };

  return (
    <Desplegable resumen="Registrar un movimiento (escribe en el ledger; NO envía órdenes)">
      <form onSubmit={enviar} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Selector etiqueta="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoMovimiento)}>
            <option value="compra">compra</option>
            <option value="venta">venta</option>
            <option value="deposito">depósito</option>
            <option value="retirada">retirada</option>
          </Selector>
          <CampoTexto
            etiqueta="Activo (solo compra/venta)"
            placeholder="GLD"
            value={conActivo ? simbolo : ""}
            onChange={(e) => setSimbolo(e.target.value)}
            disabled={!conActivo}
            required={conActivo}
          />
          <CampoTexto etiqueta="Fecha" type="date" value={dia} onChange={(e) => setDia(e.target.value)} required />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <CampoTexto
            etiqueta={conActivo ? "Cantidad" : "Importe"}
            ayuda={conActivo ? "Unidades del activo" : "Efectivo que entra o sale"}
            value={cantidad}
            onChange={(e) => setCantidad(e.target.value)}
            inputMode="decimal"
            required
          />
          <CampoTexto
            etiqueta="Precio unitario"
            placeholder="240.50"
            value={conActivo ? precio : ""}
            onChange={(e) => setPrecio(e.target.value)}
            inputMode="decimal"
            disabled={!conActivo}
            required={conActivo}
          />
          <CampoTexto
            etiqueta="Comisión"
            value={comision}
            onChange={(e) => setComision(e.target.value)}
            inputMode="decimal"
          />
        </div>
        <Nota>Usa punto decimal (240.50). Los importes viajan como texto, sin redondeos de coma flotante.</Nota>
        <Boton type="submit" variante="primario" disabled={registrar.enCurso}>
          {registrar.enCurso ? "Registrando…" : "Registrar en el ledger"}
        </Boton>
        {registrar.error ? <ErrorApiVista error={registrar.error} prefijo="No registrado:" /> : null}
        {registrar.resultado ? (
          <Aviso tipo="hecho" vivo>
            Registrado en el ledger (movimiento <Codigo>{registrar.resultado.activity_id}</Codigo>). Es contabilidad: NO
            se ha enviado ninguna orden.
          </Aviso>
        ) : null}
      </form>
    </Desplegable>
  );
}

function OrdenesEnviadas({ version }: { version: number }) {
  const consulta = useConsulta(`ordenes:${version}`, () => pedir(api.GET("/api/ordenes")));
  const o = consulta.datos;
  return (
    <Seccion titulo="Órdenes enviadas" id="ordenes">
      <Nota>
        Lo que de verdad salió al mercado, con el modo de cada orden a la vista. La cartera dice qué tienes; esto, qué
        mandaste.
      </Nota>
      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!o && consulta.cargando ? <Cargando /> : null}
      {o && o.total === 0 ? <Nota>Ninguna orden enviada todavía.</Nota> : null}
      {o && o.total > 0 ? (
        <>
          <MarcoTabla etiqueta="Órdenes enviadas, la más reciente primero" altoMaximo={420}>
            <thead>
              <tr>
                <Th>cuándo</Th>
                <Th>modo</Th>
                <Th>activo</Th>
                <Th>lado</Th>
                <Th numerica>pedida</Th>
                <Th numerica>ejecutada</Th>
                <Th numerica>precio</Th>
                <Th numerica>comisión</Th>
                <Th>estado</Th>
                <Th>referencia</Th>
              </tr>
            </thead>
            <tbody>
              {o.filas.map((f, i) => (
                <tr key={`${f.cuando}-${i}`}>
                  <Td>{momento(f.cuando, true)}</Td>
                  <Td className={f.modo.toUpperCase() === "REAL" ? "font-bold" : undefined}>{f.modo}</Td>
                  <Td className="font-medium">{f.activo}</Td>
                  <Td>{f.lado}</Td>
                  <Td numerica>{formatoCantidad(f.pedida)}</Td>
                  <Td numerica>{formatoCantidad(f.ejecutada)}</Td>
                  <Td numerica>{f.precio === null ? "—" : formatoImporte(f.precio, { decimales: 2 })}</Td>
                  <Td numerica>{formatoCantidad(f.comision)}</Td>
                  <Td>{f.estado}</Td>
                  <Td className="font-mono text-xs text-tinta-2">{f.referencia || "—"}</Td>
                </tr>
              ))}
            </tbody>
          </MarcoTabla>
          <Nota>
            {o.total} orden(es) · <strong className="text-tinta">{o.reales} con dinero real</strong> · registro en{" "}
            <Codigo>{o.registro}</Codigo>
          </Nota>
          {o.atencion.map((a) => (
            <Aviso key={a} tipo="aviso">
              <TextoApi texto={a} />
            </Aviso>
          ))}
          {o.sin_comision ? (
            <Nota>
              {o.sin_comision} sin comisión registrada: no pasan a la cartera, porque anotarlas con comisión cero las haría
              parecer más rentables de lo que fueron.
            </Nota>
          ) : null}
        </>
      ) : null}
    </Seccion>
  );
}

/** La cartera real, derivada del ledger. Valoracion (con su fecha) y hecho, separados. */
export function Cartera() {
  const [version, setVersion] = useState(0);
  const recargar = () => setVersion((v) => v + 1);
  const { versionDatos } = useEstado();
  const consulta = useConsulta(`cartera:${version}:${versionDatos}`, () => pedir(api.GET("/api/cartera")));
  const c = consulta.datos;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-tinta">Mi cartera</h1>
      <RegistrarMovimiento alRegistrar={recargar} />

      {consulta.error ? <ErrorApiVista error={consulta.error} /> : null}
      {!c && consulta.cargando ? <Cargando texto="Leyendo el ledger…" /> : null}

      {c?.error ? (
        <Aviso tipo="critico">
          <strong>El ledger cuenta una historia imposible:</strong> <TextoApi texto={c.error} />
        </Aviso>
      ) : null}

      {c && !c.error && c.vacia ? (
        <Aviso tipo="info">
          <p>La cartera está vacía: no hay ningún movimiento registrado.</p>
          <p className="mt-1">Registra una compra arriba, o importa el CSV de tu broker:</p>
          <TextoPlano className="mt-2">
            {"uv run invest-ll-portfolio add buy --symbol GLD --quantity 10 --price 240.5 --fee 2\nuv run invest-ll-portfolio import movimientos.csv"}
          </TextoPlano>
        </Aviso>
      ) : null}

      {c && !c.error && !c.vacia ? (
        <div className={consulta.cargando ? "space-y-6 opacity-60" : "space-y-6"}>
          {c.avisos.map((a) => (
            <Aviso key={a} tipo="aviso">
              <TextoApi texto={a} />
            </Aviso>
          ))}

          {c.abiertas.length ? (
            <Seccion titulo="Posiciones abiertas" id="abiertas">
              <Nota>
                Su P&amp;L es una <strong className="text-tinta">valoración con la fecha de los datos al lado</strong>, no
                un hecho: cambia con cada cierre.
              </Nota>
              <MarcoTabla etiqueta="Posiciones abiertas">
                <thead>
                  <tr>
                    <Th>activo</Th>
                    <Th numerica>cantidad</Th>
                    <Th numerica>coste medio</Th>
                    <Th numerica>invertido</Th>
                    <Th>abierta</Th>
                    <Th numerica>precio</Th>
                    <Th numerica>valor</Th>
                    <Th numerica>P&amp;L no realizado</Th>
                    <Th>datos de</Th>
                  </tr>
                </thead>
                <tbody>
                  {c.abiertas.map((p) => (
                    <tr key={p.activo}>
                      <Td className="font-medium">{p.activo}</Td>
                      <Td numerica>{formatoCantidad(p.cantidad)}</Td>
                      <Td numerica>{formatoImporte(p.coste_medio)}</Td>
                      <Td numerica>{formatoImporte(p.invertido)}</Td>
                      <Td>{fecha(p.abierta)}</Td>
                      <Td numerica>{formatoImporte(p.precio)}</Td>
                      <Td numerica>{formatoImporte(p.valor)}</Td>
                      <Td numerica>{formatoImporte(p.pnl_no_realizado, { conSigno: true })}</Td>
                      <Td className={p.precio_fecha ? "font-medium" : "font-semibold text-critico-tinta"}>
                        {p.precio_fecha ? fecha(p.precio_fecha) : "sin datos"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </MarcoTabla>
            </Seccion>
          ) : null}

          <FilaMetricas columnas={3}>
            <Metrica etiqueta="Invertido en abiertas" valor={formatoImporte(c.invertido_abiertas)} />
            <Metrica
              etiqueta="Valor con últimos datos"
              valor={c.valor_total === null ? "incompleto" : formatoImporte(c.valor_total)}
              detalle={
                c.valor_total === null
                  ? "Falta el precio de alguna posición abierta: no se suma lo que no se sabe."
                  : "Valoración: cada posición con la fecha de su último cierre."
              }
            />
            <Metrica etiqueta="Efectivo derivado" valor={formatoImporte(c.efectivo)} />
          </FilaMetricas>

          {c.retiradas.length ? (
            <Seccion titulo="Posiciones retiradas" id="retiradas">
              <Nota>
                Su P&amp;L es <strong className="text-tinta">realizado</strong>: un hecho que ya no cambia.
              </Nota>
              <MarcoTabla etiqueta="Posiciones retiradas">
                <thead>
                  <tr>
                    <Th>activo</Th>
                    <Th>abierta</Th>
                    <Th>retirada</Th>
                    <Th numerica>días</Th>
                    <Th numerica>invertido</Th>
                    <Th numerica>recuperado</Th>
                    <Th numerica>P&amp;L realizado</Th>
                  </tr>
                </thead>
                <tbody>
                  {c.retiradas.map((t) => (
                    <tr key={`${t.activo}-${t.abierta}-${t.retirada}`}>
                      <Td className="font-medium">{t.activo}</Td>
                      <Td>{fecha(t.abierta)}</Td>
                      <Td>{fecha(t.retirada)}</Td>
                      <Td numerica>{t.dias}</Td>
                      <Td numerica>{formatoImporte(t.invertido)}</Td>
                      <Td numerica>{formatoImporte(t.recuperado)}</Td>
                      <Td numerica>{formatoImporte(t.pnl_realizado, { conSigno: true })}</Td>
                    </tr>
                  ))}
                </tbody>
              </MarcoTabla>
              <Nota>
                P&amp;L realizado total:{" "}
                <strong className="cifras text-tinta">{formatoImporte(c.realizado_total, { conSigno: true })}</strong>
              </Nota>
            </Seccion>
          ) : null}
        </div>
      ) : null}

      <Nota>
        Los movimientos ya hechos se registran arriba o con <Codigo>invest-ll-portfolio</Codigo> (add / cash / import).
        Para enviar una orden al mercado, abajo o <Codigo>invest-ll-execute</Codigo>: las dos piden confirmarla.
      </Nota>

      <Separador />
      <EnviarOrden alEnviar={recargar} />
      <Separador />
      <OrdenesEnviadas version={version} />
    </div>
  );
}
