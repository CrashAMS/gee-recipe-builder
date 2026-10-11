"""F4 - construir_imagen/contar_imagenes con fake de ee y WorkerConteo sincrono."""
import pytest

from app.gee import ejecutor
from app.gee.ejecutor import SolicitudEjecucion
from app.ui import workers


class _ColFake:
    def __init__(self, log):
        self.log = log

    def _paso(self, nombre, *args):
        self.log.append((nombre, args))
        return self

    def filterBounds(self, *a): return self._paso("filterBounds", *a)
    def filterDate(self, *a): return self._paso("filterDate", *a)
    def filter(self, *a): return self._paso("filter", *a)
    def maskClouds(self): return self._paso("maskClouds")
    def scaleAndOffset(self): return self._paso("scaleAndOffset")
    def spectralIndices(self, *a, **k): return self._paso("spectralIndices", *a)
    def median(self): return self._paso("median")
    def select(self, *a): return self._paso("select", *a)
    def clip(self, *a): return self._paso("clip", *a)
    def size(self): return ("size", len(self.log))


class _FakeEE:
    def __init__(self):
        self.log = []
        self.getinfo_llamadas = 0
        outer = self

        class ImageCollection(_ColFake):
            def __init__(s, cid):
                super().__init__(outer.log)
                outer.log.append(("ImageCollection", (cid,)))

        class Filter:
            @staticmethod
            def lt(prop, x): return ("lt", prop, x)

        class Dictionary:
            def __init__(s, d): s.d = d

            def getInfo(s):
                outer.getinfo_llamadas += 1
                return {k: 9 if k == "pocas" else 23 for k in s.d}

        self.ImageCollection, self.Filter, self.Dictionary = ImageCollection, Filter, Dictionary


@pytest.fixture
def fake_ee(monkeypatch):
    f = _FakeEE()
    monkeypatch.setattr(ejecutor, "ee", f)
    return f


def _sol(**kw):
    base = dict(collection_id="COPERNICUS/S2_SR_HARMONIZED", aoi="AOI", fecha_inicio="2024-01-01",
                fecha_fin="2024-02-01", indices=["NDVI"], mascara_nubes=True, reduccion="median",
                scale=20, propiedad_nubes="CLOUDY_PIXEL_PERCENTAGE", max_nubes_pct=20)
    base.update(kw)
    return SolicitudEjecucion(**base)


def test_construir_imagen_orden_filterdate_filter_maskclouds(fake_ee):
    ejecutor.construir_imagen(_sol())
    nombres = [n for n, _ in fake_ee.log]
    assert nombres.index("filterDate") < nombres.index("filter") < nombres.index("maskClouds")
    assert ("filter", (("lt", "CLOUDY_PIXEL_PERCENTAGE", 20),)) in fake_ee.log


def test_construir_imagen_sin_umbral_no_filtra(fake_ee):
    ejecutor.construir_imagen(_sol(max_nubes_pct=None))
    assert "filter" not in [n for n, _ in fake_ee.log]


def test_contar_imagenes_devuelve_tupla_con_un_solo_getinfo(fake_ee):
    assert ejecutor.contar_imagenes(_sol(), 20) == (23, 9)
    assert fake_ee.getinfo_llamadas == 1


def test_contar_imagenes_sin_propiedad_devuelve_none(fake_ee):
    assert ejecutor.contar_imagenes(_sol(propiedad_nubes=None), 20) == (23, None)
    assert fake_ee.getinfo_llamadas == 1


def test_worker_conteo_emite_el_token_recibido(monkeypatch):
    monkeypatch.setattr(workers.auth, "asegurar_sesion", lambda p=None: "proj")
    monkeypatch.setattr(workers, "solicitud_desde_receta", lambda r: "SOL")
    monkeypatch.setattr(workers.ejecutor, "contar_imagenes", lambda sol, u: (12, 4))
    w = workers.WorkerConteo(object(), generacion=7, umbral=20)
    recibido, fin = [], []
    w.senales.terminado.connect(recibido.append)
    w.senales.finalizado.connect(lambda: fin.append(1))
    w.run()
    assert recibido == [(7, 12, 4)] and fin == [1]


def test_worker_conteo_error_emite_error_y_finaliza(monkeypatch):
    def boom(p=None):
        raise RuntimeError("sin red")
    monkeypatch.setattr(workers.auth, "asegurar_sesion", boom)
    w = workers.WorkerConteo(None, 1, 20)
    errores, fin = [], []
    w.senales.error.connect(lambda t, m: errores.append((t, m)))
    w.senales.finalizado.connect(lambda: fin.append(1))
    w.run()
    assert errores == [("inesperado", "sin red")] and fin == [1]


def test_solicitud_modis_con_umbral_levanta():
    from app.dominio.errores import FiltroNubesNoDisponible
    from app.dominio.receta import Receta
    r = Receta(sensor="MODIS/061/MOD09GA", indices=["NDVI"], geometria={"type": "Polygon", "coordinates": []},
               fecha_inicio="2024-01-01", fecha_fin="2024-02-01", mascara_nubes=False,
               composicion="median", salida="preview", max_nubes_pct=20)
    with pytest.raises(FiltroNubesNoDisponible):
        workers.solicitud_desde_receta(r)


# --- F6b: multi-índice en el ejecutor y el adapter ---

def test_construir_imagen_con_tres_indices_pasa_la_lista(fake_ee):
    ejecutor.construir_imagen(_sol(indices=["NDVI", "EVI", "NDWI"]))
    assert ("spectralIndices", (["NDVI", "EVI", "NDWI"],)) in fake_ee.log
    assert ("select", (["NDVI", "EVI", "NDWI"],)) in fake_ee.log


class _ImgFake:
    def __init__(self, bandas):
        self.bandas, self.llamadas = bandas, 0

    def bandNames(self):
        return self

    def getInfo(self):
        self.llamadas += 1
        return self.bandas


def test_verificar_banda_presente_multibanda_ok_con_un_getinfo():
    img = _ImgFake(["NDVI", "EVI", "NDWI"])
    ejecutor.verificar_banda_presente(img, ["NDVI", "EVI", "NDWI"])
    assert img.llamadas == 1


def test_verificar_banda_presente_nombra_las_faltantes():
    img = _ImgFake(["NDVI"])
    with pytest.raises(ejecutor.BandaAusente, match="'EVI', 'NDWI'") as e:
        ejecutor.verificar_banda_presente(img, ["NDVI", "EVI", "NDWI"])
    assert "'NDVI'," not in str(e.value).split("(bandas")[0]
    assert img.llamadas == 1


def test_solicitud_desde_receta_lleva_indices_y_no_mira_producto(monkeypatch):
    import sys
    import types
    from app.dominio.receta import Receta
    monkeypatch.setitem(sys.modules, "ee", types.SimpleNamespace(Geometry=lambda g: ("geom", g)))
    r = Receta(sensor="COPERNICUS/S2_SR_HARMONIZED", indices=["NDVI", "EVI"],
               geometria={"type": "Polygon", "coordinates": []}, fecha_inicio="2024-01-01",
               fecha_fin="2024-02-01", mascara_nubes=False, composicion="median",
               salida="descarga", producto="serie_temporal", periodo="mensual")
    sol = workers.solicitud_desde_receta(r)
    assert sol.indices == ["NDVI", "EVI"] and not hasattr(sol, "producto")
