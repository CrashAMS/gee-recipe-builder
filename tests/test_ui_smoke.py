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
    v._debounce_conteo.timeout.disconnect()   # el conteo nunca dispara en tests (no toca GEE)
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
    assert ventana.form.receta_actual().indices == ["NDVI"]


# --- F4: filtro de nubes + conteo ---

def _bbox_valido(ventana):
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        ventana.form.selector_aoi._bbox[k].setValue(val)


def _elegir_sensor(ventana, prefijo):
    f = ventana.form
    i = next(i for i in range(f.combo_sensor.count())
             if f.combo_sensor.itemData(i).collection_id.startswith(prefijo))
    f.combo_sensor.setCurrentIndex(i)


def test_modis_deshabilita_controles_de_nubes(ventana):
    from app.dominio import catalogo
    f = ventana.form
    ind = next(i for i in catalogo.buscar()
               if any(s.collection_id.startswith("MODIS/") for s in catalogo.sensores_para(i))
               and any(s.collection_id.startswith("COPERNICUS/S2") for s in catalogo.sensores_para(i)))
    f.combo_indice.setCurrentIndex(next(
        i for i in range(f.combo_indice.count()) if f.combo_indice.itemData(i).short_name == ind.short_name))
    _bbox_valido(ventana)
    _elegir_sensor(ventana, "COPERNICUS/S2")
    f.chk_nubes.setChecked(True)
    _elegir_sensor(ventana, "MODIS/")
    assert not f.chk_nubes.isEnabled() and not f.spin_nubes.isEnabled()
    assert not f.chk_nubes.isChecked()
    assert f.receta_actual().max_nubes_pct is None


def test_receta_actual_lleva_max_nubes_solo_con_checkbox_tildado(ventana):
    f = ventana.form
    _bbox_valido(ventana)
    _elegir_sensor(ventana, "COPERNICUS/S2")
    f.spin_nubes.setValue(35)
    assert f.receta_actual().max_nubes_pct is None
    f.chk_nubes.setChecked(True)
    assert f.receta_actual().max_nubes_pct == 35
    assert f.umbral_nubes() == 35


def test_respuesta_de_conteo_con_token_viejo_se_descarta(ventana):
    ventana._gen_conteo = 5
    ventana.form.lbl_conteo.setText("Contando escenas")
    ventana._on_conteo_ok((4, 10, 3))
    ventana._on_conteo_error(4, "inesperado", "x")
    assert ventana.form.lbl_conteo.text() == "Contando escenas"
    ventana._umbral_conteo = 20
    ventana._on_conteo_ok((5, 23, 9))
    assert ventana.form.lbl_conteo.text() == "23 escenas, 9 con < 20 % nubes"
    ventana._on_conteo_ok((5, 7, None))
    assert ventana.form.lbl_conteo.text() == "7 escenas"
    ventana._on_conteo_error(5, "inesperado", "sin red")
    assert ventana.form.lbl_conteo.text() == "conteo no disponible: sin red"


class _PoolEspia:
    def __init__(self):
        self.iniciados = []

    def start(self, w):
        self.iniciados.append(w)


def test_sin_project_no_se_lanza_conteo(ventana, monkeypatch):
    from app.gee import config
    monkeypatch.setattr(config, "hay_project_configurado", lambda: False)
    ventana.pool = _PoolEspia()
    _bbox_valido(ventana)
    g = ventana._gen_conteo
    ventana._lanzar_conteo()
    assert ventana.pool.iniciados == []
    ventana._on_conteo_ok((g, 5, 1))   # respuesta en vuelo anterior al salto
    assert ventana.form.lbl_conteo.text() == ""


def test_lanzar_conteo_incrementa_token_y_arma_worker(ventana):
    ventana.pool = _PoolEspia()
    _bbox_valido(ventana)
    g0 = ventana._gen_conteo
    ventana._lanzar_conteo()
    ventana._lanzar_conteo()
    assert ventana._gen_conteo == g0 + 2
    assert [w.generacion for w in ventana.pool.iniciados] == [g0 + 1, g0 + 2]
    assert ventana.form.lbl_conteo.text().startswith("Contando escenas")


# ---- F8: producto serie temporal ----

def _modo_serie(ventana, periodo="mensual", ini=(2023, 1, 1), fin=(2023, 4, 1)):
    from PySide6.QtCore import QDate
    from app.dominio.receta import Producto
    f = ventana.form
    _bbox_valido(ventana)
    _elegir_sensor(ventana, "COPERNICUS/S2")
    f.fecha_inicio.setDate(QDate(*ini))
    f.fecha_fin.setDate(QDate(*fin))
    f.combo_producto.setCurrentIndex(f.combo_producto.findData(Producto.SERIE_TEMPORAL))
    f.combo_periodo.setCurrentIndex(f.combo_periodo.findData(periodo))


