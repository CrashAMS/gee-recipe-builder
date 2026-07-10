"""Bridge QWebChannel — JS→Python push event-driven (HALLAZGO-1.1, 1.4)."""
import json

from PySide6.QtCore import QObject, Signal, Slot


class MapBridge(QObject):
    """Cachea el último GeoJSON y lo empuja por señal. NO hay pull síncrono desde JS."""

    aoi_recibida = Signal(dict)   # geometría GeoJSON (dict) del último polígono dibujado/editado
    aoi_eliminada = Signal()      # el usuario borró la AOI

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ultima_geometria = None

    @Slot(str)
    def polygon_drawn(self, geojson: str) -> None:
        try:
            geometria = json.loads(geojson)
        except json.JSONDecodeError:
            return  # payload inválido: ignorar en silencio (no romper la UI)
        self._ultima_geometria = geometria
        self.aoi_recibida.emit(geometria)

    @Slot()
    def aoi_borrada(self) -> None:
        self._ultima_geometria = None
        self.aoi_eliminada.emit()

    @property
    def ultima_geometria(self):
        """Lo lee 'Aceptar AOI' (pull-desde-cache; el push ya ocurrió)."""
        return self._ultima_geometria
