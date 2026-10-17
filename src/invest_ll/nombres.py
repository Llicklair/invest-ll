"""Cómo se llama cada activo para quien no sabe qué es un ticker. **Un único sitio.**

El panel habla a alguien que no sabe qué es `SPY` ni `IEF` (docs/panel-v2.md, sección 2: "ticker
→ nombre del activo"). Si cada pantalla tradujera por su cuenta, el mismo fondo acabaría llamándose
"S&P 500" en el mercado y "Bolsa de EE.UU." en la cartera. Aquí está la traducción, y también qué
se compra desde España en lugar de cada fondo de EE.UU. (`equivalente`): los ISIN solo donde no
hay duda, como pide la especificación.

Acepta el símbolo en cualquiera de las formas que circulan por el proyecto: `BTC/USDT` (órdenes y
cartera), `BTCUSDT` (universo de Binance), `BTC-USDT` (carpeta de descarga), `LUNAUSDT~2` (ticker
reutilizado) o `SPY`. No toca la red ni el disco.
"""

from __future__ import annotations

from typing import Final

MONEDAS_DE_COTIZACION: Final = ("USDT",)

SUFIJOS_EN_EUROS: Final = (".MC", ".DE", ".F", ".PA", ".AS", ".MI", ".BR", ".LS")
"""Bolsas europeas que cotizan en euros, por el sufijo con que las nombra yfinance (`SAN.MC`)."""

NOMBRES: Final[dict[str, str]] = {
    # Fondos cotizados (ETF) de EE.UU. que usan las estrategias de bolsa y el mercado.
    "SPY": "Bolsa de EE.UU.",
    "IEF": "Bonos del Tesoro de EE.UU. a 7-10 años",
    "TLT": "Bonos del Tesoro de EE.UU. a más de 20 años",
    "SHY": "Bonos del Tesoro de EE.UU. a corto plazo",
    "GLD": "Oro",
    "EFA": "Bolsa de países desarrollados fuera de EE.UU.",
    "EEM": "Bolsa de países emergentes",
    "DBC": "Materias primas",
    "VNQ": "Inmobiliario de EE.UU.",
    "QQQ": "Tecnológicas de EE.UU. (Nasdaq 100)",
    "XLK": "Tecnología de EE.UU.",
    "XLF": "Bancos y finanzas de EE.UU.",
    "XLE": "Energía de EE.UU.",
    "XLV": "Salud de EE.UU.",
    "XLP": "Consumo básico de EE.UU.",
    "XLU": "Servicios públicos de EE.UU.",
    "AAPL": "Apple",
    # Criptomonedas: las grandes y las que suelen entrar en la cesta con freno.
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "BNB": "BNB",
    "SOL": "Solana",
    "XRP": "XRP",
    "ADA": "Cardano",
    "DOGE": "Dogecoin",
    "AVAX": "Avalanche",
    "NEAR": "NEAR",
    "SUI": "Sui",
    "UNI": "Uniswap",
    "ENA": "Ethena",
    "PUMP": "Pump.fun",
    "LINK": "Chainlink",
    "DOT": "Polkadot",
    "LTC": "Litecoin",
    "BCH": "Bitcoin Cash",
    "TRX": "TRON",
    "TON": "Toncoin",
    "SHIB": "Shiba Inu",
    "PEPE": "Pepe",
    "ATOM": "Cosmos",
    "FIL": "Filecoin",
    "APT": "Aptos",
    "ARB": "Arbitrum",
    "OP": "Optimism",
    "AAVE": "Aave",
    "ETC": "Ethereum Classic",
    "XLM": "Stellar",
    "HBAR": "Hedera",
    "ICP": "Internet Computer",
    "MATIC": "Polygon",
    "POL": "Polygon",
    "TAO": "Bittensor",
    "WLD": "Worldcoin",
    "LUNA": "Terra (LUNA)",
}

NOMBRES_HYPERLIQUID: Final[dict[str, str]] = {
    # Las monedas de Hyperliquid que no están arriba, por su nombre allí (distingue mayúsculas).
    # Las más negociadas; las demás se enseñan con su símbolo.
    "HYPE": "Hyperliquid",
    "PURR": "Purr",
    "FARTCOIN": "Fartcoin",
    "TRUMP": "Official Trump",
    "BONK": "Bonk",
    "FLOKI": "Floki",
    "WIF": "dogwifhat",
    "ZEC": "Zcash",
    "XMR": "Monero",
    "TIA": "Celestia",
    "INJ": "Injective",
    "SEI": "Sei",
    "JUP": "Jupiter",
    "PENGU": "Pudgy Penguins",
    "VIRTUAL": "Virtuals Protocol",
    "MKR": "Maker",
    "CRV": "Curve",
    "LDO": "Lido",
    "ONDO": "Ondo",
    "RENDER": "Render",
    "FET": "Fetch.ai",
    "BERA": "Berachain",
    "KAITO": "Kaito",
    "XPL": "Plasma",
    "ASTER": "Aster",
    "WLFI": "World Liberty Financial",
    "STX": "Stacks",
    "IP": "Story",
    "JTO": "Jito",
    "PYTH": "Pyth Network",
    "STRK": "Starknet",
    "ZRO": "LayerZero",
    "EIGEN": "EigenLayer",
    "ETHFI": "ether.fi",
    "PENDLE": "Pendle",
    "GMX": "GMX",
    "DYDX": "dYdX",
    "SAND": "The Sandbox",
    "APE": "ApeCoin",
    "IMX": "Immutable",
    "GALA": "Gala",
    "RUNE": "THORChain",
    "ALGO": "Algorand",
    "KAS": "Kaspa",
    "W": "Wormhole",
    "NOT": "Notcoin",
    "MOVE": "Movement",
    "PAXG": "Oro tokenizado (PAX Gold)",
    "LUNC": "Terra Classic",
    "NEIRO": "Neiro",
    "DOGS": "Dogs",
    "MON": "Monad",
    "VVV": "Venice",
}

