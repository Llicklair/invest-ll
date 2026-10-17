"""Lo propio de cada exchange, en un sitio: una ficha por exchange (docs/panel-v4-real.md §1).

El conector genérico (`ccxt_conector`) no sabe nada de ningún exchange en concreto: todo lo que
cambia de uno a otro está aquí, como datos. Añadir un exchange es escribir su ficha (y comprobarla
de verdad con `python -m invest_ll.exchanges.comprobar`).

Lo comprobado el 2026-10-17 contra ccxt 4.5.68 y la documentación de cada exchange:

- **Claves** (`requiredCredentials` de ccxt): Binance, Bybit y Kraken piden apiKey + secret; OKX,
  además, la passphrase (`password`); Hyperliquid, la dirección de la cartera (`walletAddress`) y la
  clave privada (`privateKey`) de una API wallet; Coinbase Advanced, el nombre de una clave de CDP
  (`organizations/.../apiKeys/...`) y su clave privada ECDSA en PEM (Coinbase: "Do NOT select
  Ed25519").
- **Red de pruebas** (`set_sandbox_mode(True)` en ccxt): Binance (testnet.binance.vision), Bybit
  (api-testnet.bybit.com, cuenta aparte en testnet.bybit.com), OKX (el modo demo: la misma web con
  la cabecera `x-simulated-trading: 1`) e Hyperliquid (api.hyperliquid-testnet.xyz). Kraken (solo
  tiene demo de futuros) y Coinbase no tienen red de pruebas de contado en ccxt.
- **Si la clave puede retirar**: Binance `GET /sapi/v1/account/apiRestrictions`
  (`enableWithdrawals`; no existe en la red de pruebas), Bybit `GET /v5/user/query-api`
  (`permissions.Wallet` con `Withdraw`), OKX `GET /api/v5/account/config` (`perm` con `withdraw`),
  Kraken `POST /0/private/GetApiKeyInfo` (`permissions` con `withdraw-funds`), Coinbase
  `GET /api/v3/brokerage/key_permissions` (`can_transfer`). En Hyperliquid una API wallet no puede
  retirar por diseño (retirar es una acción firmada por la cartera principal): lo que se comprueba
  es que la clave privada NO sea la de la cartera principal.
- **Id de cliente**: cada exchange tiene su formato (`FORMATOS_ID`); el conector deriva uno válido
  del que le dan, siempre el mismo para el mismo (`ccxt_conector.id_en_el_exchange`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

FormatoId = Literal["texto36", "alnum32", "kraken", "texto64", "hex128"]
"""Cómo tiene que ser el id de cliente en cada exchange (ver `ccxt_conector.FORMATOS_ID`)."""

BuscarPorId = Literal["fetch_order", "abiertas_y_cerradas", "recientes"]
"""Cómo se encuentra una orden por su id de cliente:

