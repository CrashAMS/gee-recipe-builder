import pytest
from app.dominio.receta import Receta, Composicion, Salida
from app.dominio.compilador import dialecto_python, dialecto_js
from app.dominio.errores import MascaraNoDisponibleJS
from tests.conftest import check_golden

_AOI = {"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6],
        [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]}


def _receta(**kw):
    base = dict(sensor="COPERNICUS/S2_SR_HARMONIZED", indice="NDVI", geometria=_AOI,
                fecha_inicio="2023-01-01", fecha_fin="2023-12-31", mascara_nubes=True,
                composicion=Composicion.MEDIANA, salida=Salida.DESCARGA, escala=10)
    base.update(kw)
    return Receta(**base)


def test_golden_ndvi_s2_descarga():
    r = _receta()
    check_golden("ndvi_s2_descarga.py", dialecto_python.compilar(r))
    check_golden("ndvi_s2_descarga.js", dialecto_js.compilar(r))


def test_golden_evi_s2_drive_con_params():
    r = _receta(indice="EVI", salida=Salida.DRIVE, parametros={"g": 2.5, "L": 1.0})
    check_golden("evi_s2_drive.py", dialecto_python.compilar(r))
    check_golden("evi_s2_drive.js", dialecto_js.compilar(r))


def test_golden_kndvi_s2_preview():
    r = _receta(indice="kNDVI", salida=Salida.PREVIEW, mascara_nubes=False)
    check_golden("kndvi_s2_preview.py", dialecto_python.compilar(r))
    check_golden("kndvi_s2_preview.js", dialecto_js.compilar(r))


def test_golden_sin_mascara():
    r = _receta(mascara_nubes=False)
    check_golden("ndvi_s2_sinmascara.py", dialecto_python.compilar(r))


def test_js_mascara_no_disponible_levanta():
    # sensor sin snippet en MASCARA_JS + máscara pedida -> error explícito, no silencioso
    r = _receta(sensor="MODIS/061/MCD43A4", indice="NDVI", mascara_nubes=True)
    with pytest.raises(MascaraNoDisponibleJS):
        dialecto_js.compilar(r)
