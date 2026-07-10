"""Spike F3b — validar localhost + QWebChannel + GeoJSON. BORRAR al cerrar la fase."""
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

from app.mapa.servidor import ServidorMapa  # ver Paso C


class SpikeBridge(QObject):
    @Slot(str)
    def polygon_drawn(self, geojson: str):
        print("=== POLÍGONO RECIBIDO EN PYTHON ===")
        print(geojson)
        print("===================================")


def main():
    app = QApplication(sys.argv)
    assets = Path(__file__).parent / "assets"
    servidor = ServidorMapa(assets)
    servidor.iniciar()
    print(f"Servidor en http://127.0.0.1:{servidor.puerto}/_spike.html")

    view = QWebEngineView()
    bridge = SpikeBridge()
    canal = QWebChannel()
    canal.registerObject("bridge", bridge)
    view.page().setWebChannel(canal)                      # ANTES de load()
    view.load(QUrl(f"http://127.0.0.1:{servidor.puerto}/_spike.html"))
    view.resize(900, 600)
    view.show()
    try:
        app.exec()
    finally:
        servidor.detener()


if __name__ == "__main__":
    main()
