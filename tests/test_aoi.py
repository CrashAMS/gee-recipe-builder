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
