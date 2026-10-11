"""Tests del registro persistente de exports (F5) — sin ee ni Qt, todo en tmp_path."""
import json

from app.gee import exportador
from app.gee.registro_exports import (
    ESTADOS_TERMINALES, TOPE, RegistroExports, nueva_entrada, ruta_default,
)


def _reg(tmp_path):
    return RegistroExports(tmp_path / "exports.json")


def test_ida_y_vuelta(tmp_path):
    r = _reg(tmp_path)
    r.agregar(nueva_entrada("t1", "ndvi", "drive", "GEE"))
    r.agregar(nueva_entrada("t2", "evi", "cloud_storage", "bucket"))
    otro = _reg(tmp_path)   # relee de disco
    ids = [e["task_id"] for e in otro.listar()]
    assert ids == ["t2", "t1"]   # más reciente primero
    e = otro.obtener("t1")
    assert e["nombre"] == "ndvi" and e["destino"] == "drive" and e["carpeta"] == "GEE"
    assert e["estado"] == "pendiente" and e["uris"] == [] and e["fecha_lanzado"]


def test_escritura_atomica_sin_tmp_residual(tmp_path):
    r = _reg(tmp_path)
    r.agregar(nueva_entrada("t1", "a", "drive", None))
    r.actualizar_estado("t1", "corriendo")
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads((tmp_path / "exports.json").read_text(encoding="utf-8"))[0]["estado"] == "corriendo"


def test_json_corrupto_se_aparta_a_bak_y_arranca_vacio(tmp_path):
    ruta = tmp_path / "exports.json"
    ruta.write_text("{no es json", encoding="utf-8")
    r = RegistroExports(ruta)
    assert r.listar() == []
    bak = tmp_path / "exports.json.bak"
    assert bak.exists() and bak.read_text(encoding="utf-8") == "{no es json"
    r.agregar(nueva_entrada("t1", "a", "drive", None))
    assert [e["task_id"] for e in r.listar()] == ["t1"]


def test_tope_descarta_terminales_viejas_nunca_pendientes(tmp_path):
    r = _reg(tmp_path)
    # 10 pendientes viejas + 40 terminales, después 5 nuevas → 55 > TOPE.
    for i in range(10):
        r.agregar(nueva_entrada(f"p{i}", "x", "drive", None))
    for i in range(40):
        r.agregar(nueva_entrada(f"c{i}", "x", "drive", None, estado="completado"))
    for i in range(5):
        r.agregar(nueva_entrada(f"n{i}", "x", "drive", None))
    ids = [e["task_id"] for e in r.listar()]
    assert len(ids) == TOPE
    assert all(f"p{i}" in ids for i in range(10))          # pendientes viejas sobreviven
    assert all(f"c{i}" not in ids for i in range(5))       # las 5 terminales más viejas se fueron
    assert "c5" in ids and "n4" in ids


def test_tope_con_todo_pendiente_no_descarta(tmp_path):
    r = _reg(tmp_path)
    for i in range(TOPE + 3):
        r.agregar(nueva_entrada(f"p{i}", "x", "drive", None))
    assert len(r.listar()) == TOPE + 3


def test_actualizar_estado_id_inexistente_no_rompe(tmp_path):
    r = _reg(tmp_path)
    assert r.actualizar_estado("nope", "completado") is False
    assert not (tmp_path / "exports.json").exists()
    r.agregar(nueva_entrada("t1", "a", "drive", None))
    assert r.actualizar_estado("nope", "completado") is False
    assert r.obtener("t1")["estado"] == "pendiente"


def test_actualizar_estado_y_pendientes(tmp_path):
    r = _reg(tmp_path)
    r.agregar(nueva_entrada("t1", "a", "drive", None))
    r.agregar(nueva_entrada("t2", "b", "drive", None))
    assert r.actualizar_estado("t1", "completado", uris=["https://drive/x"]) is True
    assert r.obtener("t1")["uris"] == ["https://drive/x"]
    assert [e["task_id"] for e in r.pendientes()] == ["t2"]


def test_terminales_espejan_al_exportador():
    assert ESTADOS_TERMINALES == {e.value for e in exportador._TERMINALES}


def test_ruta_default_bajo_dir_config():
    from app.gee import config
    assert ruta_default() == config._dir_config() / "exports.json"


def test_oserror_al_leer_no_pisa_el_registro_al_escribir(tmp_path, monkeypatch):
    r = _reg(tmp_path)
    r.agregar(nueva_entrada("t1", "a", "drive", None))
    from pathlib import Path
    import pytest

    def bloqueado(self, *a, **k):
        raise PermissionError("tomado por antivirus")
    monkeypatch.setattr(Path, "read_text", bloqueado)
    assert r.listar() == []                 # lectura tolerante
    with pytest.raises(OSError):
        r.agregar(nueva_entrada("t2", "b", "drive", None))
    monkeypatch.undo()
    assert [e["task_id"] for e in r.listar()] == ["t1"]
