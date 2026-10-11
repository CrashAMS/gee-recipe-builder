"""Diálogo de export + panel de exports (F5). Headless (offscreen). El diálogo ya no
es dueño del export: lanza vía GestorExports y cerrarlo NO cancela nada (reemplaza
los tests de cancel-on-close de B3/B4, que dejaron de aplicar)."""
from unittest.mock import MagicMock

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox

from app.gee.registro_exports import RegistroExports, nueva_entrada
from app.ui.dialogos.dialogo_export import DialogoExportDrive
from app.ui.panel_exports import PanelExports


class GestorFake(QObject):
    cambio = Signal(str)
    lanzado = Signal(str, str)
    fallo_lanzamiento = Signal(str, str)

    def __init__(self, registro=None):
        super().__init__()
        self.registro = registro
        self.lanzamientos = []
        self.cancelados = []
        self.detenidos = 0

    def lanzar(self, image, cfg, clave=None):
        self.lanzamientos.append((image, cfg, clave))
        return clave

    def cancelar(self, task_id):
        self.cancelados.append(task_id)

    def detener_todo(self):
        self.detenidos += 1

    def siguiendo(self, task_id):
        return True

    def aviso(self, task_id):
        return None


def _dialogo(qtbot, gestor=None):
    gestor = gestor or GestorFake()
    dlg = DialogoExportDrive(image="IMG", region="REG", gestor=gestor, sugerencia_nombre="ndvi_x")
    qtbot.addWidget(dlg)
    return dlg, gestor


def test_exportar_delega_al_gestor(qtbot):
    dlg, g = _dialogo(qtbot)
    dlg._on_exportar()
    assert len(g.lanzamientos) == 1
    image, cfg, clave = g.lanzamientos[0]
    assert image == "IMG" and cfg.region == "REG" and cfg.descripcion == "ndvi_x"
    assert clave == dlg._clave and clave
    g.lanzado.emit(clave, "T1")
    assert "T1" in dlg._label_estado.text() and "panel" in dlg._label_estado.text()


def test_lanzado_de_otro_dialogo_se_ignora(qtbot):
    dlg, g = _dialogo(qtbot)
    dlg._on_exportar()
    g.lanzado.emit("otra-clave", "T9")
    assert "T9" not in dlg._label_estado.text()


def test_fallo_de_lanzamiento_rehabilita_exportar(qtbot):
    dlg, g = _dialogo(qtbot)
    dlg._on_exportar()
    assert not dlg._btn_exportar.isEnabled()
    g.fallo_lanzamiento.emit(dlg._clave, "Cuota excedida")
    assert dlg._btn_exportar.isEnabled() and "Cuota" in dlg._label_estado.text()


def test_cerrar_no_cancela(qtbot):
    dlg, g = _dialogo(qtbot)
    dlg._on_exportar()
    dlg.show()
    dlg.close()
    assert g.cancelados == [] and g.detenidos == 0


def test_escape_no_cancela(qtbot):
    dlg, g = _dialogo(qtbot)
    dlg._on_exportar()
    dlg.show()
    qtbot.keyClick(dlg, Qt.Key.Key_Escape)
    assert not dlg.isVisible()
    assert g.cancelados == [] and g.detenidos == 0


def test_dialogo_no_tiene_boton_cancelar(qtbot):
    dlg, _ = _dialogo(qtbot)
    assert not hasattr(dlg, "_btn_cancelar")


# --- Panel de exports ---
def _panel(qtbot, tmp_path):
    reg = RegistroExports(tmp_path / "exports.json")
    reg.agregar(nueva_entrada("hecho", "viejo", "drive", "GEE", estado="completado"))
    reg.actualizar_estado("hecho", "completado", uris=["https://drive/x"])
    reg.agregar(nueva_entrada("vivo", "nuevo", "cloud_storage", "bkt", estado="corriendo"))
    g = GestorFake(reg)
    panel = PanelExports(g)
    qtbot.addWidget(panel)
    return panel, g


def test_panel_lista_desde_el_registro(qtbot, tmp_path):
    panel, _ = _panel(qtbot, tmp_path)
    assert panel.tabla.rowCount() == 2
    assert panel.tabla.item(0, 0).text() == "nuevo"
    assert panel.tabla.item(0, 1).text() == "Cloud Storage: bkt"
    assert panel.tabla.item(1, 3).text() == "completado"
    assert panel.tabla.cellWidget(1, 4) is not None     # link "abrir" del completado


def test_panel_cancelar_deshabilitado_en_terminales(qtbot, tmp_path):
    panel, _ = _panel(qtbot, tmp_path)
    panel.tabla.selectRow(1)   # completado
    assert not panel.btn_cancelar.isEnabled()
    panel.tabla.selectRow(0)   # corriendo
    assert panel.btn_cancelar.isEnabled()


def test_panel_cancelar_pide_confirmacion(qtbot, tmp_path, monkeypatch):
    panel, g = _panel(qtbot, tmp_path)
    panel.tabla.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question",
                        MagicMock(return_value=QMessageBox.StandardButton.No))
    panel.btn_cancelar.click()
    assert g.cancelados == []
    monkeypatch.setattr(QMessageBox, "question",
                        MagicMock(return_value=QMessageBox.StandardButton.Yes))
    panel.btn_cancelar.click()
    assert g.cancelados == ["vivo"]


def test_panel_refresca_en_cambio(qtbot, tmp_path):
    panel, g = _panel(qtbot, tmp_path)
    g.registro.actualizar_estado("vivo", "completado")
    g.cambio.emit("vivo")
    assert panel.tabla.item(0, 3).text() == "completado"


# --- Ventana: recuperación al abrir y cierre ---
def _ventana(qtbot, monkeypatch, con_project=True):
    from app.gee import config
    from app.ui.ventana_principal import VentanaPrincipal
    monkeypatch.setattr(config, "hay_project_configurado", lambda: con_project)
    v = VentanaPrincipal()
    qtbot.addWidget(v)
    return v


def test_ventana_recupera_pendientes_y_cierra_sin_cancelar(qtbot, mapa_stub, monkeypatch):
    v = _ventana(qtbot, monkeypatch)
    g = v.gestor_exports
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.recuperar = MagicMock(return_value=1)
    g.cancelar = MagicMock()
    v._recuperar_exports()
    g.recuperar.assert_called_once()
    v.close()
    g.cancelar.assert_not_called()


def test_ventana_sin_project_no_recupera(qtbot, mapa_stub, monkeypatch):
    v = _ventana(qtbot, monkeypatch, con_project=False)
    g = v.gestor_exports
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.recuperar = MagicMock()
    v._recuperar_exports()
    g.recuperar.assert_not_called()


def test_ventana_registro_aislado_en_tests(qtbot, mapa_stub, monkeypatch, tmp_path):
    # El autouse de conftest manda _dir_config() a tmp: la recuperación diferida no
    # encuentra pendientes reales del usuario.
    v = _ventana(qtbot, monkeypatch)
    assert str(tmp_path) in str(v.gestor_exports.registro.ruta)
    assert v.gestor_exports.registro.pendientes() == []
