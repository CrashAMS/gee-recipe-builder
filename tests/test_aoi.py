import pytest
from app.dominio.aoi import desde_bbox, desde_geojson_dict, desde_archivo, desde_descriptor
from app.dominio.errores import FuenteAOIError


def test_bbox_a_polygon():
    g = desde_bbox(-58.5, -34.6, -58.4, -34.5)
    assert g["type"] == "Polygon"
    assert g["coordinates"][0][0] == g["coordinates"][0][-1]   # anillo cerrado


def test_geojson_feature_extrae_geometria():
    feat = {"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
    assert desde_geojson_dict(feat)["type"] == "Polygon"


def test_geojson_featurecollection_disuelve_a_una():
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon",
         "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon",
         "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 2]]]}}]}
    assert desde_geojson_dict(fc)["type"] in {"MultiPolygon", "GeometryCollection"}


def test_geojson_tipo_no_reconocido_levanta():
    with pytest.raises(FuenteAOIError):
        desde_geojson_dict({"type": "Topology"})


def test_shp_valido_a_4326(shp_valido):
    assert desde_archivo(shp_valido)["type"] in {"Polygon", "MultiPolygon"}


def test_shp_sin_prj_levanta(shp_sin_prj):
    with pytest.raises(FuenteAOIError):
        desde_archivo(shp_sin_prj)


def test_descriptor_bbox():
    d = {"tipo": "bbox", "oeste": -58.5, "sur": -34.6, "este": -58.4, "norte": -34.5}
    assert desde_descriptor(d)["type"] == "Polygon"


def test_descriptor_geojson_dict():
    d = {"tipo": "geojson-dict", "geojson": {"type": "Polygon",
         "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
    assert desde_descriptor(d)["type"] == "Polygon"


def test_descriptor_tipo_desconocido_levanta():
    with pytest.raises(FuenteAOIError):
        desde_descriptor({"tipo": "kml"})


def test_bbox_de_polygon_y_multipolygon():
    from app.dominio.aoi import bbox_de
    assert bbox_de(desde_bbox(-59.0, -35.0, -58.0, -34.0)) == (-59.0, -35.0, -58.0, -34.0)
    multi = {"type": "MultiPolygon", "coordinates": [
        [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        [[[5, 5], [6, 5], [6, 7], [5, 7], [5, 5]]]]}
    assert bbox_de(multi) == (0.0, 0.0, 6.0, 7.0)


# --- F6b: AOI con features (desde_archivo_features) ---

import json  # noqa: E402

import geopandas as gpd  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from app.dominio.aoi import FuenteAOI, desde_archivo_features  # noqa: E402


def test_features_conserva_n_y_properties(shp_lotes):
    fc = desde_archivo_features(shp_lotes)
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 3
    props = [f["properties"] for f in fc["features"]]
    assert [p["lote"] for p in props] == ["L1", "L2", "L3"]
    assert props[0]["ha"] == 12.5 and props[1]["ha"] is None
    assert props[0]["fecha"].startswith("2024-01-15")
    assert all(f["geometry"]["type"] == "Polygon" for f in fc["features"])
    assert FuenteAOI.desde_archivo_features is desde_archivo_features


def test_features_properties_serializables_a_json(shp_lotes):
    texto = json.dumps(desde_archivo_features(shp_lotes), allow_nan=False)
    assert "NaN" not in texto


def test_features_no_disuelve_ni_toca_camino_actual(shp_lotes):
    from app.dominio.aoi import desde_archivo
    assert desde_archivo(shp_lotes)["type"] in {"Polygon", "MultiPolygon"}
    assert len(desde_archivo_features(shp_lotes)["features"]) == 3


def test_features_501_se_leen_sin_tope(tmp_path):
    p = tmp_path / "muchos.shp"
    polis = [Polygon([(i * 0.001, 0), (i * 0.001 + 0.0005, 0), (i * 0.001 + 0.0005, 0.0005),
                      (i * 0.001, 0.0005)]) for i in range(501)]
    gpd.GeoDataFrame({"id": list(range(501))}, geometry=polis, crs="EPSG:4326").to_file(p, engine="pyogrio")
    fc = desde_archivo_features(p)
    assert len(fc["features"]) == 501 and fc["features"][-1]["properties"]["id"] == 500


def test_features_reproyecta_a_4326(tmp_path):
    p = tmp_path / "utm.shp"
    gpd.GeoDataFrame({"lote": ["A"]}, geometry=[Polygon([(500000, 6170000), (501000, 6170000),
                     (501000, 6171000), (500000, 6171000)])], crs="EPSG:32721").to_file(p, engine="pyogrio")
    x, y = desde_archivo_features(p)["features"][0]["geometry"]["coordinates"][0][0]
    assert -180 <= x <= 180 and -90 <= y <= 90


def test_features_sin_crs_levanta(shp_sin_prj):
    with pytest.raises(FuenteAOIError, match="CRS"):
        desde_archivo_features(shp_sin_prj)


def test_features_vacio_levanta(tmp_path):
    p = tmp_path / "vacio.shp"
    gpd.GeoDataFrame({"lote": []}, geometry=[], crs="EPSG:4326").to_file(p, engine="pyogrio")
    with pytest.raises(FuenteAOIError):
        desde_archivo_features(p)


def test_features_geometria_nula_levanta(tmp_path):
    p = tmp_path / "nula.shp"
    gpd.GeoDataFrame({"lote": ["A", "B"]}, geometry=[Polygon([(0, 0), (1, 0), (1, 1)]), None],
                     crs="EPSG:4326").to_file(p, engine="pyogrio")
    with pytest.raises(FuenteAOIError, match="sin geometría"):
        desde_archivo_features(p)


def test_valor_json_normaliza_tipos_no_estandar():
    import datetime as dt
    import numpy as np
    import pandas as pd
    from app.dominio.aoi import _valor_json
    assert _valor_json(pd.NA) is None and _valor_json(pd.NaT) is None
    assert _valor_json(float("inf")) is None and _valor_json(np.float64("nan")) is None
    assert _valor_json(np.int64(3)) == 3 and isinstance(_valor_json(np.int64(3)), int)
    assert _valor_json(np.datetime64("2024-01-15")).startswith("2024-01-15")
    assert _valor_json(pd.Timestamp("2024-02-01")).startswith("2024-02-01")
    assert _valor_json(dt.date(2024, 3, 10)) == "2024-03-10"
