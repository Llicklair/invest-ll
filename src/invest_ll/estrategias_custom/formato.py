"""El formato de las estrategias a medida (docs/panel-v4-real.md §2): un JSON cerrado que el motor
INTERPRETA.

**Una estrategia no es código.** Es un objeto JSON con campos fijos que se valida con pydantic
antes de guardarlo y antes de usarlo: monedas, intervalo de las velas, indicadores con nombre
(`sma`, `ema`, `rsi`, `retorno`, `maximo`, `minimo`, `volatilidad`, `atr`, `volumen_medio`), las
condiciones de `entrar` y `salir` como árbol (`y`, `o`, `no`, `>`, `<`, `>=`, `<=`,
`cruza_arriba`, `cruza_abajo`), el `tamano` y el `riesgo`. Cada lado de una comparación es un
número, `"precio"`, el nombre de un indicador o `{"valor": nombre, "por": factor}`. No hay
expresiones libres en texto, ni nombres de funciones, ni plantillas: lo que no encaja en esto se
rechaza con un error en llano, y el intérprete solo sabe evaluar estas piezas. Una estrategia mal
pensada puede perder dinero dentro de sus límites, pero no puede hacer nada fuera de su formato.

Los límites (periodos, número de reglas, profundidad del árbol) están para que una estrategia se
pueda leer y para que validarla e interpretarla sea siempre barato.

`reglas_en_llano` convierte cada regla en una frase ("Compra cuando la media de 20 velas cruza por
encima de la de 50"), que es lo que enseña la ficha y lo que lee Marcos antes de desplegar nada.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Final, Literal, cast

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    StringConstraints,
    Tag,
    ValidationError,
    model_validator,
)

from invest_ll import llano
from invest_ll.errors import InvestLLError
from invest_ll.nombres import nombre_hyperliquid

FORMATO: Final = 1
"""La versión del formato. Si cambia, las estrategias guardadas se migran: nunca se reinterpretan."""

INTERVALOS: Final = ("15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w")
"""Los que tienen Binance e Hyperliquid. Sin velas de 1-5 minutos: las comisiones se lo comen todo."""
DURACION: Final[dict[str, timedelta]] = {
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
}
INTERVALO_TXT: Final[dict[str, str]] = {
    "15m": "15 minutos",
    "30m": "30 minutos",
    "1h": "1 hora",
    "2h": "2 horas",
    "4h": "4 horas",
    "8h": "8 horas",
    "12h": "12 horas",
    "1d": "1 día",
    "3d": "3 días",
    "1w": "1 semana",
}

TIPOS: Final = (
    "sma",
    "ema",
    "rsi",
    "retorno",
    "maximo",
    "minimo",
    "volatilidad",
    "atr",
    "volumen_medio",
)
FUENTES: Final = ("cierre", "apertura", "maximo", "minimo", "volumen")
PRECIO: Final = "precio"
"""El cierre de la última vela cerrada."""
COMPARACIONES: Final = (">", "<", ">=", "<=")
CRUCES: Final = ("cruza_arriba", "cruza_abajo")
GRUPOS: Final = ("y", "o", "no")
CLAVES: Final = GRUPOS + COMPARACIONES + CRUCES

MAX_MONEDAS: Final = 5
MAX_INDICADORES: Final = 12
MAX_PERIODO: Final = 400
MAX_ATRAS: Final = 50
MAX_RAMAS: Final = 8
"""Condiciones dentro de un mismo `y` u `o`."""
MAX_COMPARACIONES: Final = 12
"""Comparaciones y cruces en `entrar` (y otras tantas en `salir`)."""
MAX_PROFUNDIDAD: Final = 4
"""Grupos (`y`, `o`, `no`) metidos unos dentro de otros."""
MAX_NODOS: Final = 1500
MAX_ANIDADO: Final = 24
"""Antes de validar nada: un JSON enorme o muy anidado se rechaza sin recorrerlo con pydantic."""
MAX_NUMERO: Final = 1e12

_NOMBRE_PATRON: Final = r"^[a-z][a-z0-9_]{0,23}$"
_NOMBRE: Final = re.compile(_NOMBRE_PATRON)
_REF_PATRON: Final = r"^(precio|[a-z][a-z0-9_]{0,23})$"
_MONEDA: Final = re.compile(r"^[A-Za-z0-9]{1,20}$")
_CONTROL: Final = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

TipoIndicador = Literal[
    "sma", "ema", "rsi", "retorno", "maximo", "minimo", "volatilidad", "atr", "volumen_medio"
]
Fuente = Literal["cierre", "apertura", "maximo", "minimo", "volumen"]
Intervalo = Literal["15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w"]
Reparto = Literal["igual", "volatilidad"]


class EstrategiaInvalidaError(InvestLLError):
    """La estrategia no cumple el formato. `errores` son frases en llano, una por problema."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("La estrategia no vale: " + "; ".join(errores) + ".")


def _corto(texto: object, largo: int = 40) -> str:
    """Un trozo de lo recibido para citarlo en un error, sin inundar la pantalla."""
    t = _CONTROL.sub("", str(texto))
    return t if len(t) <= largo else t[: largo - 1] + "…"


# -- Lo que se valida antes de que entre pydantic ------------------------------------------------


