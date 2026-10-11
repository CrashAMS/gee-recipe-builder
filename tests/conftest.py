import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import geopandas as gpd
from shapely.geometry import Polygon
import pytest

GOLDENS = Path(__file__).parent / "goldens"


def check_golden(nombre: str, contenido: str):
    GOLDENS.mkdir(exist_ok=True)
    ruta = GOLDENS / nombre
    if os.environ.get("UPDATE_GOLDENS"):
        ruta.write_text(contenido, encoding="utf-8")
        return
    assert ruta.read_text(encoding="utf-8") == contenido, f"golden desactualizado: {nombre}"


@pytest.fixture
def shp_valido(tmp_path):
    p = tmp_path / "aoi.shp"
    gpd.GeoDataFrame(geometry=[Polygon([(-58.5, -34.6), (-58.4, -34.6),
                                        (-58.4, -34.5), (-58.5, -34.5)])],
                      crs="EPSG:4326").to_file(p, engine="pyogrio")
    return p


@pytest.fixture
def shp_sin_prj(tmp_path):
    p = tmp_path / "aoi_noprj.shp"
    gpd.GeoDataFrame(geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
                      crs=None).to_file(p, engine="pyogrio")
    (p.with_suffix(".prj")).unlink(missing_ok=True)   # forzar CRS ausente
    return p


@pytest.fixture(autouse=True)
def _sin_worker_conteo_real(monkeypatch, tmp_path):
    """Ningun test de ventana debe tocar GEE: el WorkerConteo real se reemplaza por
    un QRunnable inerte (los tests que lo necesitan lo parchean por su cuenta).
    Ademas aisla `config._dir_config()` (F5): `exports.json`/`config.json` van a un
    tmp vacio, asi la recuperacion de exports al abrir la ventana nunca encuentra
    pendientes ni dispara GEE, y ningun test pisa la config real del usuario."""
    dir_cfg = tmp_path / "_appdata"
    monkeypatch.setenv("APPDATA", str(dir_cfg))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(dir_cfg))
    from PySide6.QtCore import QRunnable
    from app.ui import ventana_principal
    from app.ui.workers import SenalesConteo

    class WorkerConteoInerte(QRunnable):
        def __init__(self, receta, generacion, umbral, project_id=None):
            super().__init__()
            self.receta, self.generacion, self.umbral = receta, generacion, umbral
            self.senales = SenalesConteo()

        def run(self):
            pass

    monkeypatch.setattr(ventana_principal, "WorkerConteo", WorkerConteoInerte)


@pytest.fixture
def mapa_stub(monkeypatch):
    """Reemplaza WidgetMapa por un QWidget liviano: los tests de UI no cargan
    QtWebEngine ni piden tiles a la red. Misma API que usa VentanaPrincipal."""
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget

    from app.ui import ventana_principal

    class WidgetMapaStub(QWidget):
        aoi_dibujada = Signal(dict)
        aoi_borrada = Signal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.geometria_actual = None
            self.previews_cargados = []

        def cargar_preview(self, url_format: str, vis_leyenda: dict | None = None) -> None:
            self.previews_cargados.append((url_format, vis_leyenda))

        def limpiar_preview(self) -> None:
            self.previews_cargados.clear()

    monkeypatch.setattr(ventana_principal, "WidgetMapa", WidgetMapaStub)
    return WidgetMapaStub
