"""F8 — ejecutor partido (construir_coleccion / serie_periodo), WorkerSerieTemporal y DialogoSerie."""
import pytest

from app.dominio.receta import Receta
from app.dominio.serie_csv import FilaSerie
from app.gee import ejecutor
from app.ui import workers
from tests.test_conteo_nubes import _sol, fake_ee  # noqa: F401  (fixture reusada)

_AOI = {"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6],
        [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]}


def _receta_serie(**kw):
    base = dict(sensor="COPERNICUS/S2_SR_HARMONIZED", indices=["NDVI", "EVI"], geometria=_AOI,
                fecha_inicio="2023-01-01", fecha_fin="2023-04-01", mascara_nubes=True,
                composicion="median", salida="descarga", producto="serie_temporal",
                periodo="mensual")
    base.update(kw)
    return Receta(**base)


# ---------- ejecutor ----------

def test_construir_imagen_mismo_orden_de_llamadas(fake_ee):
    ejecutor.construir_imagen(_sol())
    assert [n for n, _ in fake_ee.log] == [
        "ImageCollection", "filterBounds", "filterDate", "filter", "maskClouds",
        "scaleAndOffset", "spectralIndices", "median", "select", "clip"]


def test_construir_coleccion_es_el_prefijo_sin_reducir(fake_ee):
    ejecutor.construir_coleccion(_sol())
    assert [n for n, _ in fake_ee.log] == [
        "ImageCollection", "filterBounds", "filterDate", "filter", "maskClouds",
        "scaleAndOffset", "spectralIndices"]


class _Num:
    def __init__(self, v):
        self.v = v

    def gt(self, x):
        return ("gt", self.v, x)


class _Img:
    def __init__(self, log):
        self.log = log

    def select(self, b):
        self.log.append(("select", b))
        return self

    def reduceRegion(self, **k):
        self.log.append(("reduceRegion", k))
        return ("medias", k)


class _Sub:
    def __init__(self, log, n):
        self.log, self.n = log, n

    def size(self):
        return _Num(self.n)

    def median(self):
        self.log.append(("median", None))
        return _Img(self.log)


class _Col:
    def __init__(self, log, n):
        self.log, self.n = log, n

    def filterDate(self, a, b):
        self.log.append(("filterDate", (a, b)))
        return _Sub(self.log, self.n)


class _EESerie:
    """Fake de ee para serie_periodo: resuelve If (lazy) y cuenta getInfo."""

    def __init__(self, medias):
        self.getinfo = 0
        outer = self

        class Reducer:
            @staticmethod
            def mean():
                return "mean"

        class Algorithms:
            @staticmethod
            def If(cond, a, b):
                return a if cond[1] > cond[2] else b

        class Dictionary:
            def __init__(s, d):
                s.d = d

            def getInfo(s):
                outer.getinfo += 1
                m = s.d["medias"]
                return {"n": s.d["n"].v, "medias": medias if isinstance(m, tuple) else {}}

        self.Reducer, self.Algorithms, self.Dictionary = Reducer, Algorithms, Dictionary


def test_serie_periodo_un_solo_getinfo_y_medias(monkeypatch):
    fake = _EESerie({"NDVI": 0.6})
    monkeypatch.setattr(ejecutor, "ee", fake)
    log = []
    n, medias = ejecutor.serie_periodo(_Col(log, 3), _sol(indices=["NDVI", "EVI"]),
                                       "2024-01-01", "2024-02-01")
    assert fake.getinfo == 1
    assert n == 3 and medias == {"NDVI": 0.6, "EVI": None}   # clave ausente -> None
    assert ("filterDate", ("2024-01-01", "2024-02-01")) in log
    red = dict(log)["reduceRegion"]
    assert red["scale"] == 20 and red["maxPixels"] == 1e9 and red["geometry"] == "AOI"


