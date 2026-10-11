"""F3 — cargar_receta, setters inversos y menú Archivo."""
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QFileDialog, QMessageBox

from app import recientes
from app.dominio import catalogo
from app.dominio.aoi import desde_bbox
from app.dominio.receta import Receta
from app.dominio.receta_json import RecetaCargada, a_json, desde_json
from app.ui.ventana_principal import VentanaPrincipal


@pytest.fixture
def ventana(qtbot, mapa_stub, monkeypatch, tmp_path):
    from app.gee import config
    monkeypatch.setattr(config, "hay_project_configurado", lambda: True)
    for var in ("APPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(var, str(tmp_path / "cfg"))
    v = VentanaPrincipal()
    qtbot.addWidget(v)
    v._debounce_preview.stop()
    v._debounce_conteo.timeout.disconnect()   # el conteo nunca dispara en tests (no toca GEE)
    return v


def _bbox_receta(**kw):
    base = dict(sensor="COPERNICUS/S2_SR", indices=["NDVI"],
                geometria=desde_bbox(-59.0, -35.0, -58.0, -34.0),
                fecha_inicio="2024-01-01", fecha_fin="2024-02-01", mascara_nubes=True,
                composicion="mean", salida="preview", escala=20)
    base.update(kw)
    return Receta(**base)


BBOX = {"tipo": "bbox", "oeste": -59.0, "sur": -35.0, "este": -58.0, "norte": -34.0}


def test_cargar_receta_bbox_deja_receta_equivalente(ventana):
    r = _bbox_receta()
    avisos = ventana.form.cargar_receta(RecetaCargada(r, BBOX))
    assert avisos == []
    assert a_json(ventana.form.receta_actual(), BBOX) == a_json(r, BBOX)


def test_cargar_emite_cambiado_una_sola_vez(ventana, qtbot):
    cuenta = []
    ventana.form.cambiado.connect(lambda: cuenta.append(1))
    ventana.form.cargar_receta(RecetaCargada(_bbox_receta(), BBOX))
    assert len(cuenta) == 1


def test_shapefile_inexistente_cae_a_dibujado_con_aviso(ventana, tmp_path):
    desc = {"tipo": "shapefile", "ruta": str(tmp_path / "no_existe.shp")}
    r = _bbox_receta()
    avisos = ventana.form.cargar_receta(RecetaCargada(r, desc))
    assert avisos and "no_existe.shp" in avisos[0]
    assert ventana.form.selector_aoi.descriptor()["tipo"] == "geojson-dict"
    assert ventana.form.receta_actual() is not None


def test_indice_desconocido_levanta_y_form_intacto(ventana):
    antes = ventana.form.combo_indice.currentIndex()
    escala = ventana.form.spin_escala.value()
    with pytest.raises(ValueError):
        ventana.form.cargar_receta(RecetaCargada(_bbox_receta(indices=["NO_EXISTE"]), BBOX))
    assert ventana.form.combo_indice.currentIndex() == antes
    assert ventana.form.spin_escala.value() == escala


def test_set_valores_ignora_claves_ajenas(ventana):
    f = ventana.form
    for i in range(f.combo_indice.count()):
        if f.combo_indice.itemData(i).parametros_ajustables:
            f.combo_indice.setCurrentIndex(i)
            break
    nombre = next(iter(f.panel_params.valores()))
    f.panel_params.set_valores({nombre: 1.25, "inexistente": 9.0})
    assert f.panel_params.valores()[nombre] == 1.25
    assert "inexistente" not in f.panel_params.valores()


def _indice_con(sensor):
    for ind in catalogo.listar_indices():
        if any(s.collection_id == sensor for s in catalogo.sensores_para(ind)):
            return ind.short_name
    pytest.skip(f"ningún índice con {sensor}")


def test_landsat5_fechas_2005_se_carga_sin_clamp(ventana):
    sensor = "LANDSAT/LT05/C02/T1_L2"
    r = _bbox_receta(sensor=sensor, indices=[_indice_con(sensor)],
                     fecha_inicio="2005-01-01", fecha_fin="2005-06-30", mascara_nubes=False)
    ventana.form.cargar_receta(RecetaCargada(r, BBOX))
    f = ventana.form
    assert f.fecha_inicio.date() == QDate(2005, 1, 1)
    assert f.fecha_fin.date() == QDate(2005, 6, 30)
    assert f.receta_actual().sensor == sensor


def test_cambiar_sensor_tras_cargar_no_pisa_la_escala(ventana):
    sensor = "LANDSAT/LT05/C02/T1_L2"
    r = _bbox_receta(sensor=sensor, indices=[_indice_con(sensor)], escala=77,
                     fecha_inicio="2005-01-01", fecha_fin="2005-06-30", mascara_nubes=False)
    f = ventana.form
    f.cargar_receta(RecetaCargada(r, BBOX))
    assert f.spin_escala.value() == 77
    f.combo_sensor.setCurrentIndex((f.combo_sensor.currentIndex() + 1) % f.combo_sensor.count())
    assert f.spin_escala.value() == 77


def test_menu_guardar_y_abrir_con_recientes(ventana, monkeypatch, tmp_path):
    f = ventana.form
    f.cargar_receta(RecetaCargada(_bbox_receta(), BBOX))
    destino = tmp_path / "mi_receta.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    ventana._guardar_receta()
    assert desde_json(destino.read_text(encoding="utf-8")).descriptor_aoi == BBOX
    assert recientes.listar() == [str(destino)]

    f.spin_escala.setValue(300)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(destino), ""))
    ventana._abrir_receta()
    assert f.spin_escala.value() == 20