def _numero(valor: object, que: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        raise ValueError(f"{que} tiene que ser un número")
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError(f"{que} tiene que ser un número normal (ni infinito ni NaN)")
    if abs(numero) > MAX_NUMERO:
        raise ValueError(f"{que} es un número demasiado grande")
    return numero


def _referencia_valida(texto: str) -> bool:
    return texto == PRECIO or bool(_NOMBRE.match(texto))


def _operando(valor: object) -> object:
    """Un lado de una comparación, ya comprobado. Lo que no es una de las cuatro formas, fuera."""
    if isinstance(valor, bool):
        raise ValueError(
            "un sí/no (true/false) no se puede comparar: usa un número, «precio» o el nombre de un "
            "indicador"
        )
    if isinstance(valor, int | float):
        return _numero(valor, "cada número de una comparación")
    if isinstance(valor, str):
        if _referencia_valida(valor):
            return valor
        raise ValueError(
            f"«{_corto(valor)}» no es un número, ni «precio», ni el nombre de un indicador "
            "(minúsculas, cifras y _). Las estrategias no admiten expresiones ni código: se "
            "escriben solo con estas piezas"
        )
    if isinstance(valor, dict):
        datos = cast("dict[object, object]", valor)
        claves = set(datos)
        if "valor" not in claves or not claves <= {"valor", "por"}:
            raise ValueError(
                'una referencia con multiplicador se escribe {"valor": "sma50", "por": 0.95}, '
                "sin más claves"
            )
        ref = datos["valor"]
        if not isinstance(ref, str) or not _referencia_valida(ref):
            raise ValueError(
                f"«{_corto(ref)}» no es «precio» ni el nombre de un indicador (minúsculas, cifras "
                "y _)"
            )
        por = _numero(datos.get("por", 1), "«por»")
        if not 0.01 <= por <= 100:
            raise ValueError("«por» multiplica el valor: tiene que estar entre 0,01 y 100")
        return Referencia.model_construct(valor=ref, por=por)
    raise ValueError(
        'cada lado de una comparación es un número, «precio», el nombre de un indicador o {"valor": '
        '"sma50", "por": 0.95}'
    )


def _forma(valor: object) -> object:
    """Que una condición sea un objeto con UNA clave conocida y lo que esa clave lleva dentro."""
    ejemplo = 'p. ej. {">": ["rsi14", 70]} o {"y": [ … ]}'
    if not isinstance(valor, dict):
        raise ValueError(f"cada condición es un objeto con una sola clave ({ejemplo})")
    datos = cast("dict[object, object]", valor)
    if len(datos) != 1:
        claves = ", ".join(f"«{_corto(k, 20)}»" for k in list(datos)[:4])
        raise ValueError(
            f"cada condición lleva UNA sola clave (y, o, no, >, <, >=, <=, cruza_arriba o "
            f"cruza_abajo) y esta lleva {len(datos)}: {claves or 'ninguna'}"
        )
    clave, dentro = next(iter(datos.items()))
    if clave not in CLAVES:
        raise ValueError(
            f"«{_corto(clave)}» no es una condición. Las que hay: y, o, no, >, <, >=, <=, "
            "cruza_arriba y cruza_abajo"
        )
    if clave in ("y", "o"):
        if not isinstance(dentro, list) or not dentro:
            raise ValueError(f'«{clave}» lleva una lista de condiciones: {{"{clave}": [ … , … ]}}')
        if len(cast("list[object]", dentro)) > MAX_RAMAS:
            raise ValueError(f"«{clave}» admite como mucho {MAX_RAMAS} condiciones")
    elif clave == "no":
        if not isinstance(dentro, dict):
            raise ValueError('«no» lleva UNA condición: {"no": { … }}')
    elif not isinstance(dentro, list) or len(cast("list[object]", dentro)) != 2:
        raise ValueError(f'«{clave}» compara dos cosas: {{"{clave}": ["sma20", "sma50"]}}')
    return datos


def _clave(valor: object) -> str | None:
    """El discriminador del árbol: la única clave del objeto (o la del nodo ya construido)."""
    if isinstance(valor, dict):
        datos = cast("dict[object, object]", valor)
        clave = next(iter(datos), None)
        return clave if isinstance(clave, str) and clave in CLAVES else None
    if isinstance(valor, _Nodo):
        return valor.CLAVE
    return None


def _moneda(valor: object) -> object:
    if not isinstance(valor, str):
        return valor
    coin = valor.strip()
    if coin.islower():
        coin = coin.upper()
    if not _MONEDA.match(coin):
        raise ValueError(f"«{_corto(valor)}» no parece el nombre de una moneda (BTC, ETH, SOL…)")
    return coin


def _texto(valor: object) -> object:
    if isinstance(valor, str):
        limpio = valor.strip()
        if _CONTROL.search(limpio):
            raise ValueError("lleva caracteres de control: escribe solo texto normal")
        return limpio
    return valor


# -- Las piezas ----------------------------------------------------------------------------------


class _Cerrado(BaseModel):
    """Nada de claves de más: lo que no está en el formato no se acepta, tampoco "por si acaso"."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Indicador(_Cerrado):
    """Un indicador con nombre, calculado sobre las velas CERRADAS de cada moneda."""

    tipo: TipoIndicador = Field(
        description=(
            "sma: media; ema: media exponencial; rsi: RSI de Wilder (0-100); retorno: cambio en "
            "`periodo` velas, en fracción (0.05 = +5 %); maximo / minimo: el más alto / más bajo de "
            "`periodo` velas; volatilidad: desviación típica del cambio de cada vela, en fracción; "
            "atr: rango medio de cada vela (máximo - mínimo, contando el hueco con el cierre "
            "anterior), en precio; volumen_medio: media del volumen."
        )
    )
    periodo: int = Field(ge=1, le=MAX_PERIODO, description="Cuántas velas mira")
    fuente: Fuente | None = Field(
        default=None,
        description=(
            "Sobre qué dato de la vela: cierre (por defecto), apertura, maximo, minimo o volumen. "
            "Por defecto, maximo usa los máximos y minimo los mínimos. atr y volumen_medio no "
            "llevan fuente."
        ),
    )
    atras: int = Field(
        default=0,
        ge=0,
        le=MAX_ATRAS,
        description=(
            "0: con la última vela cerrada. 1: como estaba una vela antes (p. ej. el máximo de las "
            "20 velas ANTERIORES, para comprar cuando el precio lo supera)."
        ),
    )

    @model_validator(mode="after")
    def _coherente(self) -> Indicador:
        if self.tipo in ("ema", "rsi", "volatilidad") and self.periodo < 2:
            raise ValueError(f"«{self.tipo}» necesita un periodo de 2 velas o más")
        if self.tipo == "atr" and self.fuente is not None:
            raise ValueError("«atr» no lleva «fuente»: usa el máximo, el mínimo y el cierre")
        if self.tipo == "volumen_medio" and self.fuente is not None:
            raise ValueError("«volumen_medio» no lleva «fuente»: siempre es el volumen")
        return self

    @property
    def de(self) -> Fuente:
        """El dato de la vela con que se calcula."""
        if self.fuente is not None:
            return self.fuente
        if self.tipo == "maximo":
            return "maximo"
        if self.tipo == "minimo":
            return "minimo"
        if self.tipo == "volumen_medio":
            return "volumen"
        return "cierre"

    @property
    def ventana(self) -> int:
        """Cuántas velas cerradas necesita para dar su valor (sin contar `atras`).

        La media exponencial y el RSI se calculan SIEMPRE sobre esta ventana fija (3 veces el
        periodo), arrancando de la media simple: así el valor no depende de cuánta historia dé la
        fuente, y el motor en vivo y la prueba sobre el pasado dan exactamente lo mismo.
        """
        if self.tipo == "ema":
            return 3 * self.periodo
        if self.tipo == "rsi":
            return 3 * self.periodo + 1
        if self.tipo in ("retorno", "volatilidad", "atr"):
            return self.periodo + 1
        return self.periodo


class Referencia(_Cerrado):
    """Un indicador (o el precio) multiplicado por un factor: "un 5 % por encima del mínimo"."""

    valor: Annotated[str, StringConstraints(pattern=_REF_PATRON)] = Field(
        description="«precio» o el nombre de un indicador"
    )
    por: float = Field(default=1.0, ge=0.01, le=100, description="0.95 = un 5 % por debajo")


Operando = Annotated[
    float | Annotated[str, StringConstraints(pattern=_REF_PATRON)] | Referencia,
    BeforeValidator(_operando),
]
"""Un número, «precio», el nombre de un indicador o {"valor": nombre, "por": factor}."""


class _Nodo(_Cerrado):
    CLAVE: ClassVar[str]


class Todas(_Nodo):
    """Se cumplen todas."""

    CLAVE: ClassVar[str] = "y"
    y: list[Condicion] = Field(min_length=1, max_length=MAX_RAMAS)


class Alguna(_Nodo):
    """Se cumple al menos una."""

    CLAVE: ClassVar[str] = "o"
    o: list[Condicion] = Field(min_length=1, max_length=MAX_RAMAS)


class Negacion(_Nodo):
    """No se cumple."""

    CLAVE: ClassVar[str] = "no"
    no: Condicion


class Mayor(_Nodo):
    CLAVE: ClassVar[str] = ">"
    mayor: tuple[Operando, Operando] = Field(alias=">")

    @property
    def par(self) -> tuple[Operando, Operando]:
        return self.mayor


class Menor(_Nodo):
    CLAVE: ClassVar[str] = "<"
    menor: tuple[Operando, Operando] = Field(alias="<")

    @property
    def par(self) -> tuple[Operando, Operando]:
        return self.menor


class MayorIgual(_Nodo):
    CLAVE: ClassVar[str] = ">="
    mayor_igual: tuple[Operando, Operando] = Field(alias=">=")

    @property
    def par(self) -> tuple[Operando, Operando]:
        return self.mayor_igual


class MenorIgual(_Nodo):
    CLAVE: ClassVar[str] = "<="
    menor_igual: tuple[Operando, Operando] = Field(alias="<=")

    @property
    def par(self) -> tuple[Operando, Operando]:
        return self.menor_igual


class CruzaArriba(_Nodo):
    """El primero estaba en o por debajo del segundo en la vela anterior y ahora está por encima."""

    CLAVE: ClassVar[str] = "cruza_arriba"
    cruza_arriba: tuple[Operando, Operando]

    @property
    def par(self) -> tuple[Operando, Operando]:
        return self.cruza_arriba


class CruzaAbajo(_Nodo):
    """El primero estaba en o por encima del segundo en la vela anterior y ahora está por debajo."""

    CLAVE: ClassVar[str] = "cruza_abajo"
    cruza_abajo: tuple[Operando, Operando]

    @property
    def par(self) -> tuple[Operando, Operando]:
        return self.cruza_abajo


Binaria = Mayor | Menor | MayorIgual | MenorIgual | CruzaArriba | CruzaAbajo
Nodo = Todas | Alguna | Negacion | Binaria

Condicion = Annotated[
    Annotated[Todas, Tag("y")]
    | Annotated[Alguna, Tag("o")]
    | Annotated[Negacion, Tag("no")]
    | Annotated[Mayor, Tag(">")]
    | Annotated[Menor, Tag("<")]
    | Annotated[MayorIgual, Tag(">=")]
    | Annotated[MenorIgual, Tag("<=")]
    | Annotated[CruzaArriba, Tag("cruza_arriba")]
    | Annotated[CruzaAbajo, Tag("cruza_abajo")],
    Discriminator(_clave),
    BeforeValidator(_forma),
]
"""Una condición: un objeto con UNA clave (y, o, no, >, <, >=, <=, cruza_arriba, cruza_abajo)."""

for _modelo in (Todas, Alguna, Negacion):
    _modelo.model_rebuild()


class Tamano(_Cerrado):
    """Cuánto compra cada vez."""

    fraccion: float = Field(
        default=1.0,
        gt=0,
        le=1,
        description="Fracción del valor del bot que invierte con todas sus monedas dentro",
    )
    reparto: Reparto = Field(
        default="igual",
        description=(
            "igual: cada moneda tiene la misma parte; volatilidad: más a la que menos se mueve "
            "(en proporción inversa a su volatilidad)"
        ),
    )
    maximo_por_moneda: float = Field(
        default=1.0, gt=0, le=1, description="Fracción máxima del valor del bot en una moneda"
    )
    periodo_volatilidad: int = Field(
        default=20,
        ge=2,
        le=MAX_PERIODO,
        description="Velas con que se mide la volatilidad para repartir (solo con reparto volatilidad)",
    )


class Riesgo(_Cerrado):
    """Las salidas por precio, en fracción. Se miran con el cierre de cada vela cerrada."""

    stop_perdida: float | None = Field(
        default=None, gt=0, lt=1, description="0.08: vende si cae un 8 % desde el precio de compra"
    )
    toma_beneficio: float | None = Field(
        default=None,
        gt=0,
        le=10,
        description="0.2: vende si sube un 20 % desde el precio de compra",
    )
    stop_seguimiento: float | None = Field(
        default=None,
        gt=0,
        lt=1,
        description="0.1: vende si cae un 10 % desde el cierre más alto desde que compró",
    )
    pausa_tras_stop: int = Field(
        default=0,
        ge=0,
        le=MAX_PERIODO,
        description="Velas que espera tras salir por un stop antes de poder volver a comprar",
    )


Moneda = Annotated[str, BeforeValidator(_moneda), StringConstraints(pattern=r"^[A-Za-z0-9]{1,20}$")]
NombreIndicador = Annotated[str, StringConstraints(pattern=_NOMBRE_PATRON)]
Texto = Annotated[str, BeforeValidator(_texto)]


class Estrategia(_Cerrado):
    """Una estrategia a medida. Compra cada moneda cuando se cumple `entrar` y la vende cuando se
    cumple `salir` o salta un stop de `riesgo`. Una posición por moneda: todo o nada."""

    formato: Literal[1] = Field(default=1, description="Versión del formato (hoy, 1)")
    nombre: Texto = Field(min_length=1, max_length=80, description="Corto y claro")
    explicacion: Texto = Field(
        min_length=1,
        max_length=2000,
        description="En llano, para la ficha: qué hace, por qué podría funcionar y sus pegas",
    )
    monedas: tuple[Moneda, ...] = Field(
        min_length=1, max_length=MAX_MONEDAS, description="BTC, ETH, SOL…"
    )
    intervalo: Intervalo = Field(description="Velas con que decide; decide al cierre de cada una")
    indicadores: dict[NombreIndicador, Indicador] = Field(
        default_factory=dict[str, Indicador],
        max_length=MAX_INDICADORES,
        description="Por nombre (minúsculas, cifras y _): sma20, rsi14, maximo_20…",
    )
    entrar: Condicion = Field(description="Cuándo compra una moneda que no tiene")
    salir: Condicion | None = Field(
        default=None, description="Cuándo vende una moneda que tiene (además de los stops)"
    )
    tamano: Tamano = Field(default_factory=Tamano)
    riesgo: Riesgo = Field(default_factory=Riesgo)

    @model_validator(mode="after")
    def _coherente(self) -> Estrategia:
        problemas: list[str] = []
        if len(set(self.monedas)) != len(self.monedas):
            problemas.append("hay monedas repetidas: pon cada una una vez")
        usados: set[str] = set()
        lados: list[tuple[str, Nodo]] = [("entrar", self.entrar)]
        if self.salir is not None:
            lados.append(("salir", self.salir))
        for lado, raiz in lados:
            hojas = list(binarias(raiz))
            if len(hojas) > MAX_COMPARACIONES:
                problemas.append(
                    f"«{lado}» tiene {len(hojas)} comparaciones y el máximo es {MAX_COMPARACIONES}: "
                    "simplifícala"
                )
            if profundidad(raiz) > MAX_PROFUNDIDAD:
                problemas.append(
                    f"«{lado}» mete grupos (y, o, no) en más de {MAX_PROFUNDIDAD} niveles: "
                    "simplifícala"
                )
            for hoja in hojas:
                a, b = hoja.par
                if isinstance(a, float) and isinstance(b, float):
                    problemas.append(
                        f"en «{lado}», «{hoja.CLAVE}» compara dos números ({_num(a)} y {_num(b)}), "
                        "que no dependen del mercado"
                    )
                for op in (a, b):
                    nombre = nombre_de(op)
                    if nombre is None or nombre == PRECIO:
                        continue
                    usados.add(nombre)
                    if nombre not in self.indicadores:
                        hay = ", ".join(sorted(self.indicadores)) or "ninguno"
                        problemas.append(
                            f"«{lado}» usa «{nombre}», que no está en «indicadores» (los que hay: "
                            f"{hay})"
                        )
        sobran = sorted(set(self.indicadores) - usados)
        if sobran:
            problemas.append(
                f"{', '.join(f'«{s}»' for s in sobran)} "
                f"{'está' if len(sobran) == 1 else 'están'} en «indicadores» pero ninguna regla "
                f"{'lo' if len(sobran) == 1 else 'los'} usa: quítalo o úsalo"
            )
        r = self.riesgo
        if self.salir is None and not (r.stop_perdida or r.toma_beneficio or r.stop_seguimiento):
            problemas.append(
                "no tiene forma de vender: pon una condición «salir» o algún stop en «riesgo»"
            )
        if problemas:
            raise ValueError("; ".join(problemas))
        return self


# -- Recorrer el árbol ---------------------------------------------------------------------------


def hijos(nodo: Nodo) -> list[Nodo]:
    if isinstance(nodo, Todas):
        return list(nodo.y)
    if isinstance(nodo, Alguna):
        return list(nodo.o)
    if isinstance(nodo, Negacion):
        return [nodo.no]
    return []


def binarias(nodo: Nodo) -> list[Binaria]:
    """Las comparaciones y cruces del árbol, de izquierda a derecha."""
    if isinstance(nodo, Todas | Alguna | Negacion):
        return [h for hijo in hijos(nodo) for h in binarias(hijo)]
    return [nodo]


def profundidad(nodo: Nodo) -> int:
    """Niveles de grupos: una comparación suelta es 0; un `y` de comparaciones, 1."""
    if isinstance(nodo, Todas | Alguna | Negacion):
        return 1 + max(profundidad(h) for h in hijos(nodo))
    return 0


def nombre_de(op: float | str | Referencia) -> str | None:
    """«precio» o el nombre del indicador al que se refiere el operando (None si es un número)."""
    if isinstance(op, Referencia):
        return op.valor
    if isinstance(op, str):
        return op
    return None


def tiene_cruce(nodo: Nodo) -> bool:
    return any(isinstance(h, CruzaArriba | CruzaAbajo) for h in binarias(nodo))


# -- Validar, guardar, comparar --------------------------------------------------------------------


def _comprobar_tamano(datos: object) -> None:
    """Sin recursión: un JSON de un millón de nodos o mil niveles se rechaza antes de recorrerlo."""
    pila: list[tuple[object, int]] = [(datos, 1)]
    nodos = 0
    while pila:
        actual, nivel = pila.pop()
        nodos += 1
        if nodos > MAX_NODOS or nivel > MAX_ANIDADO:
            raise EstrategiaInvalidaError(
                ["es demasiado grande o está demasiado anidada para ser una estrategia legible"]
            )
        if isinstance(actual, dict):
            pila.extend((v, nivel + 1) for v in cast("dict[object, object]", actual).values())
        elif isinstance(actual, list | tuple):
            pila.extend((v, nivel + 1) for v in cast("list[object]", actual))
        elif isinstance(actual, str) and len(actual) > 5000:
            raise EstrategiaInvalidaError(["lleva un texto demasiado largo"])


def validar(definicion: object) -> Estrategia:
    """La estrategia validada, o `EstrategiaInvalidaError` con cada problema en llano."""
    if isinstance(definicion, Estrategia):
        return definicion
    if not isinstance(definicion, dict):
        raise EstrategiaInvalidaError(
            ["una estrategia es un objeto JSON con sus campos (nombre, monedas, intervalo…)"]
        )
    datos = cast("dict[str, object]", definicion)
    _comprobar_tamano(datos)
    try:
        return Estrategia.model_validate(datos)
    except ValidationError as error:
        raise EstrategiaInvalidaError(_explicar(error)) from None


def a_json(estrategia: Estrategia) -> dict[str, Any]:
    """La estrategia completa y normalizada (con sus valores por defecto), lista para guardar."""
    return estrategia.model_dump(mode="json", by_alias=True)


def _operativo(estrategia: Estrategia) -> dict[str, Any]:
    datos = a_json(estrategia)
    datos.pop("nombre", None)
    datos.pop("explicacion", None)
    return datos


def _canonico(datos: object) -> str:
    return json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def huella(estrategia: Estrategia) -> str:
    """La huella de lo que la estrategia HACE (sin nombre ni explicación): dos versiones con la
    misma huella operan igual, y cuentan como una al contar las versiones probadas."""
    return hashlib.sha256(_canonico(_operativo(estrategia)).encode()).hexdigest()[:16]


def misma(a: Estrategia, b: Estrategia) -> bool:
    """Idénticas, también en nombre y explicación (guardar la misma no crea otra versión)."""
    return _canonico(a_json(a)) == _canonico(a_json(b))


def esquema() -> dict[str, Any]:
    """El JSON Schema del formato (el que enseña `GET /api/medida/esquema` y el conector MCP)."""
    return Estrategia.model_json_schema(by_alias=True)


# -- Errores en llano ----------------------------------------------------------------------------

_QUE_LE_PASA: Final[dict[str, str]] = {
    "missing": "falta",
    "extra_forbidden": "no forma parte del formato (no se admiten campos de más)",
    "literal_error": "tiene que ser uno de estos: {expected}",
    "string_type": "tiene que ser un texto",
    "string_too_short": "no puede estar vacío",
    "string_too_long": "es demasiado largo: como mucho {max_length} caracteres",
    "string_pattern_mismatch": "no vale: solo minúsculas, cifras y _ (y empezar por letra)",
    "int_type": "tiene que ser un número entero",
    "int_parsing": "tiene que ser un número entero",
    "int_from_float": "tiene que ser un número entero, sin decimales",
    "float_type": "tiene que ser un número",
    "float_parsing": "tiene que ser un número",
    "finite_number": "tiene que ser un número normal (ni infinito ni NaN)",
    "greater_than": "tiene que ser mayor que {gt}",
    "greater_than_equal": "tiene que ser {ge} o más",
    "less_than": "tiene que ser menor que {lt}",
    "less_than_equal": "no puede pasar de {le}",
    "too_short": "necesita al menos {min_length}",
    "too_long": "admite como mucho {max_length}",
    "dict_type": "tiene que ser un objeto con sus campos",
    "model_type": "tiene que ser un objeto con sus campos",
    "model_attributes_type": "tiene que ser un objeto con sus campos",
    "list_type": "tiene que ser una lista",
    "tuple_type": "tiene que ser una lista de dos",
    "union_tag_not_found": "no es una condición válida",
    "union_tag_invalid": "no es una condición válida",
    "frozen_instance": "no se puede cambiar",
}


def _donde(loc: tuple[int | str, ...]) -> str:
    """'«indicadores → sma20 → periodo»', '«entrar → y → 2.ª»'. Sin las etiquetas repetidas que
    añade la unión del árbol."""
    partes: list[str] = []
    for parte in loc:
        if isinstance(parte, int):
            partes.append(f"{parte + 1}.ª")
            continue
        texto = str(parte)
        if partes and partes[-1] == texto:
            continue  # la etiqueta del discriminador repite la clave
        if texto in ("float", "str", "Referencia", "function-before[_operando(), union]"):
            continue
        partes.append(texto)
    return "«" + " → ".join(partes) + "»" if partes else "la estrategia"


def _contexto(ctx: dict[str, Any]) -> dict[str, str]:
    """Las cifras como se leen ('1', no '1.0') y las opciones sin comillas ni 'or'."""
    valores: dict[str, str] = {}
    for clave, valor in ctx.items():
        if isinstance(valor, bool):
            valores[clave] = str(valor)
        elif isinstance(valor, int | float):
            valores[clave] = _num(float(valor))
        else:
            valores[clave] = str(valor).replace("'", "").replace(" or ", " o ")
    return valores


def _explicar(error: ValidationError) -> list[str]:
    frases: list[str] = []
    for e in error.errors():
        loc = tuple(e.get("loc") or ())
        es_nombre = bool(loc) and loc[-1] == "[key]"
        donde = _donde(loc[:-1] if es_nombre else loc)
        tipo = str(e.get("type", ""))
        if es_nombre:
            frase = (
                f"{donde} no vale como nombre: solo minúsculas, cifras y _ (y empezar por letra)"
            )
        elif tipo == "missing":
            frase = f"falta {donde}"
        elif tipo in ("value_error", "assertion_error"):
            mensaje = str(e.get("msg", "")).removeprefix("Value error, ")
            frase = f"{donde}: {mensaje}" if donde != "la estrategia" else mensaje
        else:
            plantilla = _QUE_LE_PASA.get(tipo, "no vale")
            try:
                frase = f"{donde} {plantilla.format(**_contexto(dict(e.get('ctx') or {})))}"
            except (KeyError, IndexError):  # pragma: no cover - un contexto inesperado
                frase = f"{donde} no vale"
        if frase not in frases:
            frases.append(frase)
    return frases or ["no cumple el formato"]


# -- En llano -------------------------------------------------------------------------------------

_DE_FUENTE: Final[dict[str, str]] = {
    "cierre": "",
    "apertura": " de las aperturas",
    "maximo": " de los máximos",
    "minimo": " de los mínimos",
    "volumen": " del volumen",
}
_FRACCIONES: Final = ("retorno", "volatilidad")
"""Indicadores que dan una fracción: el número con que se comparan se lee como porcentaje."""


def _velas(n: int) -> str:
    return "1 vela" if n == 1 else f"{n} velas"


def _num(x: float) -> str:
    """'70', '0,5', '67.010'."""
    d = Decimal(str(x))
    if d == d.to_integral_value():
        return llano.numero(d, 0)
    return llano.cantidad(d, 6)


def _pct(fraccion: float) -> str:
    """'5 %', '2,5 %'."""
    d = Decimal(str(fraccion)) * 100
    if d == d.to_integral_value():
        return f"{llano.numero(d, 0)} %"
    return f"{llano.cantidad(d.quantize(Decimal('0.01')), 2)} %"


def describir_indicador(ind: Indicador) -> str:
    """'la media de 20 velas', 'el máximo de las 20 velas anteriores', 'el RSI de 14 velas'."""
    p = ind.periodo
    fuente = "" if ind.de in ("cierre",) else _DE_FUENTE[ind.de]
    if ind.tipo in ("maximo", "minimo"):
        cual = "máximo" if ind.tipo == "maximo" else "mínimo"
        natural = (ind.tipo == "maximo" and ind.de == "maximo") or (
            ind.tipo == "minimo" and ind.de == "minimo"
        )
        de = "" if natural else _DE_FUENTE[ind.de] or " de los cierres"
        if ind.atras == 1:
            return f"el {cual}{de} de las {_velas(p)} anteriores"
        base = f"el {cual}{de} de {_velas(p)}"
    elif ind.tipo == "sma":
        base = f"la media{fuente} de {_velas(p)}"
    elif ind.tipo == "ema":
        base = f"la media exponencial{fuente} de {_velas(p)}"
    elif ind.tipo == "rsi":
        base = f"el RSI{fuente} de {_velas(p)}"
    elif ind.tipo == "retorno":
        base = f"el cambio{fuente} en {_velas(p)}"
    elif ind.tipo == "volatilidad":
        base = f"la volatilidad{fuente} de {_velas(p)}"
    elif ind.tipo == "atr":
        base = f"el rango medio (ATR) de {_velas(p)}"
    else:
        base = f"el volumen medio de {_velas(p)}"
    if ind.atras:
        base += f", de hace {_velas(ind.atras)}"
    return base


def describir_operando(
    op: float | str | Referencia, indicadores: dict[str, Indicador], *, fraccion: bool = False
) -> str:
    """Un lado de una comparación en llano. `fraccion`: el otro lado es un cambio o una
    volatilidad, así que un número se lee como porcentaje."""
    nombre = nombre_de(op)
    if nombre is None:
        numero = float(cast("float", op))
        return _pct(numero) if fraccion else _num(numero)
    if nombre == PRECIO:
        texto = "el precio"
    else:
        ind = indicadores.get(nombre)
        texto = describir_indicador(ind) if ind is not None else f"«{nombre}»"
    if isinstance(op, Referencia) and op.por != 1:
        if op.por < 1:
            texto = f"{texto} menos un {_pct(1 - op.por)}"
        else:
            texto = f"{texto} más un {_pct(op.por - 1)}"
    return texto


def _es_fraccion(op: float | str | Referencia, indicadores: dict[str, Indicador]) -> bool:
    nombre = nombre_de(op)
    ind = indicadores.get(nombre) if nombre else None
    return ind is not None and ind.tipo in _FRACCIONES


def contraer(texto: str) -> str:
    """'de el' -> 'del' y 'a el' -> 'al', como se dice."""
    return texto.replace(" de el ", " del ").replace(" a el ", " al ")


_VERBO: Final[dict[str, tuple[str, str]]] = {
    ">": ("está por encima de", "estaba por encima de"),
    "<": ("está por debajo de", "estaba por debajo de"),
    ">=": ("está en o por encima de", "estaba en o por encima de"),
    "<=": ("está en o por debajo de", "estaba en o por debajo de"),
    "cruza_arriba": ("cruza por encima de", "cruzó por encima de"),
    "cruza_abajo": ("cruza por debajo de", "cruzó por debajo de"),
}


def describir_binaria(
    hoja: Binaria,
    indicadores: dict[str, Indicador],
    *,
    pasado: bool = False,
    valores: tuple[str, str] | None = None,
) -> str:
    """'la media de 20 velas cruza por encima de la de 50 velas'. Con `valores`, cada lado lleva
    su cifra entre paréntesis: '(67.010)'."""
    a, b = hoja.par
    textos: list[str] = []
    for op, otro, i in ((a, b, 0), (b, a, 1)):
        t = describir_operando(op, indicadores, fraccion=_es_fraccion(otro, indicadores))
        if i == 1:
            t = _abreviado(a, b, indicadores) or t
        if valores is not None and nombre_de(op) is not None:
            t = f"{t} ({valores[i]})"
        textos.append(t)
    verbo = _VERBO[hoja.CLAVE][1 if pasado else 0]
    return contraer(f" {textos[0]} {verbo} {textos[1]}").strip()


_FEMENINOS: Final = ("sma", "ema", "volatilidad")


def _abreviado(
    a: float | str | Referencia, b: float | str | Referencia, indicadores: dict[str, Indicador]
) -> str | None:
    """'la de 50 velas' cuando los dos lados son el mismo indicador con otro periodo."""
    if not (isinstance(a, str) and isinstance(b, str)):
        return None
    ia, ib = indicadores.get(a), indicadores.get(b)
    if ia is None or ib is None or ia.atras or ib.atras:
        return None
    if (ia.tipo, ia.de) != (ib.tipo, ib.de) or ia.periodo == ib.periodo:
        return None
    articulo = "la" if ib.tipo in _FEMENINOS else "el"
    return f"{articulo} de {_velas(ib.periodo)}"


def describir_condicion(
    nodo: Nodo, indicadores: dict[str, Indicador], *, dentro: bool = False
) -> str:
    """La condición entera en una frase; los grupos de dentro, entre paréntesis."""
    if isinstance(nodo, Todas | Alguna):
        partes = [describir_condicion(h, indicadores, dentro=True) for h in hijos(nodo)]
        une = " y " if isinstance(nodo, Todas) else " o "
        texto = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + une + partes[-1]
        return f"({texto})" if dentro and len(partes) > 1 else texto
    if isinstance(nodo, Negacion):
        return f"no se cumple que {describir_condicion(nodo.no, indicadores, dentro=True)}"
    return describir_binaria(nodo, indicadores)


def nombres_monedas(monedas: tuple[str, ...] | list[str]) -> str:
    """'Bitcoin', 'Bitcoin y Ethereum', 'Bitcoin, Ethereum y Solana'."""
    nombres = [nombre_hyperliquid(c) for c in monedas]
    if len(nombres) <= 1:
        return "".join(nombres)
    return f"{', '.join(nombres[:-1])} y {nombres[-1]}"


def _frase(texto: str) -> str:
    return texto[0].upper() + texto[1:] + "."


def reglas_en_llano(estrategia: Estrategia) -> list[str]:
    """Cada regla, como frase: lo que enseña la ficha y lo que se lee antes de desplegar."""
    e = estrategia
    ind = e.indicadores
    reglas = [
        f"Opera {nombres_monedas(e.monedas)} con velas de {INTERVALO_TXT[e.intervalo]}: decide "
        "al cierre de cada vela, solo con velas ya cerradas."
    ]
    reglas.append(_frase(f"compra cuando {describir_condicion(e.entrar, ind)}"))
    if e.salir is not None:
        reglas.append(_frase(f"vende cuando {describir_condicion(e.salir, ind)}"))
    r = e.riesgo
    if r.stop_perdida:
        reglas.append(
            f"Vende si el precio cae un {_pct(r.stop_perdida)} desde el de compra (stop de "
            "pérdida)."
        )
    if r.toma_beneficio:
        reglas.append(
            f"Vende si el precio sube un {_pct(r.toma_beneficio)} desde el de compra (toma de "
            "beneficio)."
        )
    if r.stop_seguimiento:
        reglas.append(
            f"Vende si el precio cae un {_pct(r.stop_seguimiento)} desde el cierre más alto "
            "desde que compró (stop que sigue al precio)."
        )
    if r.pausa_tras_stop and (r.stop_perdida or r.stop_seguimiento or r.toma_beneficio):
        reglas.append(
            f"Tras salir por un stop, espera {_velas(r.pausa_tras_stop)} antes de volver a comprar."
        )
    if r.stop_perdida or r.stop_seguimiento or r.toma_beneficio:
        reglas.append(
            "Los stops se miran con el cierre de cada vela: dentro de una vela el precio puede ir "
            "más allá antes de que salte."
        )
    t = e.tamano
    cuanto = f"el {_pct(t.fraccion)} de su valor"
    if len(e.monedas) == 1:
        tam = f"Cuando compra, invierte {cuanto}"
    elif t.reparto == "igual":
        tam = f"Con todas sus monedas dentro invierte {cuanto}, a partes iguales entre ellas"
    else:
        tam = (
            f"Con todas sus monedas dentro invierte {cuanto}, más en las que menos se mueven "
            f"(según su volatilidad de {_velas(t.periodo_volatilidad)})"
        )
    if t.maximo_por_moneda < 1 and (len(e.monedas) > 1 or t.maximo_por_moneda < t.fraccion):
        tam += f", como mucho el {_pct(t.maximo_por_moneda)} en una moneda"
    reglas.append(tam + ".")
    return reglas


# -- La explicación y los ejemplos ---------------------------------------------------------------

EXPLICACION: Final = """\
Una estrategia a medida es un objeto JSON con campos fijos. No es código: el motor la INTERPRETA,
y lo que no encaja en el formato se rechaza con un error en llano.

- `nombre` y `explicacion` (en llano: qué hace, por qué podría funcionar y sus pegas).
- `monedas`: de 1 a 5 (BTC, ETH, SOL…). `intervalo`: las velas con que decide (15m, 30m, 1h, 2h,
  4h, 8h, 12h, 1d, 3d, 1w); decide al cierre de cada vela y SOLO con velas ya cerradas.
- `indicadores`: por nombre, p. ej. {"sma20": {"tipo": "sma", "periodo": 20}}. Tipos: sma, ema,
  rsi, retorno (cambio en n velas, en fracción), maximo, minimo, volatilidad (en fracción), atr,
  volumen_medio. `fuente` (cierre, apertura, maximo, minimo, volumen) y `atras` (0: con la última
  vela cerrada; 1: como estaba una vela antes) son opcionales. Cada indicador tiene que usarse.
- `entrar` (obligatorio) y `salir` (opcional si hay algún stop): condiciones como árbol. Cada
  condición es un objeto con UNA clave: {"y": [..]}, {"o": [..]}, {"no": {..}}, {">": [a, b]},
  {"<": [a, b]}, {">=": [a, b]}, {"<=": [a, b]}, {"cruza_arriba": [a, b]}, {"cruza_abajo": [a, b]}.
  Cada lado (a, b) es un número, "precio" (el cierre de la última vela cerrada), el nombre de un
  indicador o {"valor": "sma50", "por": 0.95} (el valor multiplicado: un 5 % por debajo). Con
  retorno y volatilidad los números son fracciones (0.05 = 5 %). Como mucho 12 comparaciones por
  lado y 4 niveles de grupos.
- `tamano`: `fraccion` del valor del bot invertida con todas sus monedas dentro (por defecto 1),
  `reparto` igual o por volatilidad, `maximo_por_moneda` (fracción).
- `riesgo`: `stop_perdida`, `toma_beneficio` y `stop_seguimiento` en fracción (0.08 = 8 %),
  mirados con el cierre de cada vela; `pausa_tras_stop` en velas.

Una posición por moneda, todo o nada: compra cuando se cumple `entrar` y no la tiene; vende toda
la posición cuando se cumple `salir` o salta un stop. Sin apalancamiento ni ventas en corto.
"""


def _ejemplo(**campos: Any) -> dict[str, Any]:
    return a_json(Estrategia.model_validate(campos))


EJEMPLOS: Final[list[dict[str, Any]]] = [
    _ejemplo(
        nombre="Cruce de medias en Bitcoin",
        explicacion=(
            "Compra Bitcoin cuando la media de 20 días cruza por encima de la de 50 y lo vende "
            "cuando cruza por debajo. Sigue las tendencias largas; cuando el precio va de lado da "
            "señales falsas y paga comisión en cada una. El stop limita una caída brusca."
        ),
        monedas=["BTC"],
        intervalo="1d",
        indicadores={
            "sma20": {"tipo": "sma", "periodo": 20},
            "sma50": {"tipo": "sma", "periodo": 50},
        },
        entrar={"cruza_arriba": ["sma20", "sma50"]},
        salir={"cruza_abajo": ["sma20", "sma50"]},
        riesgo={"stop_perdida": 0.1},
    ),
    _ejemplo(
        nombre="RSI bajo con tendencia a favor (ETH)",
        explicacion=(
            "Compra Ethereum en una caída corta (RSI de 14 velas de 4 horas por debajo de 35) solo "
            "si sigue por encima de su media de 200 velas, y vende cuando el RSI se recupera por "
            "encima de 55. Opera a menudo; si la tendencia se rompe, el stop corta la pérdida."
        ),
        monedas=["ETH"],
        intervalo="4h",
        indicadores={
            "rsi14": {"tipo": "rsi", "periodo": 14},
            "sma200": {"tipo": "sma", "periodo": 200},
        },
        entrar={"y": [{"<": ["rsi14", 35]}, {">": ["precio", "sma200"]}]},
        salir={">": ["rsi14", 55]},
        riesgo={"stop_perdida": 0.06, "pausa_tras_stop": 6},
    ),
    _ejemplo(
        nombre="Ruptura de máximos (BTC, ETH, SOL)",
        explicacion=(
            "Compra cada moneda cuando cierra por encima del máximo de los 20 días anteriores y la "
            "vende cuando cierra por debajo del mínimo de los 10 anteriores o cae un 15 % desde lo "
            "más alto. Reparte más a la que menos se mueve. Pierde poco muchas veces y gana mucho "
            "pocas: hay que aguantar rachas malas."
        ),
        monedas=["BTC", "ETH", "SOL"],
        intervalo="1d",
        indicadores={
            "maximo20": {"tipo": "maximo", "periodo": 20, "atras": 1},
            "minimo10": {"tipo": "minimo", "periodo": 10, "atras": 1},
        },
        entrar={">": ["precio", "maximo20"]},
        salir={"<": ["precio", "minimo10"]},
        tamano={"reparto": "volatilidad", "maximo_por_moneda": 0.5},
        riesgo={"stop_seguimiento": 0.15},
    ),
    _ejemplo(
        nombre="Rebote del mínimo de 30 días (ETH)",
        explicacion=(
            "Compra Ethereum cuando el precio vuelve a subir por encima de un 5 % sobre su mínimo "
            "de 30 días (un rebote), vende si cae un 8 % desde la compra o gana un 20 %. Intenta "
            "comprar barato; si la caída sigue, el rebote es falso y salta el stop."
        ),
        monedas=["ETH"],
        intervalo="1d",
        indicadores={"minimo30": {"tipo": "minimo", "periodo": 30}},
        entrar={"cruza_arriba": ["precio", {"valor": "minimo30", "por": 1.05}]},
        riesgo={"stop_perdida": 0.08, "toma_beneficio": 0.2, "pausa_tras_stop": 3},
    ),
]
"""Ejemplos que se validan al importar el módulo: si el formato cambia y dejan de valer, falla
todo, no solo la pantalla que los enseña."""
