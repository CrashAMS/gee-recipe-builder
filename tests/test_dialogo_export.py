"""Tests de FIX-3 (race Qt en Cancelar) y FIX-4 (closeEvent huérfano) —
audit de cierre de gee-recipe-builder, bloqueantes B3/B4. Headless con
pytest-qt (mismo patrón offscreen que test_ui_smoke.py); nada de esto toca
GEE real: `QThreadPool.start` se mockea, así que `ExportPollingWorker.run()`
nunca corre en estos tests."""
from unittest.mock import MagicMock

from PySide6.QtCore import QThreadPool

from app.gee.exportador import ConfigExport, DestinoExport, EstadoExport, ProgresoExport
from app.ui.dialogos.dialogo_export import DialogoExportDrive
from app.ui.workers import ExportPollingWorker

_CFG = ConfigExport(descripcion="d", prefijo_archivo="p", destino=DestinoExport.DRIVE,
                     region=None, scale=10.0)


def _prog(estado: EstadoExport, **kw) -> ProgresoExport:
    base = dict(estado=estado, crudo=estado.name, mensaje_error=None, task_id="t1")
    base.update(kw)
    return ProgresoExport(**base)


def test_export_polling_worker_no_autodelete():
    # FIX-3: el pool no puede borrar el QRunnable mientras el diálogo retiene
    # `self._worker` — sin esto, "Cancelar" puede tocar un objeto ya destruido.
    w = ExportPollingWorker(image=None, cfg=_CFG)
    assert w.autoDelete() is False


def _dialogo(qtbot, monkeypatch):
    # No arrancar el worker en un thread real: sólo interesa el wiring Qt.
    monkeypatch.setattr(QThreadPool, "globalInstance",
                        staticmethod(lambda: MagicMock(start=lambda w: None)))
    dlg = DialogoExportDrive(image=None, region=None)
    qtbot.addWidget(dlg)
    dlg._on_exportar()   # crea self._worker y habilita Cancelar
    return dlg


def test_cancelar_se_deshabilita_en_completado_no_solo_en_finalizado(qtbot, monkeypatch):
    dlg = _dialogo(qtbot, monkeypatch)
    assert dlg._btn_cancelar.isEnabled()
    dlg._on_completado(_prog(EstadoExport.COMPLETADO, uris_destino=("https://drive/x",)))
    # FIX-3: deshabilitado ya en _on_completado, antes de que llegue `finalizado`.
    assert not dlg._btn_cancelar.isEnabled()
    assert dlg._terminado is True


def test_cancelar_se_deshabilita_en_fallo(qtbot, monkeypatch):
    dlg = _dialogo(qtbot, monkeypatch)
    dlg._on_fallo("cuota excedida")
    assert not dlg._btn_cancelar.isEnabled()
    assert dlg._terminado is True


def test_close_event_cancela_export_en_curso(qtbot, monkeypatch):
    # FIX-4: cerrar (X / closeEvent) con un export en curso no debe dejar el
    # polling huérfano — cancela server-side antes de aceptar el cierre.
    dlg = _dialogo(qtbot, monkeypatch)
    dlg._worker.solicitar_cancelacion = MagicMock()
    dlg.close()
    dlg._worker.solicitar_cancelacion.assert_called_once()


def test_reject_cancela_export_en_curso(qtbot, monkeypatch):
    # FIX-4: Escape / botón "Cerrar" llaman reject() directo, sin pasar por
    # closeEvent — mismo fix debe cubrir ese camino.
    dlg = _dialogo(qtbot, monkeypatch)
    dlg._worker.solicitar_cancelacion = MagicMock()
    dlg.reject()
    dlg._worker.solicitar_cancelacion.assert_called_once()


def test_close_event_no_cancela_si_ya_termino(qtbot, monkeypatch):
    # Con el export ya en estado terminal, cerrar no debe re-disparar la cancelación.
    dlg = _dialogo(qtbot, monkeypatch)
    dlg._on_completado(_prog(EstadoExport.COMPLETADO))
    dlg._worker.solicitar_cancelacion = MagicMock()
    dlg.close()
    dlg._worker.solicitar_cancelacion.assert_not_called()


def test_close_event_sin_worker_no_rompe(qtbot, monkeypatch):
    # Cerrar sin haber lanzado ningún export (self._worker is None) no debe crashear.
    monkeypatch.setattr(QThreadPool, "globalInstance",
                        staticmethod(lambda: MagicMock(start=lambda w: None)))
    dlg = DialogoExportDrive(image=None, region=None)
    qtbot.addWidget(dlg)
    dlg.close()   # no debe lanzar excepción