POR_MIL_HYPERLIQUID: Final = "k"
"""Hyperliquid cotiza algunas monedas de precio diminuto por miles: `kPEPE` son 1.000 PEPE."""


def nombre_hyperliquid(coin: str) -> str:
    """El nombre llano de una moneda de Hyperliquid (`BTC` -> Bitcoin, `kPEPE` -> Pepe (por
    1.000)). Si no se conoce, su símbolo tal cual."""
    if coin in NOMBRES_HYPERLIQUID:
        return NOMBRES_HYPERLIQUID[coin]
    if coin in NOMBRES:
        return NOMBRES[coin]
    resto = coin.removeprefix(POR_MIL_HYPERLIQUID)
    if resto != coin and resto and resto.isupper():
        return f"{nombre_hyperliquid(resto)} (por 1.000)"
    return coin


_EQUIVALENTES: Final[dict[str, tuple[str, str]]] = {
    # simbolo -> (forma corta para un titulo, que comprar desde Espana)
    "SPY": (
        "un ETF del S&P 500",
        "un ETF UCITS del S&P 500 (p. ej. iShares Core S&P 500, ISIN IE00B5BMR087)",
    ),
    "IEF": (
        "un ETF de bonos del Tesoro de EE.UU. a 7-10 años",
        "un ETF UCITS de bonos del Tesoro de EE.UU. a 7-10 años",
    ),
    "GLD": (
        "un ETC de oro físico",
        "un ETC de oro físico (p. ej. iShares Physical Gold, ISIN IE00B4ND3602)",
    ),
    "EEM": (
        "un ETF de mercados emergentes",
        "un ETF UCITS de mercados emergentes (p. ej. iShares Core MSCI EM IMI, ISIN IE00BKM4GZ66)",
    ),
    "EFA": (
        "un ETF de bolsa de países desarrollados fuera de EE.UU.",
        "un ETF UCITS de bolsa de países desarrollados fuera de EE.UU.",
    ),
    "TLT": (
        "un ETF de bonos del Tesoro de EE.UU. a más de 20 años",
        "un ETF UCITS de bonos del Tesoro de EE.UU. a más de 20 años",
    ),
    "DBC": ("un ETF de materias primas", "un ETF UCITS de materias primas"),
    "VNQ": (
        "un ETF inmobiliario estadounidense (REIT)",
        "un ETF UCITS inmobiliario estadounidense (REIT)",
    ),
    "SHY": (
        "un ETF de bonos del Tesoro a corto plazo",
        "un ETF UCITS de bonos del Tesoro a corto plazo",
    ),
}


def base(simbolo: str) -> str:
    """El activo sin la moneda de cotización: `BTC/USDT`, `BTCUSDT~2` y `btc-usdt` dan `BTC`."""
    limpio = simbolo.strip().upper().split("~")[0]
    for separador in ("/", "-"):
        if separador in limpio:
            return limpio.split(separador)[0]
    for moneda in MONEDAS_DE_COTIZACION:
        if limpio.endswith(moneda) and len(limpio) > len(moneda):
            return limpio.removesuffix(moneda)
    return limpio


def es_cripto(simbolo: str) -> bool:
    """Un par contra USDT (`BTC/USDT`, `BTCUSDT`, `BTC-USDT`). Lo demás se trata como bolsa."""
    limpio = simbolo.strip().upper().split("~")[0]
    return any(
        limpio.endswith(f"{sep}{m}") for m in MONEDAS_DE_COTIZACION for sep in ("/", "-", "")
    )


def moneda_de(simbolo: str) -> str:
    """La moneda en que cotiza: `BTC/EUR` → EUR, `BTCUSDT` → USDT, `SAN.MC` → EUR, `SPY` → USD.

    En un par manda lo que va detrás de la barra; un par de Binance sin barra cotiza en su moneda
    de cotización; en bolsa, las europeas en euros por su sufijo y lo demás (los fondos de EE.UU.
    del proyecto) en dólares.
    """
    limpio = simbolo.strip().upper().split("~")[0]
    if "/" in limpio and limpio.split("/", 1)[1]:
        return limpio.split("/", 1)[1]
    for cotizacion in MONEDAS_DE_COTIZACION:
        if limpio.endswith(cotizacion) and len(limpio) > len(cotizacion):
            return cotizacion
    if limpio.endswith(SUFIJOS_EN_EUROS):
        return "EUR"
    return "USD"


def nombre_conocido(simbolo: str) -> str | None:
    """El nombre llano si lo hay; `None` si el activo no está en la lista."""
    return NOMBRES.get(base(simbolo))


def nombre_llano(simbolo: str) -> str:
    """El nombre para enseñar. Si no se conoce, el propio activo sin la moneda (`AVAX`)."""
    return nombre_conocido(simbolo) or base(simbolo)


def equivalente(simbolo: str) -> str | None:
    """Qué comprar desde España en lugar de este fondo de EE.UU. `None` si no es uno de ellos."""
    par = _EQUIVALENTES.get(base(simbolo))
    return par[1] if par else None


def equivalente_corto(simbolo: str) -> str:
    """La forma corta para un título ("un ETF del S&P 500"); el nombre llano si no hay."""
    par = _EQUIVALENTES.get(base(simbolo))
    return par[0] if par else nombre_llano(simbolo)
