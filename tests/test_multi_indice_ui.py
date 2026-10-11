"""F7 - formulario multi-indice: lista checkable, interseccion de sensores, params agrupados,
combo de banda del preview. Headless, sin GEE."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from app.dominio import catalogo
from app.dominio.aoi import desde_bbox
from app.dominio.receta import Receta
from app.dominio.receta_json import RecetaCargada
from app.ui.ventana_principal import VentanaPrincipal

BBOX = {"tipo": "bbox", "oeste": -59.0, "sur": -35.0, "este": -58.0, "norte": -34.0}


@pytest.fixture
def ventana(qtbot, mapa_stub, monkeypatch):
    from app.gee import config
    monkeypatch.setattr(config, "hay_project_configurado", lambda: True)
    v = VentanaPrincipal()
    qtbot.addWidget(v)
    v._debounce_conteo.timeout.disconnect()   # el conteo nunca dispara en tests (no toca GEE)
    # AOI valida para que receta_actual() no sea None
    v.form.selector_aoi.tipo.setCurrentIndex(2)
    for k, val in [("oeste", -59.0), ("sur", -35.0), ("este", -58.0), ("norte", -34.0)]:
        v.form.selector_aoi._bbox[k].setValue(val)
    return v


def _item(form, sn):
    lista = form.lista_indices
    for i in range(lista.count()):
        if lista.item(i).data(Qt.ItemDataRole.UserRole) == sn:
            return lista.item(i)
    return None


def _principal(form, sn):
    form.combo_indice.setCurrentIndex(
        next(i for i in range(form.combo_indice.count())
             if form.combo_indice.itemData(i).short_name == sn))


def _tildar(form, sn, marcar=True):
    _item(form, sn).setCheckState(Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)


def _receta(**kw):
    base = dict(sensor="COPERNICUS/S2_SR", indices=["NDVI"],
                geometria=desde_bbox(-59.0, -35.0, -58.0, -34.0),
                fecha_inicio="2024-01-01", fecha_fin="2024-02-01", mascara_nubes=True,
                composicion="mean", salida="preview", escala=20)
    base.update(kw)
    return Receta(**base)


def test_tildar_extra_arma_receta_con_dos_indices(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "EVI")
    assert f.indices_seleccionados() == ["NDVI", "EVI"]
    r = f.receta_actual()
    assert r.indices == ["NDVI", "EVI"] and r.indices[0] == "NDVI"
    assert f.lbl_seleccion.text() == "NDVI, EVI"


def test_extras_en_orden_de_tildado(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "NDWI")
    _tildar(f, "EVI")
    assert f.indices_seleccionados() == ["NDVI", "NDWI", "EVI"]


def test_principal_no_se_puede_destildar(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "NDVI", marcar=False)
    assert _item(f, "NDVI").checkState() == Qt.CheckState.Checked
    assert f.indices_seleccionados() == ["NDVI"]


def test_filtrar_buscador_no_pierde_la_seleccion(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "EVI")
    f.edit_buscar.setText("ndvi")
    assert _item(f, "EVI") is None                      # EVI ya no esta en la lista filtrada
    assert f.indices_seleccionados() == ["NDVI", "EVI"]
    f.edit_buscar.setText("")
    assert _item(f, "EVI").checkState() == Qt.CheckState.Checked


def test_item_sin_sensor_en_comun_queda_deshabilitado(ventana):
    f = ventana.form
    _principal(f, "ARI")                                 # ARI y DBI no comparten sensor
    it = _item(f, "DBI")
    assert not (it.flags() & Qt.ItemFlag.ItemIsEnabled)
    assert "sin sensor en común" in it.toolTip()
    _tildar(f, "DBI")                                    # aunque se fuerce el tilde, no se suma
    assert f.indices_seleccionados() == ["ARI"]


def test_sensores_son_la_interseccion(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "EVI")
    ids = [f.combo_sensor.itemData(i).collection_id for i in range(f.combo_sensor.count())]
    assert ids == [s.collection_id for s in catalogo.sensores_para_indices(["NDVI", "EVI"])]
    assert "MODIS/006/MOD09GQ" in [s.collection_id for s in catalogo.sensores_para("NDVI")]
    assert "MODIS/006/MOD09GQ" not in ids


def test_parametro_compartido_tiene_un_solo_spinbox_y_valores_planos(ventana):
    f = ventana.form
    _principal(f, "EVI")                                 # EVI: C1 C2 L g
    _tildar(f, "SAVI")                                   # SAVI: L (compartido)
    assert list(f.panel_params._spins) == ["C1", "C2", "L", "g"]
    assert set(f.panel_params.valores()) == {"C1", "C2", "L", "g"}
    textos = [lbl.text() for lbl in f.panel_params.findChildren(QLabel)]
    assert any("L (compartido con EVI)" in t for t in textos)
    assert set(f.receta_actual().parametros) == {"C1", "C2", "L", "g"}


def test_tildar_conserva_parametros_editados(ventana):
    f = ventana.form
    _principal(f, "EVI")
    f.panel_params._spins["L"].setValue(0.7)
    _tildar(f, "SAVI")
    assert f.panel_params.valores()["L"] == pytest.approx(0.7)


def test_cambiar_principal_destilda_extras_incompatibles(ventana):
    f = ventana.form
    _principal(f, "ARI")
    _tildar(f, "ARI2")
    assert f.indices_seleccionados() == ["ARI", "ARI2"]
    _principal(f, "DBI")                                 # DBI es disjunto de ARI y de ARI2
    assert f.indices_seleccionados() == ["DBI"]
    assert "ARI2" in f.lbl_desc.text()                   # avisa cuales se destildaron
    assert catalogo.sensores_para_indices(f.indices_seleccionados())


def test_cargar_receta_con_tres_indices_restaura_todo(ventana):
    r = _receta(indices=["NDVI", "EVI", "NDWI"], parametros={"L": 0.9, "g": 2.0})
    avisos = ventana.form.cargar_receta(RecetaCargada(r, BBOX))
    f = ventana.form
    assert f.indices_seleccionados() == ["NDVI", "EVI", "NDWI"]
    assert f.combo_sensor.currentData().collection_id == "COPERNICUS/S2_SR"
    assert f.panel_params.valores()["L"] == pytest.approx(0.9)
    assert f.panel_params.valores()["g"] == pytest.approx(2.0)
    assert not any("índices" in a for a in avisos)
    assert f.receta_actual().indices == ["NDVI", "EVI", "NDWI"]


def test_cargar_receta_indice_extra_inexistente_deja_form_intacto(ventana):
    f = ventana.form
    _principal(f, "SAVI")
    with pytest.raises(ValueError, match="NO_EXISTE"):
        f.cargar_receta(RecetaCargada(_receta(indices=["NDVI", "NO_EXISTE"]), BBOX))
    assert f.indices_seleccionados() == ["SAVI"]


def test_cargar_receta_sensor_no_comun_a_todos_los_indices_levanta(ventana):
    f = ventana.form
    _principal(f, "SAVI")
    r = _receta(sensor="MODIS/006/MOD09GQ", indices=["NDVI", "EVI"],   # EVI no existe en MOD09GQ
                mascara_nubes=False, escala=250)
    with pytest.raises(ValueError, match="compatible"):
        f.cargar_receta(RecetaCargada(r, BBOX))
    assert f.indices_seleccionados() == ["SAVI"]


def test_combo_banda_lista_indices_y_default_es_el_primero(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "EVI")
    cb = ventana.combo_banda
    assert [cb.itemText(i) for i in range(cb.count())] == ["NDVI", "EVI"]
    assert cb.currentData() == "NDVI"


def test_combo_banda_conserva_la_elegida_si_sigue_en_la_receta(ventana):
    f = ventana.form
    _principal(f, "NDVI")
    _tildar(f, "EVI")
    ventana.combo_banda.setCurrentIndex(1)
    _tildar(f, "NDWI")
    assert ventana.combo_banda.currentData() == "EVI"
    _tildar(f, "EVI", marcar=False)                      # la banda elegida desaparece
    assert ventana.combo_banda.currentData() == "NDVI"


def test_paleta_sigue_la_banda_previsualizada(ventana):
    from app.mapa.preview import paleta_por_dominio
    f = ventana.form
    _principal(f, "NDVI")                                # vegetation
    _tildar(f, "NDWI")                                   # water
    ventana.combo_banda.setCurrentIndex(1)
    dom = catalogo.cargar_catalogo()["NDWI"].application_domain
    assert ventana.combo_paleta.currentData() == paleta_por_dominio(dom)
