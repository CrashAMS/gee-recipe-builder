"""Smoke UI headless — F3a. Verifica cableado del form y actualización en vivo del script."""
import pytest
from pathlib import Path

from app.ui.ventana_principal import VentanaPrincipal
from app.ui import workers


@pytest.fixture
def ventana(qtbot, mapa_stub, monkeypatch):
    # Sin project configurado, _ejecutar abre un QInputDialog modal que cuelga el test.
    from app.gee import config
    monkeypatch.setattr(config, "hay_project_configurado", lambda: True)
    v = VentanaPrincipal()
    qtbot.addWidget(v)
    return v


def test_arranca_con_indice_y_sensor_poblados(ventana):
    # Al primer índice, el combo de sensor tiene al menos una opción (query index-first de F1).
    assert ventana.form.combo_indice.count() > 0
    assert ventana.form.combo_sensor.count() > 0


def test_visor_muestra_script_no_vacio_con_receta_completa(ventana):
    # Setear una AOI bbox válida para completar la receta.
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)  # bbox
    ventana.form.selector_aoi._bbox["oeste"].setValue(-59.0)
    ventana.form.selector_aoi._bbox["sur"].setValue(-35.0)
    ventana.form.selector_aoi._bbox["este"].setValue(-58.0)
    ventana.form.selector_aoi._bbox["norte"].setValue(-34.0)
    ventana._actualizar_script()
    texto = ventana.visor.texto.toPlainText()
    assert texto and "Completá el formulario" not in texto


def test_toggle_js_python_cambia_el_script(ventana):
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        ventana.form.selector_aoi._bbox[k].setValue(val)
    ventana.visor.rb_js.setChecked(True)
    ventana._actualizar_script()
    script_js = ventana.visor.texto.toPlainText()
    ventana.visor.rb_py.setChecked(True)
    ventana._actualizar_script()
    script_py = ventana.visor.texto.toPlainText()
    assert script_js != script_py


def test_mascara_se_deshabilita_si_sensor_no_la_soporta(ventana, monkeypatch):
    # Forzar soporta_mascara=False y refrescar → checkbox deshabilitado y destildado.
    from app.dominio import catalogo
    monkeypatch.setattr(catalogo, "soporta_mascara", lambda _s: False)
    ventana.form._on_sensor()
    assert not ventana.form.chk_mascara.isEnabled()
    assert not ventana.form.chk_mascara.isChecked()


def test_ejecutar_con_salida_preview_dispara_worker_preview(ventana, qtbot, monkeypatch):
    # FIX-5: "Salida: Preview en mapa" ahora está habilitada en el combo (antes
    # deshabilitada, panel_formulario.py) y _ejecutar debe rutear a
    # _lanzar_preview en vez del flujo de descarga a disco.
    from app.gee import config

    monkeypatch.setattr(config, "hay_project_configurado", lambda: True)
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        ventana.form.selector_aoi._bbox[k].setValue(val)
    idx_preview = ventana.form.combo_salida.findData("preview")
    assert idx_preview != -1, "el ítem 'preview' debe estar habilitado y seleccionable"
    ventana.form.combo_salida.setCurrentIndex(idx_preview)
    ventana._ejecutar()
    assert len(lanzados) == 1
    assert isinstance(lanzados[0], workers.WorkerPreview)


def test_boton_ejecutar_usa_worker_sin_tocar_gee(ventana, qtbot, monkeypatch, tmp_path):
    # Mockear el diálogo de guardado y el pool para no tocar GEE ni el filesystem real.
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "s.tif"), "")))
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    # Completar receta (bbox) para que no aborte por "incompleta".
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        ventana.form.selector_aoi._bbox[k].setValue(val)
    ventana._ejecutar()
    assert len(lanzados) == 1
    assert isinstance(lanzados[0], workers.WorkerDescarga)