def test_abrir_json_invalido_muestra_error(ventana, monkeypatch, tmp_path):
    malo = tmp_path / "malo.json"
    malo.write_text("{no", encoding="utf-8")
    mostrados = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: mostrados.append(a[2]))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(malo), ""))
    ventana._abrir_receta()
    assert mostrados and "JSON" in mostrados[0]


def test_cargar_receta_con_max_nubes_tilda_checkbox_y_spin(ventana):
    ventana.form.cargar_receta(RecetaCargada(_bbox_receta(max_nubes_pct=30), BBOX))
    assert ventana.form.chk_nubes.isChecked()
    assert ventana.form.spin_nubes.value() == 30
    assert ventana.form.receta_actual().max_nubes_pct == 30


def test_cargar_receta_sin_max_nubes_destilda(ventana):
    ventana.form.chk_nubes.setChecked(True)
    ventana.form.cargar_receta(RecetaCargada(_bbox_receta(), BBOX))
    assert not ventana.form.chk_nubes.isChecked()
    assert ventana.form.receta_actual().max_nubes_pct is None


# --- F6b: form mono-índice ante recetas multi-índice / producto ---

def test_receta_con_dos_indices_restaura_principal_y_extras_sin_aviso(ventana):
    r = _bbox_receta(indices=["NDVI", "EVI"])
    avisos = ventana.form.cargar_receta(RecetaCargada(r, BBOX))
    assert ventana.form.receta_actual().indices == ["NDVI", "EVI"]
    assert not any("índices" in a for a in avisos)


def test_receta_con_segundo_indice_desconocido_levanta(ventana):
    with pytest.raises(ValueError, match="NO_EXISTE"):
        ventana.form.cargar_receta(RecetaCargada(_bbox_receta(indices=["NDVI", "NO_EXISTE"]), BBOX))


def test_tabla_con_aoi_sin_features_avisa_y_queda_como_imagen(ventana):
    # F9: la tabla se restaura salvo que el AOI cargado (bbox/dibujo) no tenga features.
    r = _bbox_receta(producto="tabla_poligonos", features=fc_mini())
    avisos = ventana.form.cargar_receta(RecetaCargada(r, BBOX))
    assert any("tabla por polígono" in a for a in avisos)
    assert ventana.form.receta_actual().producto.value == "imagen"


def test_tabla_con_shapefile_se_restaura_sin_aviso(ventana, shp_lotes):
    desc = {"tipo": "shapefile", "ruta": str(shp_lotes)}
    r = _bbox_receta(producto="tabla_poligonos", features=fc_mini())
    avisos = ventana.form.cargar_receta(RecetaCargada(r, desc))
    assert not any("tabla" in a for a in avisos)
    actual = ventana.form.receta_actual()
    assert actual.producto.value == "tabla_poligonos"
    assert len(actual.features["features"]) == 3


def fc_mini():
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": desde_bbox(-59.0, -35.0, -58.0, -34.0), "properties": {}}]}


def test_estimacion_usa_n_bandas_igual_a_cantidad_de_indices(ventana, monkeypatch):
    from app.ui import panel_formulario
    llamadas = []
    real = panel_formulario.estimar_tamano_descarga

    def espia(*a, **k):
        llamadas.append(k["n_bandas"])
        return real(*a, **k)
    monkeypatch.setattr(panel_formulario, "estimar_tamano_descarga", espia)
    ventana.form.actualizar_estimacion(_bbox_receta(indices=["NDVI", "EVI", "NDWI"]))
    assert llamadas == [3]
