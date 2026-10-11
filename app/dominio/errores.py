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


class TablaSinPoligonos(DominioError):
    """La tabla por polígono se pidió sin FeatureCollection (AOI rectángulo/dibujo)."""


class ColumnaTablaEnConflicto(DominioError):
    """Una property del shapefile coincide con una columna de estadística de la tabla."""


class FiltroNubesNoDisponible(DominioError):
    """Se pidió filtrar por % de nubes en un sensor sin propiedad de nubes (ej. MODIS)."""


class IndiceIncompatible(DominioError):
    """El índice no tiene ningún sensor compatible en el catálogo."""


class DemasiadosPeriodos(DominioError):
    """La serie temporal pide más períodos que el tope (60): se levanta antes de tocar GEE."""

    def __init__(self, n: int, tope: int):
        self.n, self.tope = n, tope
        super().__init__(
            f"El rango genera {n} períodos y el máximo es {tope}: "
            "elegí un período más largo o acortá el rango de fechas.")
