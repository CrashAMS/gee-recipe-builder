"""Clasificación accionable de errores de GEE — F2 [HALLAZGO-1.1]."""
import re


class ErrorEjecucionGEE(Exception):
    """Base de errores accionables del ejecutor."""


class ComputoDemasiadoGrande(ErrorEjecucionGEE):
    """El servidor no puede computar la imagen (tile de cómputo > 48-80 MiB)."""


class DescargaExcedeLimite(ErrorEjecucionGEE):
    """La descarga directa excede 32MB / 10000px por lado → camino Drive (F4)."""


class ErrorGEEDesconocido(ErrorEjecucionGEE):
    """EEException no reconocida — se propaga el mensaje crudo."""


# "Output of image computation is too large (3 bands for N pixels = 183.0 MiB > 80.0 MiB)"
_PATRON_COMPUTO = re.compile(r"output of image computation is too large", re.I)
# "Total request size (X bytes) must be less than or equal to 33554432 bytes."
# "Pixel grid dimensions (AxB) must be less than or equal to 10000."
_PATRON_DESCARGA = re.compile(
    r"(total request size|33554432|pixel grid dimensions.*10000|must be less than or equal to 10000)",
    re.I,
)


def clasificar_error(exc: Exception) -> ErrorEjecucionGEE:
    msg = str(exc)
    if _PATRON_COMPUTO.search(msg):
        return ComputoDemasiadoGrande(
            "El cómputo de la imagen es demasiado grande para GEE. "
            "Subí `scale` (menos resolución) o reducí el AOI. "
            f"Detalle GEE: {msg}"
        )
    if _PATRON_DESCARGA.search(msg):
        return DescargaExcedeLimite(
            "La imagen excede el límite de descarga directa (32MB / 10000px por lado). "
            "Usá el export a Google Drive (disponible en F4) o subí `scale` / achicá el AOI. "
            f"Detalle GEE: {msg}"
        )
    return ErrorGEEDesconocido(msg)
