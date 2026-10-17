/**
 * La minigrafica de cada fila de la mesa (SVG propio). Sin ejes y en tinta neutra: en la mesa el
 * color se reserva para las celdas de variacion, y la sparkline solo dice la forma del camino.
 * Es redundante con las columnas de al lado, asi que se oculta a los lectores de pantalla y la
 * celda lleva su resumen en texto.
 */
export function Sparkline({
  valores,
  ancho = 96,
  alto = 24,
}: {
  valores: readonly number[];
  ancho?: number;
  alto?: number;
}) {
  if (valores.length < 2) return <span className="text-tinta-suave">—</span>;
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const margen = 3;
  const rango = max - min || 1;
  const x = (i: number) => margen + (i / (valores.length - 1)) * (ancho - 2 * margen);
  const y = (v: number) => margen + (1 - (v - min) / rango) * (alto - 2 * margen);
  const camino = valores.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const ultimo = valores[valores.length - 1] ?? 0;
  return (
    <svg width={ancho} height={alto} viewBox={`0 0 ${ancho} ${alto}`} aria-hidden="true" className="block">
      <path d={camino} fill="none" stroke="var(--tinta-suave)" strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
      <circle
        cx={x(valores.length - 1)}
        cy={y(ultimo)}
        r="2.25"
        fill="var(--tinta)"
        stroke="var(--superficie)"
        strokeWidth="1.5"
      />
    </svg>
  );
}
