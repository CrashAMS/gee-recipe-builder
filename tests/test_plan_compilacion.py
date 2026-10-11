"""F6a — plan neutral de compilación y paridad estructural JS/Python."""
import pytest
from app.dominio.receta import Salida as DestinoSalida
from app.dominio.compilador import dialecto_js, dialecto_python
from app.dominio.compilador.dialecto_js import ESCALA_JS
from app.dominio.compilador.plan import (
    FiltroNubes, Indices, Salida, TipoPaso, construir_plan, tipos_renderizados)
from app.dominio.errores import FiltroNubesNoDisponible, MascaraNoDisponibleJS
from tests.test_compilador import _receta

T = TipoPaso


def test_orden_de_pasos_receta_base():
    assert construir_plan(_receta()).tipos == (
        T.FUENTE, T.FILTRO_FECHAS, T.MASCARA, T.ESCALA, T.INDICES, T.REDUCTOR, T.SALIDA)


def test_filtro_nubes_solo_con_umbral():
    assert construir_plan(_receta()).paso(T.FILTRO_NUBES) is None
    plan = construir_plan(_receta(max_nubes_pct=20))
    assert plan.paso(T.FILTRO_NUBES) == FiltroNubes("CLOUDY_PIXEL_PERCENTAGE", 20)
    assert plan.tipos.index(T.FILTRO_NUBES) == plan.tipos.index(T.FILTRO_FECHAS) + 1


def test_sin_mascara_no_hay_paso_mascara_pero_si_escala():
    plan = construir_plan(_receta(mascara_nubes=False))
    assert T.MASCARA not in plan.tipos
    assert T.ESCALA in plan.tipos


def test_indices_y_bandas_de_salida():
    r = _receta(indice="EVI", parametros={"g": 2.5, "L": 1.0}, salida=DestinoSalida.DRIVE)
    plan = construir_plan(r)
    ind, sal = plan.paso(T.INDICES), plan.paso(T.SALIDA)
    assert ind == Indices(("EVI",), (("L", 1.0), ("g", 2.5)))
    assert sal == Salida(DestinoSalida.DRIVE, 10, ("EVI",), "EVI")
    assert sal.bandas == ind.nombres == (r.indice,)


def test_plan_hashable_e_igual_para_recetas_iguales():
    a, b = construir_plan(_receta(max_nubes_pct=20)), construir_plan(_receta(max_nubes_pct=20))
    assert a == b and hash(a) == hash(b)
    assert len({a, b, construir_plan(_receta())}) == 2


# Las 12 recetas de los goldens actuales (tests/test_compilador.py).
_RECETAS_GOLDEN = {
    "s2_descarga": dict(),
    "s2_drive": dict(indice="EVI", salida=DestinoSalida.DRIVE, parametros={"g": 2.5, "L": 1.0}),
    "s2_preview": dict(indice="kNDVI", salida=DestinoSalida.PREVIEW, mascara_nubes=False),
    "s2_sinmascara": dict(mascara_nubes=False),
    "s2_nubes": dict(max_nubes_pct=20),
    "l8c1sr": dict(sensor="LANDSAT/LC08/C01/T1_SR"),
    "l7c1sr": dict(sensor="LANDSAT/LE07/C01/T1_SR"),
    "l8c2l2": dict(sensor="LANDSAT/LC08/C02/T1_L2"),
    "l8c2l2_nubes": dict(sensor="LANDSAT/LC08/C02/T1_L2", max_nubes_pct=30),
    "modis_ga": dict(sensor="MODIS/061/MOD09GA"),
    "modis_q1": dict(sensor="MODIS/061/MOD09Q1"),
    "modis_gq_sinmascara": dict(sensor="MODIS/061/MOD09GQ", mascara_nubes=False),
}


@pytest.mark.parametrize("kw", _RECETAS_GOLDEN.values(), ids=_RECETAS_GOLDEN.keys())
def test_paridad_tipos_renderizados_js_python_plan(kw):
    plan = construir_plan(_receta(**kw))
    js = tipos_renderizados(dialecto_js.segmentos(plan))
    py = tipos_renderizados(dialecto_python.segmentos(plan))
    assert js == py == plan.tipos
    # Todo segmento tipado emite texto, salvo JS `Escala` sin función (ESCALA_JS[id] is None).
    for d in (dialecto_js, dialecto_python):
        for tipos, lineas in d.segmentos(plan):
            assert lineas or (d is dialecto_js and tipos == (T.ESCALA,)), (d.__name__, tipos)


def test_js_escala_sin_funcion_sigue_presente_como_tipo():
    sensor = "LANDSAT/LC08/C01/T1_SR"
    assert ESCALA_JS[sensor] is None
    segs = dialecto_js.segmentos(construir_plan(_receta(sensor=sensor)))
    assert ((T.ESCALA,), []) in segs


def test_modis_con_umbral_falla_en_el_plan():
    with pytest.raises(FiltroNubesNoDisponible):
        construir_plan(_receta(sensor="MODIS/061/MOD09GA", max_nubes_pct=20))


def test_receta_doblemente_invalida_levanta_filtro_nubes_en_js():
    # MCD43A4: sin snippet en MASCARA_JS y sin propiedad de nubes (decisión 5 de F6a).
    r = _receta(sensor="MODIS/061/MCD43A4", max_nubes_pct=20)
    with pytest.raises(FiltroNubesNoDisponible):
        dialecto_js.compilar(r)
    with pytest.raises(MascaraNoDisponibleJS):
        dialecto_js.compilar(_receta(sensor="MODIS/061/MCD43A4"))
