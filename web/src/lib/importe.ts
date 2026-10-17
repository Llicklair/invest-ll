/**
 * Lo que la persona teclea como importe o cantidad, a la cadena decimal que espera la API.
 *
 * En España se escribe "1.000" (mil) y "12,50" (doce con cincuenta), y el teclado numerico del
 * movil pone una COMA como separador decimal. Reglas, sin adivinar mas de la cuenta:
 * - Se quitan espacios y el simbolo "€".
 * - Si hay coma: los puntos son de miles y la coma es la decimal ("1.234,5" -> "1234.5").
 * - Si no hay coma y los puntos agrupan de tres en tres ("1.000", "12.500.000"): son miles.
 * - Si no: el punto es el decimal ("0.00123", "12.5").
 * Devuelve `null` si no es un numero >= 0. Nunca pasa por float: es manipulacion de texto.
 */
export function leerImporte(texto: string): string | null {
  let t = texto.replace(/[\s €]/g, "");
  if (t === "") return null;
  if (t.includes(",")) {
    if ((t.match(/,/g) ?? []).length > 1) return null;
    t = t.replace(/\./g, "").replace(",", ".");
  } else if (/^\d{1,3}(\.\d{3})+$/.test(t)) {
    t = t.replace(/\./g, "");
  }
  if (!/^\d+(\.\d+)?$/.test(t) && !/^\d*\.\d+$/.test(t)) return null;
  if (t.startsWith(".")) t = `0${t}`;
  // Sin ceros a la izquierda ("007" -> "7"), conservando "0.5".
  t = t.replace(/^0+(?=\d)/, "");
  return t;
}

/**
 * Lo tecleado para confirmar una cantidad: igual que `leerImporte` pero solo cambia la coma
 * decimal por punto (aqui no hay miles: son cantidades como 0,00123). Lo que no se reconoce va
 * tal cual, y la API dira por que no coincide.
 */
export function normalizarTecleo(texto: string): string {
  const t = texto.trim();
  return /^\d*,\d+$/.test(t) ? t.replace(",", ".") : t;
}