def test_combo_periodo_solo_con_serie_y_salida_deshabilitada(ventana):
    from app.dominio.receta import PERIODOS, Producto
    f = ventana.form
    assert [f.combo_periodo.itemData(i) for i in range(f.combo_periodo.count())] == list(PERIODOS)
    assert f.combo_periodo.isHidden() and f.combo_salida.isEnabled()
    _modo_serie(ventana, "anual")
    assert not f.combo_periodo.isHidden() and not f.combo_salida.isEnabled()
    r = f.receta_actual()
    assert r.producto is Producto.SERIE_TEMPORAL and r.periodo == "anual"
    f.combo_producto.setCurrentIndex(f.combo_producto.findData(Producto.IMAGEN))
    assert f.combo_periodo.isHidden() and f.combo_salida.isEnabled()
    assert f.receta_actual().periodo is None


def test_ejecutar_con_serie_lanza_worker_y_abre_dialogo(ventana, monkeypatch):
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    _modo_serie(ventana)
    ventana._ejecutar()
    assert len(lanzados) == 1 and isinstance(lanzados[0], workers.WorkerSerieTemporal)
    assert ventana._dialogo_serie is not None and ventana._dialogo_serie.total == 3
    assert ventana._dialogo_serie.isVisible()


def test_ejecutar_serie_con_mas_de_60_periodos_avisa_sin_lanzar(ventana, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    avisos, lanzados = [], []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    monkeypatch.setattr(ventana.pool, "start", lambda w: lanzados.append(w))
    _modo_serie(ventana, "16_dias", ini=(2020, 1, 1), fin=(2023, 1, 1))
    ventana._ejecutar()
    assert lanzados == [] and len(avisos) == 1 and "60" in avisos[0]
    assert ventana._dialogo_serie is None


def test_close_event_cancela_serie_en_curso(ventana, monkeypatch):
    monkeypatch.setattr(ventana.pool, "start", lambda w: None)
    _modo_serie(ventana)
    ventana._ejecutar()
    w = ventana._worker_serie
    ventana.close()
    assert w._cancelar.is_set()


def test_cargar_receta_restaura_producto_y_periodo_sin_aviso(ventana, qtbot):
    from app.dominio.aoi import desde_bbox
    from app.dominio.receta import Producto, Receta
    from app.dominio.receta_json import RecetaCargada
    r = Receta(sensor="COPERNICUS/S2_SR", indices=["NDVI"], geometria=desde_bbox(-59.0, -35.0, -58.0, -34.0),
               fecha_inicio="2023-01-01", fecha_fin="2023-06-01", mascara_nubes=True,
               composicion="mean", salida="descarga", escala=20,
               producto="serie_temporal", periodo="16_dias")
    cuenta = []
    ventana.form.cambiado.connect(lambda: cuenta.append(1))
    avisos = ventana.form.cargar_receta(RecetaCargada(r, {"tipo": "bbox", "oeste": -59.0, "sur": -35.0,
                                                          "este": -58.0, "norte": -34.0}))
    assert avisos == [] and len(cuenta) == 1
    f = ventana.form
    assert Producto(f.combo_producto.currentData()) is Producto.SERIE_TEMPORAL
    assert f.combo_periodo.currentData() == "16_dias" and not f.combo_periodo.isHidden()
    assert f.receta_actual() == r


# ---- B1: refresco de preview reencolado; B2: disparo automático sin OAuth ----
def test_preview_descartado_en_vuelo_se_reencola(ventana):
    ventana._preview_en_curso = True
    ventana._lanzar_preview(interactivo=False)
    assert ventana._preview_pendiente
    ventana._on_preview_ok(object())      # resultado de la receta vieja: se descarta
    assert ventana._ultimo_resultado is None
    ventana._debounce_preview.stop()
    ventana._on_preview_fin()
    assert not ventana._preview_pendiente and ventana._debounce_preview.isActive()


def test_preview_automatico_sin_sesion_no_abre_oauth(ventana, monkeypatch):
    from app.gee import auth, config
    lanzados = []
    monkeypatch.setattr(ventana.pool, "start", lanzados.append)
    ventana.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        ventana.form.selector_aoi._bbox[k].setValue(val)
    ventana._lanzar_preview(interactivo=False)
    w = lanzados[-1]
    assert w.interactivo is False

    def oauth(p=None):
        raise AssertionError("un disparo automático no debe abrir OAuth")
    con_lock = []
    monkeypatch.setattr(auth, "asegurar_sesion", oauth)
    monkeypatch.setattr(config, "leer_project", lambda: "proj")
    monkeypatch.setattr(auth, "intentar_inicializar",
                        lambda p: con_lock.append(workers._LOCK_SESION.locked()) or False)
    errores, fin = [], []
    w.senales.error.connect(lambda t, m: errores.append(t))
    w.senales.finalizado.connect(lambda: fin.append(1))
    workers.WorkerPreview.run(w)
    assert con_lock == [True] and errores == [] and fin == [1]
