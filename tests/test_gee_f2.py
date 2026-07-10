"""Tests puros de F2 — errores, descarga (unzip), config. Sin GEE ni red."""
import io
import zipfile

import pytest

from app.gee.errores import (
    ComputoDemasiadoGrande,
    DescargaExcedeLimite,
    ErrorGEEDesconocido,
    clasificar_error,
)
from app.gee.descarga import extraer_tif_de_zip
from app.gee import config


def test_clasifica_computo_demasiado_grande():
    exc = Exception("Output of image computation is too large (3 bands for 7996648 pixels = 183.0 MiB > 80.0 MiB)")
    res = clasificar_error(exc)
    assert isinstance(res, ComputoDemasiadoGrande)
    assert "scale" in str(res).lower()


def test_clasifica_limite_descarga_32mb():
    exc = Exception("Total request size (40000000 bytes) must be less than or equal to 33554432 bytes.")
    res = clasificar_error(exc)
    assert isinstance(res, DescargaExcedeLimite)
    assert "drive" in str(res).lower()


def test_clasifica_limite_pixeles_10000():
    exc = Exception("Pixel grid dimensions (12000x8000) must be less than or equal to 10000.")
    assert isinstance(clasificar_error(exc), DescargaExcedeLimite)


def test_clasifica_desconocido_propaga_mensaje():
    exc = Exception("Some other GEE error")
    res = clasificar_error(exc)
    assert isinstance(res, ErrorGEEDesconocido)
    assert "Some other GEE error" in str(res)


def test_extraer_tif_de_zip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("download.NDVI.tif", b"II*\x00fake-geotiff-bytes")
    destino = tmp_path / "salida.tif"
    ruta = extraer_tif_de_zip(buf.getvalue(), str(destino))
    assert ruta == str(destino)
    assert destino.read_bytes().startswith(b"II*\x00")


def test_extraer_tif_sin_tif_falla():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"no tif here")
    with pytest.raises(ValueError, match="no contiene"):
        extraer_tif_de_zip(buf.getvalue(), "x.tif")


def test_config_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.leer_project() is None
    config.guardar_project("mi-proyecto-gee")
    assert config.leer_project() == "mi-proyecto-gee"


def test_config_actualiza_project(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.guardar_project("uno")
    config.guardar_project("dos")
    assert config.leer_project() == "dos"
