"use client";

import { CircleQuestionMark } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { clases } from "./ui";

/**
 * El glosario, en llano. Cuando un termino hace falta en la interfaz principal, va con su
 * explicacion al lado (docs/panel-v2.md, principio 3).
 */
export const GLOSARIO = {
  "peor-momento": {
    pregunta: "¿Qué es «el peor momento»?",
    termino: "El peor momento",
    texto:
      "Lo más que llegó a valer por debajo de su máximo anterior. Es lo que habrías visto en tu cuenta en el peor día: si entonces vendes, la pérdida se hace real.",
  },
  liquidez: {
    pregunta: "¿Qué es la liquidez?",
    termino: "Liquidez",
    texto:
      "Dinero que no está invertido: se queda en dólares digitales (USDT) o en efectivo esperando. No sube ni baja con el mercado.",
  },
  etf: {
    pregunta: "¿Qué es un fondo cotizado (ETF)?",
    termino: "Fondo cotizado (ETF)",
    texto:
      "Una cesta de muchas empresas o bonos que se compra de una vez, como si fuera una sola acción. Por ejemplo, uno del S&P 500 lleva dentro las 500 mayores empresas de EE.UU.",
  },
  ucits: {
    pregunta: "¿Qué es UCITS?",
    termino: "UCITS",
    texto:
      "La versión europea de un fondo, la que se puede comprar desde España. Se comporta casi igual que el fondo de EE.UU. que usamos para las cifras.",
  },
  broker: {
    pregunta: "¿Qué es «tu bróker»?",
    termino: "Tu bróker",
    texto:
      "La aplicación o el banco donde compras fondos y acciones (por ejemplo, el de tu banco, MyInvestor o Trade Republic). Este panel no se conecta a él: te dice qué comprar y tú lo compras.",
  },
  binance: {
    pregunta: "¿Qué es Binance?",
    termino: "Binance",
    texto:
      "Una plataforma para comprar criptomonedas. Este panel sí puede mandarle órdenes, pero solo con las claves que tú le des y confirmando tú cada una.",
  },
  pruebas: {
    pregunta: "¿Qué es el modo pruebas?",
    termino: "Modo pruebas",
    texto:
      "Binance tiene una red de pruebas con dinero ficticio. Las órdenes salen de verdad, pero nada de lo que pase cuesta dinero: sirve para aprender sin pagar.",
  },
  usdt: {
    pregunta: "¿Qué es USDT?",
    termino: "USDT (dólares digitales)",
    texto: "Una criptomoneda que vale siempre lo mismo que un dólar. Las estrategias de cripto la usan como «liquidez».",
  },
  "prueba-pasado": {
    pregunta: "¿Qué quiere decir «probada sobre el pasado»?",
    termino: "Probada sobre el pasado",
    texto:
      "Se ha calculado qué habría pasado si se hubiera seguido la estrategia con los precios de años anteriores. Dice cómo se comportó, no cómo se comportará.",
  },
  "prueba-real": {
    pregunta: "¿Qué quiere decir «en prueba real»?",
    termino: "En prueba real",
    texto:
      "Desde esa fecha se apunta cada día lo que haría la estrategia, sin tocar nada después. Es la única prueba que no puede estar hecha a medida del pasado.",
  },
  aportacion: {
    pregunta: "¿Qué es una aportación?",
    termino: "Aportación",
    texto: "El dinero que añades cada mes. Aportar poco a poco hace que la fecha en la que empiezas importe menos.",
  },
  comisiones: {
    pregunta: "¿Qué comisiones se cuentan?",
    termino: "Comisiones y costes",
    texto:
      "Lo que te cobra la plataforma por cada compra o venta, más lo que se pierde entre el precio que ves y el que te dan. Todas las cifras de este panel ya los descuentan.",
  },
  // -- Panel v3 (Operar y Bots) --
  usdc: {
    pregunta: "¿Qué es USDC?",
    termino: "USDC (dólares digitales)",
    texto: "Una criptomoneda que vale siempre lo mismo que un dólar. Aquí es la moneda con la que compras y vendes, y es ficticia: no es dinero tuyo.",
  },
  vela: {
    pregunta: "¿Cómo se leen las velas?",
    termino: "Velas",
    texto:
      "Cada vela es un trozo de tiempo (un minuto, una hora, un día). El cuerpo va del precio con que empezó al precio con que acabó; las líneas finas, hasta el más alto y el más bajo. Hueca: acabó más arriba de donde empezó. Rellena: acabó más abajo. La última se sigue moviendo hasta que su tiempo termina.",
  },
  libro: {
    pregunta: "¿Qué es el libro de órdenes?",
    termino: "Libro de órdenes",
    texto:
      "Las órdenes que esperan a que alguien las acepte. Arriba, quien quiere vender y a qué precio; abajo, quien quiere comprar. «Acumulado» suma la cantidad desde el centro hacia fuera: es lo que te comerías si compraras o vendieras tanto de golpe.",
  },
  diferencial: {
    pregunta: "¿Qué es la diferencia entre compra y venta?",
    termino: "Diferencia (diferencial)",
    texto:
      "Lo que separa la venta más barata de la compra más cara. Si compras y vendes al momento, pierdes más o menos eso, además de la comisión.",
  },
  "tipo-orden": {
    pregunta: "¿A mercado o con límite?",
    termino: "A mercado o con límite",
    texto:
      "A mercado compras (o vendes) ya, al mejor precio que haya en el libro; si pides mucho, pagas también los precios siguientes. Con límite dices el precio que estás dispuesto a pagar (o a cobrar) y la orden espera hasta que el mercado llegue a él; quizá no llegue nunca. Con límite la comisión es más baja.",
  },
  mantener: {
    pregunta: "¿Qué es «si solo hubieras mantenido»?",
    termino: "Si solo hubieras mantenido",
    texto:
      "Lo que habría pasado con el mismo dinero, desde el mismo momento, comprando sus monedas al arrancar y sin hacer nada más. Si el bot gana menos que eso, sus operaciones no han servido (todavía).",
  },
} as const satisfies Record<string, { pregunta: string; termino: string; texto: string }>;

export type ClaveGlosario = keyof typeof GLOSARIO;

/** "¿Qué es esto?": un boton pequeno que despliega la explicacion debajo, sin salir de la pagina. */
export function QueEsEsto({
  clave,
  children,
  className,
  etiqueta = "¿Qué es esto?",
}: {
  clave?: ClaveGlosario;
  /** Explicacion propia si no esta en el glosario. */
  children?: ReactNode;
  className?: string;
  etiqueta?: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const id = useId();
  const entrada = clave ? GLOSARIO[clave] : null;
  return (
    <span className={clases("inline", className)}>
      <button
        type="button"
        aria-expanded={abierto}
        aria-controls={id}
        onClick={() => setAbierto((a) => !a)}
        className="inline-flex min-h-11 items-center gap-1 align-middle text-sm font-medium text-marca underline-offset-4 hover:underline"
      >
        <CircleQuestionMark aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
        {entrada && etiqueta === "¿Qué es esto?" ? entrada.pregunta : etiqueta}
      </button>
      {abierto ? (
        <span id={id} className="mt-1 mb-2 block rounded-xl bg-marca-suave px-4 py-3 text-[0.9375rem] leading-relaxed text-tinta">
          {entrada ? <strong className="font-semibold">{entrada.termino}. </strong> : null}
          {entrada?.texto}
          {children}
        </span>
      ) : null}
    </span>
  );
}
