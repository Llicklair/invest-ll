"""Errores de la capa de datos de mercado (T013).

La distinción que importa: unos significan "esto no se puede hacer" y otros "esto ha fallado
ahora". Los segundos nunca deben dejar el histórico local peor que antes.
"""

from __future__ import annotations

from invest_ll.errors import InvestLLError


class FetchError(InvestLLError):
    """Raíz de los errores de descarga."""


class UnknownSymbolError(FetchError):
    """El proveedor no reconoce el activo.

    Se lanza en lugar de devolver una lista vacía: "no existe" y "no hubo operaciones" son cosas
    muy distintas, y confundirlas produce un histórico vacío con aspecto de válido.
    """


class UnsupportedIntervalError(FetchError):
    """El proveedor no ofrece esa granularidad.

    Se comprueba contra las capacidades declaradas antes de pedir nada, para fallar pronto y con
    un mensaje útil en vez de a mitad de una descarga larga.
    """


class NoDataError(FetchError):
    """El rango solicitado no tiene datos en el proveedor."""


class ProviderUnavailableError(FetchError):
    """El proveedor no responde tras agotar los reintentos.

    Recuperable: el histórico local queda intacto (FR-015). Volver a intentarlo más tarde es una
    respuesta razonable; perder lo que ya se tenía, no.
    """


class RateLimitError(FetchError):
    """Se alcanzó el límite de peticiones del proveedor.

    Recuperable con espera. Reintentar de inmediato solo empeora la situación.
    """
