"""Widget del mapa embebido. Import de QtWebEngine/QtWebChannel aislado acá (Addons ~169MB)."""
import json
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.mapa.bridge import MapBridge
from app.mapa.servidor import ServidorMapa

_ASSETS = Path(__file__).parent / "assets"


class WidgetMapa(QWidget):
    aoi_dibujada = Signal(dict)   # re-expone MapBridge.aoi_recibida hacia el resto de la UI
    aoi_borrada = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Import lazy: solo al construir el widget se toca PySide6-Addons
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._servidor = ServidorMapa(_ASSETS)
        self._servidor.iniciar()

        self._bridge = MapBridge()
        self._bridge.aoi_recibida.connect(self.aoi_dibujada)
        self._bridge.aoi_eliminada.connect(self.aoi_borrada)

        self._view = QWebEngineView(self)
        self._canal = QWebChannel()
        self._canal.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._canal)          # ANTES de load() (HALLAZGO-1.4)
        self._view.load(QUrl(f"http://127.0.0.1:{self._servidor.puerto}/index.html"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    # ── API para el resto de la UI ──
    @property
    def geometria_actual(self):
        """GeoJSON dict de la AOI viva (o None). Lo lee 'Aceptar AOI'."""
        return self._bridge.ultima_geometria

    def cargar_preview(self, url_format: str) -> None:
        self._view.page().runJavaScript(f"cargarPreview({json.dumps(url_format)});")

    def limpiar_preview(self) -> None:
        self._view.page().runJavaScript("limpiarPreview();")

    def closeEvent(self, event):
        self._servidor.detener()
        super().closeEvent(event)
