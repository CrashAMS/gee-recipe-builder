"""Excepciones del núcleo de dominio — F1."""


class DominioError(Exception):
    """Raíz de todos los errores del dominio."""


class RecetaJSONInvalida(DominioError):
    """El JSON de una receta guardada es ilegible o incompatible (mensaje accionable)."""


class SimboloDesconocido(DominioError):
    """Un símbolo del array `bands` no cae en banda, constante ni kernel."""


class FuenteAOIError(DominioError):
    """AOI inválida o no interpretable (shp incompleto, CRS ausente, etc.)."""


class MascaraNoDisponibleJS(DominioError):
    """Se pidió máscara de nubes en JS para un sensor sin snippet JS."""


class FiltroNubesNoDisponible(DominioError):
    """Se pidió filtrar por % de nubes en un sensor sin propiedad de nubes (ej. MODIS)."""


class IndiceIncompatible(DominioError):
    """El índice no tiene ningún sensor compatible en el catálogo."""