# ---- F2: buscador de índices + paleta/leyenda del preview ----
def test_buscador_filtra_combo_indice(ventana):
    total = ventana.form.combo_indice.count()
    ventana.form.edit_buscar.setText("ndvi")
    n = ventana.form.combo_indice.count()
    assert 0 < n < total
    assert ventana.form.combo_sensor.count() > 0
    ventana.form.edit_buscar.setText("")
    assert ventana.form.combo_indice.count() == total
    idx = ventana.form.combo_dominio.findData("water")
    ventana.form.combo_dominio.setCurrentIndex(idx)
    assert all(ventana.form.combo_indice.itemData(i).application_domain == "water"
               for i in range(ventana.form.combo_indice.count()))


def test_buscador_sin_coincidencias_no_rompe_ni_lanza_preview(ventana, qtbot, monkeypatch):
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    ventana.form.edit_buscar.setText("zzzzqqqq")
    assert ventana.form.combo_indice.count() == 0
    assert ventana.form.lbl_desc.text() == "Sin coincidencias"
    assert ventana.form.receta_actual() is None
    ventana._lanzar_preview(interactivo=False)
    assert lanzados == []


def _receta_bbox_lista(ventana):
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        ventana.form.selector_aoi._bbox[k].setValue(val)


def test_on_preview_ok_pasa_vis_al_stub(ventana):
    from app.mapa.preview import PreviewResultado
    res = PreviewResultado("https://t/{z}", {"min": 0.1, "max": 0.9, "palette": ["FFFFFF", "green"]}, True)
    ventana._on_preview_ok(res)
    url, vis = ventana._mapa.previews_cargados[-1]
    assert url == "https://t/{z}"
    assert vis["palette"] == ["#FFFFFF", "green"] and (vis["min"], vis["max"]) == (0.1, 0.9)
    assert vis["nota"] == ""
    assert (ventana.spin_min.value(), ventana.spin_max.value()) == (0.1, 0.9)
    ventana._on_preview_ok(PreviewResultado("u", {"min": 0, "max": 1, "palette": ["white"]}, False))
    assert ventana._mapa.previews_cargados[-1][1]["nota"] == "rango no estimado"


def test_cambiar_paleta_relanza_worker_con_vis_params(ventana, qtbot, monkeypatch):
    from app.mapa.preview import PALETAS, PreviewResultado
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    _receta_bbox_lista(ventana)
    ventana._on_preview_ok(PreviewResultado("u", {"min": 0.2, "max": 0.7, "palette": ["white"]}, True))
    ventana.combo_paleta.setCurrentIndex(ventana.combo_paleta.findData("agua"))
    qtbot.waitUntil(lambda: len(lanzados) == 1, timeout=3000)
    w = lanzados[0]
    assert w.vis_params == {"min": 0.2, "max": 0.7, "palette": PALETAS["agua"]}


def test_override_manual_y_auto(ventana, qtbot, monkeypatch):
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    _receta_bbox_lista(ventana)
    ventana._debounce_preview.stop()
    ventana.spin_min.setValue(0.3)
    ventana.spin_max.setValue(0.6)
    qtbot.waitUntil(lambda: len(lanzados) == 1, timeout=3000)
    assert (lanzados[0].vis_params["min"], lanzados[0].vis_params["max"]) == (0.3, 0.6)
    ventana._preview_en_curso = False
    ventana.btn_auto.click()
    qtbot.waitUntil(lambda: len(lanzados) == 2, timeout=3000)
    assert lanzados[1].vis_params is None


def test_cargar_receta_limpia_filtro_del_buscador(ventana):
    from app.dominio.receta_json import a_json, desde_json
    _receta_bbox_lista(ventana)
    ventana.form.combo_indice.setCurrentIndex(
        next(i for i in range(ventana.form.combo_indice.count())
             if ventana.form.combo_indice.itemData(i).short_name == "NDVI"))
    texto = a_json(ventana.form.receta_actual(), ventana.form.selector_aoi.descriptor())
    ventana.form.edit_buscar.setText("agua")
    assert "NDVI" not in {ventana.form.combo_indice.itemData(i).short_name
                          for i in range(ventana.form.combo_indice.count())}
    ventana.form.cargar_receta(desde_json(texto))
    assert ventana.form.edit_buscar.text() == ""
    assert ventana.form.combo_dominio.currentData() is None
    assert ventana.form._indice_actual().short_name == "NDVI"
    assert ventana.form.receta_actual().indice == "NDVI"