- `fetch_order`: el exchange la busca directamente por ese id (Binance, OKX, Hyperliquid).
- `abiertas_y_cerradas`: se piden las abiertas y las cerradas filtrando por ese id (Bybit, Kraken).
- `recientes`: se piden las órdenes recientes del par y se busca entre ellas (Coinbase).
"""

ComoPermisos = Literal["binance", "bybit", "okx", "kraken", "coinbase", "hyperliquid"]


@dataclass(frozen=True, slots=True)
class Campo:
    """Un campo de las claves, como lo pide ccxt (`clave`) y como se le explica a Marcos."""

    clave: str
    nombre: str
    secreto: bool
    ayuda: str


@dataclass(frozen=True, slots=True)
class Ficha:
    id: str
    nombre: str
    id_ccxt: str
    campos: tuple[Campo, ...]
    red_de_pruebas: str | None
    """Dónde está la red de pruebas, en llano; `None` si el exchange no tiene."""
    como_conseguir_pruebas: tuple[str, ...]
    como_conseguir_real: tuple[str, ...]
    aviso: str | None
    permisos: ComoPermisos
    sabe_si_retira_en_pruebas: bool
    """En dinero real todos lo dicen; en la red de pruebas, no todos (Binance no)."""
    formato_id: FormatoId
    param_id_cliente: str
    """El parámetro de `create_order` de ccxt para el id de cliente."""
    buscar_por_id: BuscarPorId
    param_buscar_id: str
    compra_a_mercado_con_precio: bool
    """Coinbase compra a mercado por importe (ccxt lo calcula con el precio) e Hyperliquid no tiene
    órdenes de mercado (ccxt las hace límite con un deslizamiento máximo sobre el precio)."""
    opciones_ccxt: tuple[tuple[str, object], ...] = ()
    params_orden: tuple[tuple[str, object], ...] = ()
    params_saldo: tuple[tuple[str, object], ...] = ()
    tamanos_libro: tuple[int, ...] | None = None
    """Los tamaños de libro que acepta el exchange (Binance solo unos pocos). `None`: cualquiera."""
    max_libro: int = 100
    max_velas: int = 1000
    """Velas por petición, como mucho. Si se piden más, se pide varias veces."""
    par_de_referencia: str = "BTC/USDT"
    """El par de BTC en ese exchange (para comprobar que responde)."""
    par_de_pruebas: str | None = None
    """Un par con libro en la red de pruebas, si no es el de referencia."""

    @property
    def tiene_pruebas(self) -> bool:
        return self.red_de_pruebas is not None

    def sabe_si_retira(self, red: Literal["pruebas", "real"]) -> bool:
        return red == "real" or self.sabe_si_retira_en_pruebas

    def campo(self, clave: str) -> Campo:
        return next(c for c in self.campos if c.clave == clave)


SOLO_CONTADO: Final[tuple[tuple[str, object], ...]] = (
    ("defaultType", "spot"),
    ("fetchMarkets", {"types": ["spot"]}),
)
"""Solo los mercados de contado: menos que descargar y ningún derivado por error."""

API_KEY: Final = Campo(
    clave="apiKey",
    nombre="Clave de la API (API key)",
    secreto=False,
    ayuda="La clave pública: identifica la clave, no basta para operar.",
)
SECRETO: Final = Campo(
    clave="secret",
    nombre="Clave secreta (secret)",
    secreto=True,
    ayuda="Se enseña una sola vez al crear la clave. Nunca la compartas.",
)

BINANCE: Final = Ficha(
    id="binance",
    nombre="Binance",
    id_ccxt="binance",
    campos=(API_KEY, SECRETO),
    red_de_pruebas="testnet.binance.vision",
    como_conseguir_pruebas=(
        "Entra en testnet.binance.vision con tu cuenta de GitHub.",
        "Pulsa «Generate HMAC_SHA256 Key» y ponle un nombre (las Ed25519 o RSA no sirven aquí).",
        "Copia la API Key y la Secret Key: la secreta solo se enseña una vez.",
        "El saldo de pruebas se reparte solo; la red de pruebas se borra más o menos una vez al mes.",
    ),
    como_conseguir_real=(
        "En binance.com: tu perfil → Gestión de API → Crear API → «Generada por el sistema».",
        "Deja «Habilitar lectura» y marca «Habilitar trading de Spot y Margin».",
        "NO marques «Habilitar retiros»: con ese permiso el panel no activa el dinero real.",
        "Si puedes, restringe la clave a la IP de tu casa.",
        "Copia la API Key y la Secret Key: la secreta solo se enseña una vez.",
    ),
    aviso=None,
    permisos="binance",
    sabe_si_retira_en_pruebas=False,
    formato_id="texto36",
    param_id_cliente="clientOrderId",
    buscar_por_id="fetch_order",
    param_buscar_id="clientOrderId",
    compra_a_mercado_con_precio=False,
    opciones_ccxt=(
        *SOLO_CONTADO,
        ("warnOnFetchOpenOrdersWithoutSymbol", False),
    ),
    tamanos_libro=(5, 10, 20, 50, 100, 500, 1000, 5000),
    max_libro=5000,
    max_velas=1000,
)

HYPERLIQUID: Final = Ficha(
    id="hyperliquid",
    nombre="Hyperliquid",
    id_ccxt="hyperliquid",
    campos=(
        Campo(
            clave="walletAddress",
            nombre="Dirección de tu cartera",
            secreto=False,
            ayuda=(
                "La de tu cuenta de Hyperliquid (0x…), la principal: NO la de la API wallet. Es "
                "pública: identifica la cuenta."
            ),
        ),
        Campo(
            clave="privateKey",
            nombre="Clave privada de la API wallet",
            secreto=True,
            ayuda=(
                "La de la API wallet que creaste en Hyperliquid (More → API), no la de tu "
                "cartera: la API wallet opera pero no puede retirar."
            ),
        ),
    ),
    red_de_pruebas="la red de pruebas de Hyperliquid (app.hyperliquid-testnet.xyz)",
    como_conseguir_pruebas=(
        "Entra en app.hyperliquid-testnet.xyz con tu cartera (la misma dirección que en la real).",
        "Pide USDC de pruebas en «Faucet»: solo los da a direcciones que ya han depositado en la "
        "red real.",
        "En More → API crea una API wallet («Generate»), ponle nombre y autorízala.",
        "Copia su clave privada (se enseña una vez) y pega aquí la dirección de TU cartera y esa "
        "clave privada.",
        "Para la orden de prueba usa PURR/USDC o HYPE/USDC: en la red de pruebas el BTC de contado "
        "casi no tiene libro.",
    ),
    como_conseguir_real=(
        "Entra en app.hyperliquid.xyz con tu cartera.",
        "More → API → crea una API wallet («Generate»), ponle nombre y autorízala con tu cartera.",
        "Copia la clave privada de la API wallet (se enseña una vez).",
        "Pega aquí la dirección de TU cartera y la clave privada de la API wallet. Nunca la clave "
        "privada de tu cartera principal: esa sí puede retirar, y con ella el panel no activa real.",
    ),
    aviso=(
        "Hyperliquid no usa claves de API: una API wallet firma las órdenes por ti y no puede "
        "retirar. Caduca (como mucho a los 180 días): cuando caduque, crea otra."
    ),
    permisos="hyperliquid",
    sabe_si_retira_en_pruebas=True,
    formato_id="hex128",
    param_id_cliente="clientOrderId",
    buscar_por_id="fetch_order",
    param_buscar_id="clientOrderId",
    compra_a_mercado_con_precio=True,
    opciones_ccxt=SOLO_CONTADO,
    # Una "orden de mercado" en Hyperliquid es una límite IOC con un precio máximo: ccxt pone un
    # 5 % de deslizamiento por defecto; con un 2 %, si el precio se ha ido más, no se ejecuta.
    params_orden=(("slippage", "0.02"),),
    params_saldo=(("type", "spot"),),
    max_libro=20,
    max_velas=5000,
    # ccxt llama BTC/USDC al BTC de contado de Hyperliquid (el token UBTC, "@142").
    par_de_referencia="BTC/USDC",
    # En la red de pruebas, BTC/USDC es otro token, casi sin libro (comprobado el 2026-10-17).
    par_de_pruebas="PURR/USDC",
)

BYBIT: Final = Ficha(
    id="bybit",
    nombre="Bybit",
    id_ccxt="bybit",
    campos=(API_KEY, SECRETO),
    red_de_pruebas="testnet.bybit.com",
    como_conseguir_pruebas=(
        "Crea una cuenta en testnet.bybit.com (es aparte de la real).",
        "Pide monedas de prueba en Activos → «Request test coins».",
        "Perfil → API → Crear nueva clave → «Generada por el sistema», lectura y escritura.",
        "Marca solo el permiso de contado (Spot → Trade); nada de Wallet ni retiros.",
        "Copia la API Key y el Secret.",
    ),
    como_conseguir_real=(
        "En bybit.com: Perfil → API → Crear nueva clave → «Generada por el sistema».",
        "Elige lectura y escritura y marca solo el contado (Spot → Trade).",
        "NO marques «Wallet → Withdraw» (retirar): con ese permiso el panel no activa real.",
        "Restringe la clave a tu IP: sin IP, Bybit la caduca a los 3 meses.",
        "Copia la API Key y el Secret.",
    ),
    aviso=None,
    permisos="bybit",
    sabe_si_retira_en_pruebas=True,
    formato_id="texto36",
    param_id_cliente="clientOrderId",
    buscar_por_id="abiertas_y_cerradas",
    param_buscar_id="orderLinkId",
    compra_a_mercado_con_precio=False,
    opciones_ccxt=SOLO_CONTADO,
    max_libro=200,
    max_velas=1000,
)

OKX: Final = Ficha(
    id="okx",
    nombre="OKX",
    id_ccxt="okx",
    campos=(
        API_KEY,
        SECRETO,
        Campo(
            clave="password",
            nombre="Frase de contraseña (passphrase)",
            secreto=True,
            ayuda="La que escribiste al crear la clave. OKX no la vuelve a enseñar.",
        ),
    ),
    red_de_pruebas="el modo demo de OKX (Demo trading)",
    como_conseguir_pruebas=(
        "En okx.com: Trade → «Demo trading» para entrar en el modo de pruebas.",
        "Dentro del modo demo: Perfil → API → crear una clave de API de demo.",
        "Permisos: Read y Trade, sin Withdraw. Escribe una passphrase y apúntala.",
        "Copia la API key, la Secret key y la passphrase.",
    ),
    como_conseguir_real=(
        "En okx.com: Perfil → API → Crear clave de API («API trading»).",
        "Permisos: Read y Trade. NO marques Withdraw (retirar): con él el panel no activa real.",
        "Escribe una passphrase y apúntala: OKX no la vuelve a enseñar.",
        "Vincula tu IP si puedes: sin IP, OKX borra las claves con Trade tras 14 días sin uso.",
        "Copia la API key, la Secret key y la passphrase.",
    ),
    aviso=None,
    permisos="okx",
    sabe_si_retira_en_pruebas=True,
    formato_id="alnum32",
    param_id_cliente="clientOrderId",
    buscar_por_id="fetch_order",
    param_buscar_id="clientOrderId",
    compra_a_mercado_con_precio=False,
    opciones_ccxt=SOLO_CONTADO,
    # Comprar a mercado: la cantidad en la moneda que se compra (si no, OKX la lee como importe).
    params_orden=(("tgtCcy", "base_ccy"),),
    max_libro=400,
    max_velas=300,
)

KRAKEN: Final = Ficha(
    id="kraken",
    nombre="Kraken",
    id_ccxt="kraken",
    campos=(
        API_KEY,
        Campo(
            clave="secret",
            nombre="Clave privada (Private Key)",
            secreto=True,
            ayuda="Se enseña una sola vez al crear la clave. Nunca la compartas.",
        ),
    ),
    red_de_pruebas=None,
    como_conseguir_pruebas=(),
    como_conseguir_real=(
        "En kraken.com: Ajustes → API (Connections & API) → crear una clave.",
        "Permisos: Funds → Query; Orders and trades → Query open orders & trades, Query closed "
        "orders & trades, Create & modify orders y Cancel & close orders.",
        "NO marques «Withdraw Funds» ni los de direcciones de retirada: con ellos el panel no "
        "activa el dinero real.",
        "Copia la API Key y la Private Key.",
    ),
    aviso=(
        "Kraken no tiene red de pruebas de contado: antes de dinero real, prueba la estrategia en "
        "ficticio."
    ),
    permisos="kraken",
    sabe_si_retira_en_pruebas=False,
    formato_id="kraken",
    param_id_cliente="clientOrderId",
    buscar_por_id="abiertas_y_cerradas",
    param_buscar_id="clientOrderId",
    compra_a_mercado_con_precio=False,
    max_libro=500,
    max_velas=720,
    par_de_referencia="BTC/USD",
)

COINBASE: Final = Ficha(
    id="coinbase",
    nombre="Coinbase (Advanced)",
    id_ccxt="coinbase",
    campos=(
        Campo(
            clave="apiKey",
            nombre="Nombre de la clave",
            secreto=False,
            ayuda="Empieza por organizations/…/apiKeys/…",
        ),
        Campo(
            clave="secret",
            nombre="Clave privada",
            secreto=True,
            ayuda=(
                "Entera, desde -----BEGIN EC PRIVATE KEY----- hasta -----END EC PRIVATE KEY-----."
            ),
        ),
    ),
    red_de_pruebas=None,
    como_conseguir_pruebas=(),
    como_conseguir_real=(
        "Entra en portal.cdp.coinbase.com con tu cuenta de Coinbase → API Keys → Create API key.",
        "En las opciones avanzadas elige el algoritmo ECDSA (Ed25519 no sirve para Advanced Trade).",
        "Permisos: View y Trade. NO marques Transfer: con él el panel no activa el dinero real.",
        "Copia el nombre de la clave (organizations/…/apiKeys/…) y la clave privada entera.",
    ),
    aviso=(
        "Coinbase no tiene red de pruebas: antes de dinero real, prueba la estrategia en ficticio."
    ),
    permisos="coinbase",
    sabe_si_retira_en_pruebas=False,
    formato_id="texto64",
    # ccxt ignora `clientOrderId` en Coinbase y pone uno suyo: el de la API va tal cual.
    param_id_cliente="client_order_id",
    buscar_por_id="recientes",
    param_buscar_id="client_order_id",
    compra_a_mercado_con_precio=True,
    max_libro=500,
    max_velas=300,
    par_de_referencia="BTC/USD",
)

FICHAS: Final[tuple[Ficha, ...]] = (BINANCE, HYPERLIQUID, BYBIT, OKX, KRAKEN, COINBASE)
POR_ID: Final[dict[str, Ficha]] = {f.id: f for f in FICHAS}
