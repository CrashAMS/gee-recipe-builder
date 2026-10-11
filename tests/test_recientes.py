import os
import pytest

from app import recientes
from app.gee import config


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def _archivo(tmp_path, nombre):
    p = tmp_path / nombre
    p.write_text("{}")
    return p


def test_orden_y_dedupe(tmp_path):
    a, b = _archivo(tmp_path, "a.json"), _archivo(tmp_path, "b.json")
    recientes.agregar(a)
    recientes.agregar(b)
    recientes.agregar(a)
    assert recientes.listar() == [os.path.abspath(a), os.path.abspath(b)]


def test_tope_10(tmp_path):
    for i in range(12):
        recientes.agregar(_archivo(tmp_path, f"r{i}.json"))
    lista = recientes.listar()
    assert len(lista) == 10
    assert lista[0].endswith("r11.json")


def test_ruta_inexistente_se_omite(tmp_path):
    a = _archivo(tmp_path, "a.json")
    recientes.agregar(a)
    recientes.agregar(tmp_path / "fantasma.json")
    assert recientes.listar() == [os.path.abspath(a)]


def test_archivo_corrupto_da_vacio_y_no_se_pisa(tmp_path):
    ruta = config._dir_config() / "recientes.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("{corrupto", encoding="utf-8")
    assert recientes.listar() == []
    assert ruta.read_text(encoding="utf-8") == "{corrupto"


def test_no_quedan_tmp(tmp_path):
    recientes.agregar(_archivo(tmp_path, "a.json"))
    recientes.limpiar()
    assert recientes.listar() == []
    assert not list(config._dir_config().glob("*.tmp"))


def test_archivo_no_utf8_da_vacio():
    ruta = config._dir_config() / "recientes.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(b"\xff\xfe\x00\xd8")
    assert recientes.listar() == []
