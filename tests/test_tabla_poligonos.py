"""F9 — dominio de la tabla por polígono (columnas, filas, CSV) y su ejecutor con fake de ee."""
import pytest

from app.dominio import tabla_poligonos as tp
from app.dominio.errores import ColumnaTablaEnConflicto, TablaSinPoligonos
from app.dominio.serie_csv import escribir_csv
from app.gee import ejecutor
from app.gee.ejecutor import SolicitudEjecucion

FC = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": None, "properties": {"lote": "Ñandú", "ha": 1.5}},
    {"type": "Feature", "geometry": None, "properties": {"lote": "L2", "zona": "N"}},
]}


def test_columnas_un_indice():
    assert tp.columnas_para(FC, ["NDVI"]) == [
        "lote", "ha", "zona", "NDVI_mean", "NDVI_min", "NDVI_max", "NDVI_std", "NDVI_n"]


def test_columnas_dos_indices_en_orden_de_receta():
    cols = tp.columnas_para(FC, ["EVI", "NDVI"])
    assert cols[3:] == [f"{i}_{s}" for i in ("EVI", "NDVI") for s in ("mean", "min", "max", "std", "n")]


def test_filas_conservan_properties_y_stats_renombradas():
    cols = tp.columnas_salida(["lote"], ["NDVI"])
    info = {"features": [{"properties": {"lote": "A", "NDVI_mean": 0.5, "NDVI_min": 0.1,
                                          "NDVI_max": 0.9, "NDVI_std": 0.2, "NDVI_n": 40}}]}
    assert tp.filas_desde_info(info, cols) == [["A", 0.5, 0.1, 0.9, 0.2, 40]]


def test_stat_nula_o_ausente_es_celda_vacia():
    cols = tp.columnas_salida(["lote"], ["NDVI"])
    info = {"features": [{"properties": {"lote": "A", "NDVI_n": 0, "NDVI_mean": None}}]}
    texto = tp.filas_a_texto(tp.filas_desde_info(info, cols), cols)
    assert texto.splitlines()[1] == "A,,,,,0"


def test_colision_con_columna_de_estadistica_levanta():
    with pytest.raises(ColumnaTablaEnConflicto, match="NDVI_mean"):
        tp.columnas_salida(["lote", "NDVI_mean"], ["NDVI"])


def test_csv_ida_y_vuelta_con_acentos(tmp_path):
    import csv
    cols = tp.columnas_para(FC, ["NDVI"])
    texto = tp.filas_a_texto([["Ñandú", 1.5, None, 0.5, 0.1, 0.9, 0.2, 40]], cols)
    ruta = tmp_path / "t.csv"
    escribir_csv(ruta, texto)
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh))
    assert filas[0] == cols and filas[1][:3] == ["Ñandú", "1.5", ""]


@pytest.mark.parametrize("n,local", [(500, True), (501, False)])
def test_es_local_en_el_umbral(n, local):
    fc = {"type": "FeatureCollection", "features": [{}] * n}
    assert tp.es_local(fc) is local


def test_exigir_poligonos():
    with pytest.raises(TablaSinPoligonos):
        tp.exigir_poligonos(None)
    with pytest.raises(TablaSinPoligonos):
        tp.exigir_poligonos({"type": "FeatureCollection", "features": []})
    assert tp.exigir_poligonos(FC) is FC


# ---- ejecutor con fake de ee ----

class _Reducer:
    def __init__(self, nombre="mean", cadena=None):
        self.cadena = cadena or [nombre]
        self.salidas = None

    def combine(self, reducer2, outputPrefix=None, sharedInputs=False):
        assert sharedInputs is True
        return _Reducer(cadena=self.cadena + reducer2.cadena)

    def setOutputs(self, nombres):
        r = _Reducer(cadena=self.cadena)
        r.salidas = list(nombres)
        return r


class _FakeReducer:
    def __getattr__(self, nombre):
        return lambda: _Reducer(nombre)


class _FC:
    def __init__(self, log, pasos=()):
        self.log, self.pasos = log, tuple(pasos)

    def select(self, *a):
        self.log.append(("select", a))
        return _FC(self.log, self.pasos + (("select", a),))


class _Imagen:
    def __init__(self, log, banda=None):
        self.log, self.banda = log, banda

    def select(self, banda):
        return _Imagen(self.log, banda)

    def reduceRegions(self, collection, reducer, scale):
        self.log.append(("reduceRegions", self.banda, reducer.cadena, reducer.salidas, scale,
                         collection))
        return _FC(self.log, collection.pasos + (("reduce", self.banda),))


class _FakeEE:
    Reducer = _FakeReducer()

    def __init__(self):
        self.log = []

    def FeatureCollection(self, fc):
        self.log.append(("FeatureCollection", fc))
        return _FC(self.log)


def _sol(**kw):
    base = dict(collection_id="COPERNICUS/S2_SR_HARMONIZED", aoi="AOI", fecha_inicio="2024-01-01",
                fecha_fin="2024-02-01", indices=["NDVI", "EVI"], mascara_nubes=False,
                reduccion="median", scale=30)
    base.update(kw)
    return SolicitudEjecucion(**base)


def test_ejecutor_un_reduce_regions_por_indice_con_scale_y_select_sin_geometria(monkeypatch):
    fake = _FakeEE()
    monkeypatch.setattr(ejecutor, "ee", fake)
    monkeypatch.setattr(ejecutor, "construir_imagen", lambda sol: _Imagen(fake.log))
    out = ejecutor.tabla_poligonos(_sol(), FC)
    reduce = [e for e in fake.log if e[0] == "reduceRegions"]
    assert [(e[1], e[4]) for e in reduce] == [("NDVI", 30), ("EVI", 30)]
    assert reduce[0][2] == ["mean", "min", "max", "stdDev", "count"]
    assert reduce[1][3] == ["EVI_mean", "EVI_min", "EVI_max", "EVI_std", "EVI_n"]
    assert reduce[1][5].pasos == (("reduce", "NDVI"),)          # encadenado: la salida de uno entra al otro
    cols = tp.columnas_para(FC, ["NDVI", "EVI"])
    assert out.pasos[-1] == ("select", (cols, None, False))


def test_ejecutor_colision_levanta_antes_de_tocar_ee(monkeypatch):
    fake = _FakeEE()
    monkeypatch.setattr(ejecutor, "ee", fake)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {"EVI_n": 1}}]}
    with pytest.raises(ColumnaTablaEnConflicto):
        ejecutor.tabla_poligonos(_sol(), fc)
    assert fake.log == []
