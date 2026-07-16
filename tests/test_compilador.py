import pytest
from app.dominio.catalogo.sensores import PERFILES, sensores_con_mascara
from app.dominio.receta import Receta, Composicion, Salida
from app.dominio.compilador import dialecto_python, dialecto_js
from app.dominio.compilador.dialecto_js import MASCARA_JS, ESCALA_JS
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


# --- FIX-1/FIX-2 (paridad dura JS): cobertura de escalado + máscara para las
# familias agregadas (Landsat C1 SR, Landsat C2 L2, MODIS GA/Q1/GQ). ---

def test_golden_ndvi_landsat_c1sr_l8():
    # LC08 C1 SR: máscara "L8" (pixel_qa bit5+bit3), sin escala (ee_extra no
    # tiene entrada de scale/offset para C1 SR -> scaleAndOffset() es no-op).
    r = _receta(sensor="LANDSAT/LC08/C01/T1_SR", indice="NDVI")
    check_golden("ndvi_l8c1sr_descarga.js", dialecto_js.compilar(r))


def test_golden_ndvi_landsat_c1sr_l457():
    # LE07 C1 SR: máscara "L457" (bit5 AND bit7, OR bit3, + mask() propia).
    r = _receta(sensor="LANDSAT/LE07/C01/T1_SR", indice="NDVI")
    check_golden("ndvi_l7c1sr_descarga.js", dialecto_js.compilar(r))


def test_golden_ndvi_landsat_c2_l2():
    # LC08 C2 L2: máscara QA_PIXEL bits 2/3/4 + escala SR_B*/ST_B10.
    r = _receta(sensor="LANDSAT/LC08/C02/T1_L2", indice="NDVI")
    check_golden("ndvi_l8c2l2_descarga.js", dialecto_js.compilar(r))


def test_golden_ndvi_modis_ga():
    # MOD09GA: máscara "state_1km" + escala sur_refl_b*.
    r = _receta(sensor="MODIS/061/MOD09GA", indice="NDVI")
    check_golden("ndvi_modisga_descarga.js", dialecto_js.compilar(r))


def test_golden_ndvi_modis_q1():
    # MOD09Q1: misma lógica de bits que GA pero banda "State".
    r = _receta(sensor="MODIS/061/MOD09Q1", indice="NDVI")
    check_golden("ndvi_modisq1_descarga.js", dialecto_js.compilar(r))


def test_golden_ndvi_modis_gq_sin_mascara():
    # MOD09GQ no soporta máscara (fuera de _CON_MASCARA) pero sí escala.
    r = _receta(sensor="MODIS/061/MOD09GQ", indice="NDVI", mascara_nubes=False)
    check_golden("ndvi_modisgq_sinmascara.js", dialecto_js.compilar(r))


def test_mascara_js_cubre_todos_los_sensores_con_mascara():
    # Todo collection ID con soporta_mascara=True (32) tiene entrada en MASCARA_JS.
    assert sensores_con_mascara() <= MASCARA_JS.keys()
    assert len(sensores_con_mascara()) == 32


def test_escala_js_tiene_decision_explicita_para_todo_el_catalogo():
    # Todo ID del catálogo (40) tiene una decisión de escala explícita: nombre
    # de función JS, o `None` transcripto a mano ("sin escala", ver docstring).
    assert set(ESCALA_JS.keys()) == set(PERFILES.keys())
