"""F9 — producto 'Tabla por polígono' en el form (habilitación por AOI), ruteo de la ventana y
WorkerTabla. Headless, sin GEE."""
import csv
import dataclasses

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from app.dominio import tabla_poligonos
from app.dominio.receta import Producto
from app.ui import panel_formulario, workers
from app.ui.ventana_principal import VentanaPrincipal


@pytest.fixture
def ventana(qtbot, mapa_stub, monkeypatch):
    from app.gee import config
    monkeypatch.setattr(config, "hay_project_configurado", lambda: True)
    v = VentanaPrincipal()
    qtbot.addWidget(v)
    v._debounce_preview.stop()
    v._debounce_conteo.timeout.disconnect()
    return v


def _bbox(form):
    form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        form.selector_aoi._bbox[k].setValue(val)


def _shp(form, ruta):
    form.selector_aoi.set_descriptor({"tipo": "shapefile", "ruta": str(ruta)})


def _item_tabla(form):
    c = form.combo_producto
    return c.model().item(c.findData(Producto.TABLA_POLIGONOS))


def _elegir_tabla(form):
    form.combo_producto.setCurrentIndex(form.combo_producto.findData(Producto.TABLA_POLIGONOS))


def test_bbox_y_dibujo_deshabilitan_la_tabla_con_tooltip(ventana):
    f = ventana.form
    _bbox(f)
    assert not _item_tabla(f).isEnabled()
    tip = f.combo_producto.itemData(f.combo_producto.findData(Producto.TABLA_POLIGONOS),
                                    Qt.ItemDataRole.ToolTipRole)
    assert "shapefile o GeoJSON" in tip and "rectángulo" in tip
    f.selector_aoi.set_geometria_dibujada({"type": "Polygon", "coordinates": [
        [[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.6]]]})
    assert not _item_tabla(f).isEnabled()


def test_shapefile_habilita_la_tabla_incluso_con_un_feature(ventana, shp_lotes, shp_valido):
    f = ventana.form
    _shp(f, shp_lotes)
    assert _item_tabla(f).isEnabled()
    _shp(f, shp_valido)                       # 1 feature sin atributos
    assert _item_tabla(f).isEnabled()


def test_volver_a_bbox_con_tabla_elegida_vuelve_a_imagen(ventana, shp_lotes):
    f = ventana.form
    _shp(f, shp_lotes)
    _elegir_tabla(f)
    assert f.producto_actual() is Producto.TABLA_POLIGONOS
    assert not f.combo_salida.isEnabled()
    _bbox(f)
    assert f.producto_actual() is Producto.IMAGEN
    assert f.combo_salida.isEnabled()


def test_receta_actual_lleva_producto_y_fc(ventana, shp_lotes):
    f = ventana.form
    _shp(f, shp_lotes)
    _elegir_tabla(f)
    r = f.receta_actual()
    assert r.producto is Producto.TABLA_POLIGONOS
    assert [x["properties"]["lote"] for x in r.features["features"]] == ["L1", "L2", "L3"]
    assert r.geometria["type"] in {"Polygon", "MultiPolygon"}     # sigue siendo la disuelta
    f.combo_producto.setCurrentIndex(f.combo_producto.findData(Producto.IMAGEN))
    assert f.receta_actual().features is None


def test_no_relee_features_al_cambiar_otros_campos(ventana, shp_lotes, monkeypatch):
    f = ventana.form
    _shp(f, shp_lotes)
    llamadas = []
    orig = panel_formulario.FuenteAOI.desde_archivo_features
    monkeypatch.setattr(panel_formulario.FuenteAOI, "desde_archivo_features",
                        staticmethod(lambda ruta: llamadas.append(ruta) or orig(ruta)))
    f.spin_escala.setValue(40)
    f.chk_mascara.toggle()
    assert llamadas == []


# ---- ruteo de la ventana ----

def test_ejecutar_tabla_local_pide_csv_y_lanza_worker(ventana, shp_lotes, monkeypatch, tmp_path):
    f = ventana.form
    _shp(f, shp_lotes)
    _elegir_tabla(f)
    destino = str(tmp_path / "t.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (destino, ""))
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lanzados.append)
    ventana._ejecutar()
    assert len(lanzados) == 1 and isinstance(lanzados[0], workers.WorkerTabla)
    assert lanzados[0].modo == "local" and lanzados[0].ruta_csv == destino


def test_ejecutar_tabla_sobre_umbral_pide_carpeta_y_va_a_drive(ventana, shp_lotes, monkeypatch):
    f = ventana.form
    _shp(f, shp_lotes)
    _elegir_tabla(f)
    monkeypatch.setattr(tabla_poligonos, "UMBRAL_TABLA_LOCAL", 1)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Mi_Carpeta", True))
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lanzados.append)
    ventana._ejecutar()
    assert lanzados[0].modo == "drive"
    pedidos = []
    monkeypatch.setattr(ventana.gestor_exports, "lanzar_tabla",
                        lambda fc, cfg, clave=None: pedidos.append((fc, cfg)))
    ventana._on_tabla_ok("FC")
    fc, cfg = pedidos[0]
    assert fc == "FC" and cfg.carpeta_drive == "Mi_Carpeta"
    assert cfg.selectors[:3] == ("lote", "fecha", "ha") and cfg.selectors[-1].endswith("_n")