def test_serie_periodo_sin_imagenes_devuelve_none(monkeypatch):
    fake = _EESerie({"NDVI": 0.6})
    monkeypatch.setattr(ejecutor, "ee", fake)
    n, medias = ejecutor.serie_periodo(_Col([], 0), _sol(), "2024-01-01", "2024-02-01")
    assert fake.getinfo == 1 and n == 0 and medias == {"NDVI": None}


# ---------- worker ----------

@pytest.fixture
def gee_fake(monkeypatch):
    estado = {"sesion": 0, "llamadas": [], "worker": None, "cancelar_en": None}

    def sesion(project=None):
        estado["sesion"] += 1

    def serie_periodo(col, sol, ini, fin):
        estado["llamadas"].append((ini, fin))
        if estado["cancelar_en"] == len(estado["llamadas"]):
            estado["worker"].solicitar_cancelacion()
        return 2, {"NDVI": 0.5, "EVI": None}

    monkeypatch.setattr(workers.auth, "asegurar_sesion", sesion)
    monkeypatch.setattr(workers, "solicitud_desde_receta", lambda r: "SOL")
    monkeypatch.setattr(workers.ejecutor, "construir_coleccion", lambda sol: "COL")
    monkeypatch.setattr(workers.ejecutor, "serie_periodo", serie_periodo)
    return estado


def _correr(worker):
    ev = {"progreso": [], "terminado": None, "cancelado": None, "error": None, "fin": 0}
    s = worker.senales
    s.progreso.connect(lambda i, t, f: ev["progreso"].append((i, t, f)))
    s.terminado.connect(lambda f: ev.__setitem__("terminado", f))
    s.cancelado.connect(lambda f: ev.__setitem__("cancelado", f))
    s.error.connect(lambda t, m: ev.__setitem__("error", (t, m)))
    s.finalizado.connect(lambda: ev.__setitem__("fin", ev["fin"] + 1))
    worker.run()
    return ev


def test_worker_emite_n_progresos_y_terminado(gee_fake):
    w = workers.WorkerSerieTemporal(_receta_serie())
    ev = _correr(w)
    assert [(i, t) for i, t, _ in ev["progreso"]] == [(1, 3), (2, 3), (3, 3)]
    assert ev["terminado"] == [f for _, _, f in ev["progreso"]]
    assert ev["terminado"][0] == FilaSerie("2023-01-01", "2023-02-01", 2, {"NDVI": 0.5, "EVI": None})
    assert ev["cancelado"] is None and ev["error"] is None and ev["fin"] == 1
    assert gee_fake["sesion"] == 1 and w.ha_terminado() and not w.autoDelete()


def test_worker_cancelado_tras_periodo_2(gee_fake):
    w = workers.WorkerSerieTemporal(_receta_serie())
    gee_fake["worker"], gee_fake["cancelar_en"] = w, 2
    ev = _correr(w)
    assert len(ev["cancelado"]) == 2 and ev["terminado"] is None
    assert len(gee_fake["llamadas"]) == 2 and ev["fin"] == 1


def test_worker_demasiados_periodos_sale_por_error_sin_gee(gee_fake):
    w = workers.WorkerSerieTemporal(_receta_serie(periodo="16_dias", fecha_inicio="2020-01-01",
                                                  fecha_fin="2023-01-01"))
    ev = _correr(w)
    assert ev["error"][0] == "DemasiadosPeriodos" and "60" in ev["error"][1]
    assert gee_fake["sesion"] == 0 and gee_fake["llamadas"] == [] and ev["fin"] == 1


def test_worker_error_gee_a_mitad_emite_error_y_finalizado(gee_fake, monkeypatch):
    def rompe(col, sol, ini, fin):
        raise RuntimeError("red caida")
    monkeypatch.setattr(workers.ejecutor, "serie_periodo", rompe)
    ev = _correr(workers.WorkerSerieTemporal(_receta_serie()))
    assert ev["error"] == ("inesperado", "red caida") and ev["fin"] == 1


