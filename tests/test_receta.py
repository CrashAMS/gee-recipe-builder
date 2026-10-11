"""Validación de Receta.max_nubes_pct (F4) e ida y vuelta JSON."""
import pytest

from app.dominio.receta import Receta, Composicion, Salida
from app.dominio.receta_json import a_json, desde_json

_AOI = {"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6],
        [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]}


def _receta(**kw):
    base = dict(sensor="COPERNICUS/S2_SR_HARMONIZED", indice="NDVI", geometria=_AOI,
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