def test_ejecutar_tabla_cancelando_el_dialogo_no_lanza(ventana, shp_lotes, monkeypatch):
    f = ventana.form
    _shp(f, shp_lotes)
    _elegir_tabla(f)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lanzados.append)
    ventana._ejecutar()
    assert lanzados == []


def test_error_de_tabla_muestra_critical(ventana, monkeypatch):
    vistos = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: vistos.append(a[1:]))
    ventana._on_tabla_error("ColumnaTablaEnConflicto", "choca")
    assert "ColumnaTablaEnConflicto" in vistos[0][0] and vistos[0][1] == "choca"


# ---- WorkerTabla.run() síncrono ----

class _FCInfo:
    def __init__(self, info):
        self.info = info

    def getInfo(self):
        return self.info


@pytest.fixture
def receta_tabla(ventana, shp_lotes):
    _shp(ventana.form, shp_lotes)
    _elegir_tabla(ventana.form)
    return dataclasses.replace(ventana.form.receta_actual(), indices=["NDVI"])


def _parchear(monkeypatch, info=None, exc=None):
    monkeypatch.setattr(workers.auth, "asegurar_sesion", lambda p=None: "proj")
    monkeypatch.setattr(workers, "solicitud_desde_receta", lambda r: "SOL")

    def fake(sol, fc):
        if exc:
            raise exc
        return _FCInfo(info) if info is not None else "FC_EE"
    monkeypatch.setattr(workers.ejecutor, "tabla_poligonos", fake)


def test_worker_local_escribe_csv_y_emite_la_ruta(receta_tabla, monkeypatch, tmp_path):
    info = {"features": [
        {"properties": {"lote": "L1", "fecha": "2024-01-15", "ha": 12.5, "NDVI_mean": 0.5,
                        "NDVI_min": 0.1, "NDVI_max": 0.9, "NDVI_std": 0.2, "NDVI_n": 9}},
        {"properties": {"lote": "L2", "fecha": "2024-02-01", "NDVI_n": 0}}]}
    _parchear(monkeypatch, info=info)
    ruta = tmp_path / "t.csv"
    w = workers.WorkerTabla(receta_tabla, "local", ruta)
    ok, fin = [], []
    w.senales.terminado.connect(ok.append)
    w.senales.finalizado.connect(lambda: fin.append(1))
    w.run()
    assert ok == [str(ruta)] and fin == [1]
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh))
    assert filas[0][:4] == ["lote", "fecha", "ha", "NDVI_mean"]
    assert filas[1][:4] == ["L1", "2024-01-15", "12.5", "0.5"]
    assert filas[2][2:] == ["", "", "", "", "", "0"]       # stats nulas -> celdas vacías


def test_worker_drive_emite_la_fc_sin_escribir(receta_tabla, monkeypatch, tmp_path):
    _parchear(monkeypatch)
    w = workers.WorkerTabla(receta_tabla, "drive")
    ok = []
    w.senales.terminado.connect(ok.append)
    w.run()
    assert ok == ["FC_EE"]
    assert list(tmp_path.glob("*.csv")) == []


def test_worker_error_emite_error_y_finaliza(receta_tabla, monkeypatch, tmp_path):
    _parchear(monkeypatch, exc=RuntimeError("sin red"))
    w = workers.WorkerTabla(receta_tabla, "local", tmp_path / "x.csv")
    errores, fin = [], []
    w.senales.error.connect(lambda t, m: errores.append((t, m)))
    w.senales.finalizado.connect(lambda: fin.append(1))
    w.run()
    assert errores == [("inesperado", "sin red")] and fin == [1]


def test_worker_colision_de_columnas_falla_antes_de_la_sesion(receta_tabla, monkeypatch, tmp_path):
    r = receta_tabla
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": r.geometria, "properties": {"NDVI_mean": 1}}]}
    r = dataclasses.replace(r, features=fc)
    llamadas = []
    monkeypatch.setattr(workers.auth, "asegurar_sesion", lambda p=None: llamadas.append(p))
    w = workers.WorkerTabla(r, "local", tmp_path / "x.csv")
    errores = []
    w.senales.error.connect(lambda t, m: errores.append(t))
    w.run()
    assert errores == ["ColumnaTablaEnConflicto"] and llamadas == []


def test_worker_modo_invalido():
    with pytest.raises(ValueError):
        workers.WorkerTabla(None, "otro")


def test_ejecutar_tabla_con_colision_avisa_antes_de_pedir_archivo(ventana, shp_lotes, monkeypatch):
    f = ventana.form
    _shp(f, shp_lotes)
    _elegir_tabla(f)
    r = f.receta_actual()
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": r.geometria, "properties": {f"{r.indices[0]}_n": 1}}]}
    monkeypatch.setattr(f, "receta_actual", lambda: dataclasses.replace(r, features=fc))
    avisos, dialogos = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: avisos.append(a[1:]))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: dialogos.append(1) or ("", ""))
    ventana._ejecutar()
    assert avisos and dialogos == []
