import json
import pytest

from app.dominio.errores import RecetaJSONInvalida
from app.dominio.receta import Receta, Composicion, Salida
from app.dominio.receta_json import a_json, desde_json

GEOM = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def _receta(**kw):
    base = dict(sensor="COPERNICUS/S2_SR", indices=["NDVI"], geometria=GEOM,
                fecha_inicio="2024-01-01", fecha_fin="2024-02-01", mascara_nubes=True,
                composicion="median", salida="descarga", escala=20, parametros={"g": 2.5})
    base.update(kw)
    return Receta(**base)


@pytest.mark.parametrize("descriptor", [
    {"tipo": "shapefile", "ruta": "C:/x/zona.shp"},
    {"tipo": "bbox", "oeste": -59.0, "sur": -35.0, "este": -58.0, "norte": -34.0},
    {"tipo": "geojson-dict", "geojson": GEOM},
    None,
])
def test_ida_y_vuelta(descriptor):
    r = _receta()
    cargada = desde_json(a_json(r, descriptor))
    assert cargada.receta == r
    assert cargada.descriptor_aoi == descriptor


def test_enums_serializados_como_string():
    datos = json.loads(a_json(_receta()))
    assert datos["version"] == 1
    assert datos["receta"]["composicion"] == "median"
    assert datos["receta"]["salida"] == "descarga"
    assert desde_json(a_json(_receta())).receta.composicion is Composicion.MEDIANA


def test_serializa_todos_los_campos_de_receta():
    from dataclasses import fields
    assert set(json.loads(a_json(_receta()))["receta"]) == {f.name for f in fields(Receta)}


@pytest.mark.parametrize("version", [None, 2, "1", True])
def test_version_invalida(version):
    d = json.loads(a_json(_receta()))
    if version is None:
        del d["version"]
    else:
        d["version"] = version
    with pytest.raises(RecetaJSONInvalida):
        desde_json(json.dumps(d))


def test_version_mas_nueva_lo_dice():
    d = json.loads(a_json(_receta()))
    d["version"] = 2
    with pytest.raises(RecetaJSONInvalida, match="más nueva"):
        desde_json(json.dumps(d))


@pytest.mark.parametrize("geom", [None, {"coordinates": []}, "x"])
def test_geometria_faltante_o_sin_type(geom):
    d = json.loads(a_json(_receta()))
    if geom is None:
        del d["receta"]["geometria"]
    else:
        d["receta"]["geometria"] = geom
    with pytest.raises(RecetaJSONInvalida, match="geometr"):
        desde_json(json.dumps(d))


def test_json_mal_formado():
    with pytest.raises(RecetaJSONInvalida, match="JSON"):
        desde_json("{no es json")


def test_campo_obligatorio_faltante_y_enum_invalido():
    d = json.loads(a_json(_receta()))
    del d["receta"]["indices"]
    with pytest.raises(RecetaJSONInvalida, match="indices"):
        desde_json(json.dumps(d))
    d = json.loads(a_json(_receta()))
    d["receta"]["salida"] = "nube"
    with pytest.raises(RecetaJSONInvalida):
        desde_json(json.dumps(d))


def test_campo_extra_ignorado_y_escala_faltante_usa_default():
    d = json.loads(a_json(_receta()))
    d["receta"]["campo_futuro"] = 1
    d["extra"] = 2
    del d["receta"]["escala"]
    r = desde_json(json.dumps(d)).receta
    assert r.escala == 10 and r.salida is Salida.DESCARGA


@pytest.mark.parametrize("campo,valor", [
    ("escala", "20"), ("parametros", None), ("mascara_nubes", "si"),
    ("fecha_inicio", "ayer"), ("sensor", 3),
])
def test_tipos_invalidos_son_receta_invalida(campo, valor):
    d = json.loads(a_json(_receta()))
    d["receta"][campo] = valor
    with pytest.raises(RecetaJSONInvalida):
        desde_json(json.dumps(d))


# --- F6b: indices / producto / periodo y JSON legado ---

def test_ida_y_vuelta_tres_indices_serie_mensual():
    r = _receta(indices=["NDVI", "EVI", "NDWI"], producto="serie_temporal", periodo="mensual")
    d = json.loads(a_json(r))
    assert d["version"] == 1 and "indice" not in d["receta"]
    assert d["receta"]["indices"] == ["NDVI", "EVI", "NDWI"]
    assert d["receta"]["producto"] == "serie_temporal" and d["receta"]["periodo"] == "mensual"
    assert desde_json(a_json(r)).receta == r


def test_json_legado_con_indice_carga():
    d = json.loads(a_json(_receta()))
    del d["receta"]["indices"], d["receta"]["producto"], d["receta"]["periodo"]
    d["receta"]["indice"] = "EVI"
    r = desde_json(json.dumps(d)).receta
    assert r.indices == ["EVI"] and r.producto.value == "imagen" and r.periodo is None


def test_json_legado_coherente_con_indices_carga():
    d = json.loads(a_json(_receta(indices=["NDVI", "EVI"])))
    d["receta"]["indice"] = "NDVI"
    assert desde_json(json.dumps(d)).receta.indices == ["NDVI", "EVI"]


@pytest.mark.parametrize("mutar", [
    lambda r: r.update(indice="EVI"),          # incoherente con indices=["NDVI"]
    lambda r: r.update(indices=[]),
    lambda r: r.update(indices="NDVI"),
    lambda r: r.update(indices=["NDVI", 1]),
    lambda r: r.update(producto=3),
    lambda r: r.update(periodo=16),
    lambda r: r.update(indices=["NDVI", "NDVI"]),
], ids=["incoherente", "vacia", "no_lista", "no_str", "producto", "periodo", "duplicados"])
def test_indices_producto_periodo_invalidos(mutar):
    d = json.loads(a_json(_receta()))
    mutar(d["receta"])
    with pytest.raises(RecetaJSONInvalida):
        desde_json(json.dumps(d))
