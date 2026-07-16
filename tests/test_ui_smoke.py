"""Smoke UI headless — F3a. Verifica cableado del form y actualización en vivo del script."""
import pytest
from pathlib import Path

from app.ui.ventana_principal import VentanaPrincipal
from app.ui import workers


@pytest.fixture
def ventana(qtbot):
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