# ---------- diálogo ----------

_FILAS = [FilaSerie("2023-01-01", "2023-02-01", 3, {"NDVI": 0.4, "EVI": 0.2}),
          FilaSerie("2023-02-01", "2023-03-01", 0, {"NDVI": None, "EVI": None}),
          FilaSerie("2023-03-01", "2023-04-01", 1, {"NDVI": 0.6, "EVI": None})]


def _alimentar(dlg, filas):
    for i, f in enumerate(filas, start=1):
        dlg.on_progreso(i, len(_FILAS), f)


def test_dialogo_grafico_una_serie_por_indice_y_omite_none(qtbot):
    from app.ui.dialogos.dialogo_serie import _HAY_QTCHARTS, DialogoSerie
    assert _HAY_QTCHARTS
    dlg = DialogoSerie(["NDVI", "EVI"], 3)
    qtbot.addWidget(dlg)
    _alimentar(dlg, _FILAS)
    assert dlg.usa_grafico and set(dlg.series) == {"NDVI", "EVI"}
    assert [(p.x(), round(p.y(), 3)) for p in dlg.series["NDVI"].points()] == [(0.0, 0.4), (2.0, 0.6)]
    assert [p.x() for p in dlg.series["EVI"].points()] == [0.0]
    assert dlg.eje_x.categories() == ["2023-01-01", "2023-02-01", "2023-03-01"]
    assert dlg.barra.value() == 3 and not dlg.btn_exportar.isEnabled()
    dlg.on_terminado(_FILAS)
    dlg.on_finalizado()
    assert dlg.btn_exportar.isEnabled() and not dlg.btn_cancelar.isEnabled()


def test_dialogo_sin_qtcharts_usa_tabla(qtbot, monkeypatch):
    from app.ui.dialogos import dialogo_serie
    monkeypatch.setattr(dialogo_serie, "_HAY_QTCHARTS", False)
    dlg = dialogo_serie.DialogoSerie(["NDVI"], 3)
    qtbot.addWidget(dlg)
    assert "QtCharts" in dlg.lbl_estado.text()
    _alimentar(dlg, _FILAS)
    assert not dlg.usa_grafico and dlg.tabla.rowCount() == 3
    assert dlg.tabla.item(1, 2).text() == "" and dlg.tabla.item(0, 2).text() == "0.4"


def test_dialogo_exportar_csv_tras_cancelar(qtbot, tmp_path):
    from app.ui.dialogos.dialogo_serie import DialogoSerie
    dlg = DialogoSerie(["NDVI", "EVI"], 3)
    qtbot.addWidget(dlg)
    pedidos = []
    dlg.cancelacion_pedida.connect(lambda: pedidos.append(1))
    _alimentar(dlg, _FILAS[:2])
    dlg.btn_cancelar.click()
    assert pedidos == [1]
    dlg.on_cancelado(_FILAS[:2])
    dlg.on_finalizado()
    assert dlg.btn_exportar.isEnabled()
    ruta = dlg.exportar_csv(str(tmp_path / "s.csv"))
    texto = (tmp_path / "s.csv").read_text(encoding="utf-8-sig")
    assert ruta and texto.splitlines() == [
        "periodo_inicio,periodo_fin,NDVI_mean,EVI_mean,n_imagenes",
        "2023-01-01,2023-02-01,0.4,0.2,3", "2023-02-01,2023-03-01,,,0"]


def test_cerrar_dialogo_en_curso_pide_cancelar(qtbot):
    from app.ui.dialogos.dialogo_serie import DialogoSerie
    dlg = DialogoSerie(["NDVI"], 3)
    qtbot.addWidget(dlg)
    pedidos = []
    dlg.cancelacion_pedida.connect(lambda: pedidos.append(1))
    dlg.show()
    dlg.close()
    assert pedidos == [1]
