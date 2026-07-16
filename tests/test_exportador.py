"""Tests para ExportadorGEE — F4 (lógica pura, sin GEE ni Qt)."""
import pytest

from app.gee.exportador import (
    ConfigExport, DestinoExport, EstadoExport, ProgresoExport,
    construir_task, es_error_de_cuota, interpretar_estado, sanitizar_descripcion,
)


# --- interpretar_estado ---
@pytest.mark.parametrize("crudo,esperado", [
    ("UNSUBMITTED", EstadoExport.PENDIENTE),
    ("READY", EstadoExport.PENDIENTE),
    ("RUNNING", EstadoExport.CORRIENDO),
    ("COMPLETED", EstadoExport.COMPLETADO),
    ("FAILED", EstadoExport.FALLIDO),
    ("CANCEL_REQUESTED", EstadoExport.CANCELADO),
    ("CANCELLED", EstadoExport.CANCELADO),
])
def test_interpretar_estado_mapea_todos_los_estados(crudo, esperado):
    prog = interpretar_estado({"state": crudo})
    assert prog.estado is esperado
    assert prog.crudo == crudo


def test_interpretar_estado_completado_es_terminal_y_ok():
    prog = interpretar_estado({"state": "COMPLETED", "id": "T1",
                               "destination_uris": ["https://drive/x"]})
    assert prog.terminal and prog.ok
    assert prog.task_id == "T1"
    assert prog.uris_destino == ("https://drive/x",)


def test_interpretar_estado_failed_terminal_no_ok_con_error():
    prog = interpretar_estado({"state": "FAILED",
                               "error_message": "User memory limit exceeded"})
    assert prog.terminal and not prog.ok
    assert prog.mensaje_error == "User memory limit exceeded"


def test_interpretar_estado_state_ausente_default_pendiente():
    prog = interpretar_estado({})
    assert prog.estado is EstadoExport.PENDIENTE
    assert not prog.terminal


# --- sanitizar_descripcion ---
def test_sanitizar_descripcion_reemplaza_ilegales_y_recorta():
    assert sanitizar_descripcion("NDVI 2024/03 (test)!") == "NDVI_2024_03__test__"
    assert len(sanitizar_descripcion("x" * 200)) == 100
    assert sanitizar_descripcion("   ") == "export_gee"


# --- es_error_de_cuota ---
@pytest.mark.parametrize("msg,esperado", [
    ("Too many tasks already in the queue", True),
    ("User memory limit exceeded", True),
    ("Quota exceeded for concurrent tasks", True),
    ("Image.load: collection not found", False),
    ("", False),
])
def test_es_error_de_cuota(msg, esperado):
    assert es_error_de_cuota(msg) is esperado


# --- construir_task (ee.batch mockeado) ---
def test_construir_task_drive_pasa_folder_y_no_bucket(monkeypatch):
    capturado = {}

    def fake_to_drive(**kwargs):
        capturado.update(kwargs)
        return "TASK_DRIVE"

    import ee
    monkeypatch.setattr(ee.batch.Export.image, "toDrive", fake_to_drive)
    cfg = ConfigExport("mi export", "mi_export", DestinoExport.DRIVE,
                       region="GEOM", carpeta_drive="MiCarpeta", scale=10)
    task = construir_task("IMG", cfg)
    assert task == "TASK_DRIVE"
    assert capturado["folder"] == "MiCarpeta"
    assert capturado["description"] == "mi_export"     # sanitizado
    assert capturado["fileFormat"] == "GeoTIFF"
    assert capturado["maxPixels"] == 1_000_000_000
    assert "bucket" not in capturado


def test_construir_task_cloud_storage_pasa_bucket_y_no_folder(monkeypatch):
    capturado = {}
    import ee
    monkeypatch.setattr(ee.batch.Export.image, "toCloudStorage",
                        lambda **kw: capturado.update(kw) or "TASK_GCS")
    cfg = ConfigExport("x", "x", DestinoExport.CLOUD_STORAGE,
                       region="GEOM", bucket="mi-bucket")
    task = construir_task("IMG", cfg)
    assert task == "TASK_GCS"
    assert capturado["bucket"] == "mi-bucket"
    assert "folder" not in capturado
