"""Validación de Receta.max_nubes_pct (F4) e ida y vuelta JSON."""
import pytest

from app.dominio.receta import Receta, Composicion, Salida
from app.dominio.receta_json import a_json, desde_json

_AOI = {"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6],
        [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]}


def _receta(**kw):
    base = dict(sensor="COPERNICUS/S2_SR_HARMONIZED", indices=["NDVI"], geometria=_AOI,
                fecha_inicio="2023-01-01", fecha_fin="2023-12-31", mascara_nubes=True,
                composicion=Composicion.MEDIANA, salida=Salida.DESCARGA)
    base.update(kw)
    return Receta(**base)


def test_default_es_none():
    assert _receta().max_nubes_pct is None


@pytest.mark.parametrize("v", [0, 1, 50, 100])
def test_rango_valido(v):
    assert _receta(max_nubes_pct=v).max_nubes_pct == v


@pytest.mark.parametrize("v", [-1, 101, 20.5, "20", True])
def test_fuera_de_rango_o_tipo_invalido(v):
    with pytest.raises(ValueError, match="max_nubes_pct"):
        _receta(max_nubes_pct=v)


@pytest.mark.parametrize("v", [30, None])
def test_ida_y_vuelta_json_conserva_max_nubes(v):
    assert desde_json(a_json(_receta(max_nubes_pct=v))).receta.max_nubes_pct == v


def test_json_con_max_nubes_fuera_de_rango_es_invalido():
    import json
    from app.dominio.errores import RecetaJSONInvalida
    datos = json.loads(a_json(_receta()))
    datos["receta"]["max_nubes_pct"] = 150
    with pytest.raises(RecetaJSONInvalida):
        desde_json(json.dumps(datos))


# --- F6b: indices, producto, periodo ---

from app.dominio.receta import PERIODOS, Producto, nombre_bandas  # noqa: E402


def test_shim_indice_es_el_primero():
    r = _receta(indices=["EVI", "NDVI"])
    assert r.indice == r.indices[0] == "EVI"


@pytest.mark.parametrize("v,msg", [([], "vacía"), (["NDVI", "EVI", "NDVI"], "duplicados"),
                                   ("NDVI", "str suelto"), (["NDVI", 3], "str")])
def test_indices_invalidos(v, msg):
    with pytest.raises(ValueError, match=msg):
        _receta(indices=v)


def test_duplicados_no_se_reordenan_ni_deduplican():
    with pytest.raises(ValueError, match="NDVI"):
        _receta(indices=["NDVI", "NDVI"])


def test_tupla_se_normaliza_a_list_con_el_mismo_orden():
    r = _receta(indices=("NDWI", "NDVI", "EVI"))
    assert r.indices == ["NDWI", "NDVI", "EVI"] and isinstance(r.indices, list)


def test_producto_default_imagen_y_str_se_coacciona():
    assert _receta().producto is Producto.IMAGEN and _receta().periodo is None
    r = _receta(producto="serie_temporal", periodo="mensual")
    assert r.producto is Producto.SERIE_TEMPORAL
    assert _receta(producto="tabla_poligonos").producto is Producto.TABLA_POLIGONOS


@pytest.mark.parametrize("kw", [
    dict(producto="serie_temporal"),                      # serie sin periodo
    dict(producto="serie_temporal", periodo="semanal"),   # periodo desconocido
    dict(producto="imagen", periodo="mensual"),           # imagen con periodo
    dict(producto="tabla_poligonos", periodo="anual"),
])
def test_periodo_invalido(kw):
    with pytest.raises(ValueError, match="periodo"):
        _receta(**kw)


@pytest.mark.parametrize("p", PERIODOS)
def test_serie_acepta_todos_los_periodos(p):
    assert _receta(producto="serie_temporal", periodo=p).periodo == p


def test_nombre_bandas():
    assert nombre_bandas(["NDVI"]) == "NDVI"
    assert nombre_bandas(["NDVI", "EVI", "NDWI"]) == "NDVI-EVI-NDWI"
