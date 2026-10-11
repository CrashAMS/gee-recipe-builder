"""Lista de recetas abiertas/guardadas recientemente (recientes.json, tope 10). Sin Qt."""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.gee import config

TOPE = 10


def _ruta() -> Path:
    return config._dir_config() / "recientes.json"


def _leer_crudo() -> list[str]:
    try:
        datos = json.loads(_ruta().read_text(encoding="utf-8"))
    except (OSError, ValueError):   # ValueError cubre JSON inválido y UnicodeDecodeError
        return []
    return [r for r in datos if isinstance(r, str)] if isinstance(datos, list) else []


def listar() -> list[str]:
    """Más reciente primero; omite rutas que ya no existen. No modifica el archivo."""
    return [r for r in _leer_crudo() if Path(r).exists()]


def agregar(ruta: str | Path) -> None:
    nueva = os.path.abspath(ruta)
    clave = os.path.normcase(nueva)
    previas = [r for r in _leer_crudo() if os.path.normcase(r) != clave]
    config.escribir_json_atomico(_ruta(), [nueva] + previas[:TOPE - 1])


def limpiar() -> None:
    config.escribir_json_atomico(_ruta(), [])
