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
def shp_lotes(tmp_path):
    """F6b: 3 lotes con properties (`lote` str, `fecha` date, `ha` float con un NaN), 4326.
    Lo consumen desde_archivo_features y la tabla por polígono (F9)."""
    import datetime as dt
    p = tmp_path / "lotes.shp"
    polis = [Polygon([(-58.5 + i * 0.01, -34.6), (-58.49 + i * 0.01, -34.6),
                      (-58.49 + i * 0.01, -34.59), (-58.5 + i * 0.01, -34.59)]) for i in range(3)]
    gpd.GeoDataFrame({"lote": ["L1", "L2", "L3"],
                      "fecha": [dt.date(2024, 1, 15), dt.date(2024, 2, 1), dt.date(2024, 3, 10)],
                      "ha": [12.5, float("nan"), 7.25]},
                     geometry=polis, crs="EPSG:4326").to_file(p, engine="pyogrio")
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
    from app.ui import workers
    from app.ui.workers import SenalesConteo

    class WorkerConteoInerte(QRunnable):
        def __init__(self, receta, generacion, umbral, project_id=None):
            super().__init__()
            self.receta, self.generacion, self.umbral = receta, generacion, umbral
            self.senales = SenalesConteo()

        def run(self):
            pass

    monkeypatch.setattr(ventana_principal, "WorkerConteo", WorkerConteoInerte)

    # Mismo criterio para el preview (F7): sin esto, tests que llaman cargar_receta disparan
    # un WorkerPreview real (GEE) cuyo dialogo de error abre en el teardown y crashea en
    # Windows (heap 0xc0000374). Subclase inerte: `isinstance(w, workers.WorkerPreview)` sigue
    # valiendo y `workers.WorkerPreview.run` real queda disponible para los tests del worker.
    class WorkerPreviewInerte(workers.WorkerPreview):
        def run(self):
            pass

    monkeypatch.setattr(ventana_principal, "WorkerPreview", WorkerPreviewInerte)

    # F8: la serie temporal tampoco debe tocar GEE desde un test de ventana.
    class WorkerSerieTemporalInerte(workers.WorkerSerieTemporal):
        def run(self):
            pass

    monkeypatch.setattr(ventana_principal, "WorkerSerieTemporal", WorkerSerieTemporalInerte)


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
