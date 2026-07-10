"""Tests para el mapa interactivo — F3b (piezas sin display)."""
import json
from urllib.request import urlopen

from app.mapa.bridge import MapBridge
from app.mapa.preview import VIS_PARAMS_DEFAULT, PreviewWorker
from app.mapa.servidor import ServidorMapa


class _ResultadoFake:
    def __init__(self, d):
        self._d = d

    def getInfo(self):
        return self._d


class _ImagenFake:
    """Sustituto de ee.Image para testear el auto-stretch sin tocar GEE."""

    def __init__(self, stats, rompe=False):
        self._stats = stats
        self._rompe = rompe

    def geometry(self):
        return None

    def reduceRegion(self, **kwargs):
        if self._rompe:
            raise RuntimeError("boom")
        return _ResultadoFake(self._stats)


def test_servidor_sirve_archivo(tmp_path):
    (tmp_path / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    srv = ServidorMapa(tmp_path)
    srv.iniciar()
    try:
        resp = urlopen(f"http://127.0.0.1:{srv.puerto}/index.html", timeout=5)
        assert resp.status == 200
        assert b"ok" in resp.read()
    finally:
        srv.detener()


def test_servidor_es_local_y_puerto_valido(tmp_path):
    srv = ServidorMapa(tmp_path)
    srv.iniciar()
    try:
        assert srv._httpd.server_address[0] == "127.0.0.1"
        assert srv.puerto > 0
    finally:
        srv.detener()


def test_bridge_cachea_y_emite_geometria():
    bridge = MapBridge()
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    recibidas = []
    bridge.aoi_recibida.connect(recibidas.append)
    bridge.polygon_drawn(json.dumps(geom))
    assert bridge.ultima_geometria == geom
    assert recibidas == [geom]


def test_bridge_ignora_json_malformado():
    bridge = MapBridge()
    bridge.polygon_drawn("no es json {")
    assert bridge.ultima_geometria is None


def test_bridge_borra_aoi():
    bridge = MapBridge()
    bridge.polygon_drawn(json.dumps({"type": "Polygon", "coordinates": [[[0, 0]]]}))
    bridge.aoi_borrada()
    assert bridge.ultima_geometria is None


def _mock_reducer(monkeypatch):
    # ee.Reducer.minMax() exige ee.Initialize(); en tests offline lo neutralizamos
    # (el _ImagenFake.reduceRegion ignora el reducer igual).
    import ee
    monkeypatch.setattr(ee.Reducer, "minMax", staticmethod(lambda: None), raising=False)


def test_preview_stretch_aplica_rango_real(monkeypatch):
    # El auto-stretch estira min/max al rango real del índice (rampa visible).
    _mock_reducer(monkeypatch)
    w = PreviewWorker(lambda: None, auto_stretch=True)
    w._estirar_al_rango_real(_ImagenFake({"NDVI_min": 0.16, "NDVI_max": 0.34}))
    assert w._vis["min"] == 0.16
    assert w._vis["max"] == 0.34
    assert w._vis["palette"] == VIS_PARAMS_DEFAULT["palette"]  # paleta intacta


def test_preview_stretch_falla_cae_al_default(monkeypatch):
    # Si reduceRegion rompe, el vis queda como estaba (fallback silencioso, no rompe preview).
    _mock_reducer(monkeypatch)
    w = PreviewWorker(lambda: None)
    w._estirar_al_rango_real(_ImagenFake(None, rompe=True))
    assert w._vis["min"] == 0 and w._vis["max"] == 1


def test_preview_stretch_rango_degenerado_no_estira(monkeypatch):
    # min == max (imagen constante) → no se estira (evita min==max en la paleta).
    _mock_reducer(monkeypatch)
    w = PreviewWorker(lambda: None)
    w._estirar_al_rango_real(_ImagenFake({"NDVI_min": 0.5, "NDVI_max": 0.5}))
    assert w._vis["min"] == 0 and w._vis["max"] == 1


def test_preview_sin_autostretch_mantiene_default():
    w = PreviewWorker(lambda: None, auto_stretch=False)
    assert w._vis == VIS_PARAMS_DEFAULT
