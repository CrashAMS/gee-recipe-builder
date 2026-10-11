"""F1 — escala nativa por sensor, calendarios limitados y estimación en vivo."""
import pytest
from PySide6.QtCore import QDate

from app.ui.ventana_principal import VentanaPrincipal


@pytest.fixture
def ventana(qtbot, mapa_stub, monkeypatch):
    from app.gee import config
    monkeypatch.setattr(config, "hay_project_configurado", lambda: True)
    v = VentanaPrincipal()
    qtbot.addWidget(v)
    v._debounce_preview.stop()
    return v


def _bbox(v, oeste=-59.0, sur=-35.0, este=-58.0, norte=-34.0):
    v.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", oeste), ("sur", sur), ("este", este), ("norte", norte)]:
        v.form.selector_aoi._bbox[k].setValue(val)


def _elegir_sensor(form, prefijo):
    for i in range(form.combo_sensor.count()):
        if form.combo_sensor.itemData(i).collection_id.startswith(prefijo):
            form.combo_sensor.setCurrentIndex(i)
            return
    pytest.skip(f"ningún sensor {prefijo} para el índice por defecto")


def _indice_con(form, prefijo):
    for i in range(form.combo_indice.count()):
        from app.dominio import catalogo
        sens = catalogo.sensores_para(form.combo_indice.itemData(i))
        if any(s.collection_id.startswith(prefijo) for s in sens):
            form.combo_indice.setCurrentIndex(i)
            return
    raise AssertionError(prefijo)


def test_cambiar_a_landsat_pone_30m(ventana):
    f = ventana.form
    _indice_con(f, "LANDSAT/LC08/C02")
    _elegir_sensor(f, "LANDSAT/LC08/C02")
    assert f.spin_escala.value() == 30


def test_escala_manual_se_conserva_al_cambiar_sensor(ventana):
    f = ventana.form
    _indice_con(f, "LANDSAT/LC08/C02")
    f.combo_sensor.setCurrentIndex(0)
    f.spin_escala.setValue(77)
    _elegir_sensor(f, "LANDSAT/LC08/C02")
    assert f.spin_escala.value() == 77


def test_min_calendarios_es_inicio_del_sensor(ventana):
    f = ventana.form
    _indice_con(f, "COPERNICUS/S2_SR")
    _elegir_sensor(f, "COPERNICUS/S2_SR_HARMONIZED")
    assert f.fecha_inicio.minimumDate() == QDate(2017, 3, 28)
    assert f.fecha_fin.minimumDate() == f.fecha_inicio.date() >= QDate(2017, 3, 28)


def test_fin_no_puede_quedar_antes_de_inicio(ventana):
    f = ventana.form
    f.fecha_inicio.setDate(QDate.currentDate().addMonths(-2))
    f.fecha_fin.setDate(QDate.currentDate().addYears(-1))
    assert f.fecha_fin.date() >= f.fecha_inicio.date()


def test_cambiar_bbox_actualiza_etiqueta(ventana):
    assert ventana.form.lbl_estimacion.text() == ""
    _bbox(ventana)
    assert "px" in ventana.form.lbl_estimacion.text()
    assert "MB" in ventana.form.lbl_estimacion.text()


def test_un_cambio_de_bbox_arma_la_receta_una_vez(ventana, monkeypatch):
    _bbox(ventana)
    llamadas = []
    original = ventana.form.receta_actual
    monkeypatch.setattr(ventana.form, "receta_actual",
                        lambda: llamadas.append(1) or original())
    ventana.form.selector_aoi._bbox["este"].setValue(-57.5)
    ventana._debounce_preview.stop()
    assert len(llamadas) == 1


def test_cambio_de_sensor_arma_la_receta_una_vez(ventana, monkeypatch):
    f = ventana.form
    _bbox(ventana)
    _indice_con(f, "LANDSAT/LC08/C02")
    destino = (f.combo_sensor.currentIndex() + 1) % f.combo_sensor.count()
    llamadas = []
    original = f.receta_actual
    monkeypatch.setattr(f, "receta_actual", lambda: llamadas.append(1) or original())
    f.combo_sensor.setCurrentIndex(destino)
    ventana._debounce_preview.stop()
    assert len(llamadas) == 1


def test_max_calendarios_de_sensor_deprecado(ventana):
    f = ventana.form
    _indice_con(f, "LANDSAT/LT05/C02")
    _elegir_sensor(f, "LANDSAT/LT05/C02")
    assert f.fecha_fin.maximumDate() == QDate(2012, 5, 5)
