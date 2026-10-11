"""Tests para el mapa interactivo — F3b (piezas sin display)."""
import json
from urllib.request import urlopen

from app.mapa.bridge import MapBridge
from app.mapa.preview import (
    PALETAS, VIS_PARAMS_DEFAULT, PreviewResultado, estirar_vis_al_rango, paleta_por_dominio,
    url_tiles_para, vis_para_leyenda,
)
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


def test_widget_mapa_sin_webengine_da_mensaje_accionable(qtbot, monkeypatch):
    # Simula PySide6 >=6.12 (QtWebEngine fuera de Addons): el error dice qué instalar.
    import sys

    import pytest

    from app.mapa.widget_mapa import QtWebEngineNoDisponible, WidgetMapa

    monkeypatch.setitem(sys.modules, "PySide6.QtWebEngineWidgets", None)
    with pytest.raises(QtWebEngineNoDisponible, match=r"PySide6-Addons>=6\.7,<6\.12"):
        WidgetMapa()


def _mock_reducer(monkeypatch):
    # ee.Reducer.percentile() exige ee.Initialize(); en tests offline lo neutralizamos
    # (el _ImagenFake.reduceRegion ignora el reducer igual).
    import ee
    monkeypatch.setattr(ee.Reducer, "percentile", staticmethod(lambda *a, **k: None), raising=False)


def test_preview_stretch_aplica_percentiles_y_marca_estirado(monkeypatch):
    _mock_reducer(monkeypatch)
    vis, estirado = estirar_vis_al_rango(
        _ImagenFake({"NDVI_p2": 0.16, "NDVI_p98": 0.34}), VIS_PARAMS_DEFAULT)
    assert (vis["min"], vis["max"]) == (0.16, 0.34)
    assert estirado is True
    assert vis["palette"] == VIS_PARAMS_DEFAULT["palette"]  # paleta intacta


def test_preview_stretch_no_muta_el_vis_de_entrada(monkeypatch):
    _mock_reducer(monkeypatch)
    estirar_vis_al_rango(_ImagenFake({"NDVI_p2": 0.16, "NDVI_p98": 0.34}), VIS_PARAMS_DEFAULT)
    assert VIS_PARAMS_DEFAULT["min"] == 0 and VIS_PARAMS_DEFAULT["max"] == 1


def test_preview_stretch_falla_no_estirado_y_sin_mutar(monkeypatch):
    _mock_reducer(monkeypatch)
    vis, estirado = estirar_vis_al_rango(_ImagenFake(None, rompe=True), VIS_PARAMS_DEFAULT)
    assert (vis["min"], vis["max"]) == (0, 1)
    assert estirado is False
    assert VIS_PARAMS_DEFAULT["min"] == 0 and VIS_PARAMS_DEFAULT["max"] == 1


def test_preview_stretch_rango_degenerado_no_estirado(monkeypatch):
    _mock_reducer(monkeypatch)
    vis, estirado = estirar_vis_al_rango(
        _ImagenFake({"NDVI_p2": 0.5, "NDVI_p98": 0.5}), VIS_PARAMS_DEFAULT)
    assert (vis["min"], vis["max"]) == (0, 1)
    assert estirado is False


class _ImagenGetMapId(_ImagenFake):
    def __init__(self, stats):
        super().__init__(stats)
        self.vis_pedido = None

    def getMapId(self, vis):
        self.vis_pedido = vis

        class _Fetcher:
            url_format = "https://tiles/{z}/{x}/{y}"
        return {"tile_fetcher": _Fetcher()}


def _fake_ee_image(monkeypatch):
    import ee
    monkeypatch.setattr(ee, "Image", lambda x: x)


def test_url_tiles_para_devuelve_preview_resultado(monkeypatch):
    _mock_reducer(monkeypatch)
    _fake_ee_image(monkeypatch)
    img = _ImagenGetMapId({"NDVI_p2": 0.1, "NDVI_p98": 0.9})
    res = url_tiles_para(img)
    assert isinstance(res, PreviewResultado)
    assert res.url == "https://tiles/{z}/{x}/{y}"
    assert (res.vis["min"], res.vis["max"]) == (0.1, 0.9)
    assert res.estirado is True
    assert img.vis_pedido == res.vis


def test_url_tiles_para_override_respeta_min_max_y_no_estira(monkeypatch):
    _fake_ee_image(monkeypatch)
    img = _ImagenGetMapId({"NDVI_p2": 0.1, "NDVI_p98": 0.9})   # no debe leerse
    res = url_tiles_para(img, {"min": -1, "max": 2, "palette": ["000000", "ffffff"]},
                         auto_stretch=False)
    assert (res.vis["min"], res.vis["max"]) == (-1, 2)
    assert res.estirado is False
    assert img.vis_pedido["min"] == -1


def test_paleta_por_dominio_conocido_y_desconocido():
    assert paleta_por_dominio("vegetation") == "vegetación"
    assert paleta_por_dominio("water") == "agua"
    assert paleta_por_dominio("urban") == "genérica"
    assert paleta_por_dominio("kernel") == "genérica"
    assert paleta_por_dominio("inventado") == "genérica"
    assert paleta_por_dominio(None) == "genérica"
    assert set(PALETAS) >= {"vegetación", "agua", "quemado", "suelo", "nieve", "genérica"}


def test_vis_para_leyenda_antepone_hash_a_hex_y_deja_nombres_css():
    vis = {"min": 0, "max": 1, "palette": ["white", "CE7E45", "#112233", "abc"]}
    out = vis_para_leyenda(vis)
    assert out["palette"] == ["white", "#CE7E45", "#112233", "#abc"]
    assert vis["palette"][1] == "CE7E45"   # no muta la entrada
