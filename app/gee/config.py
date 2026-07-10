"""Persistencia del Google Cloud project elegido — F2."""
import json
import os
from pathlib import Path

_APP = "gee-recipe-builder"


def _dir_config() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / _APP


def _ruta_config() -> Path:
    return _dir_config() / "config.json"


def leer_project() -> str | None:
    ruta = _ruta_config()
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8")).get("project")
    except (json.JSONDecodeError, OSError):
        return None


def guardar_project(project_id: str) -> None:
    d = _dir_config()
    d.mkdir(parents=True, exist_ok=True)
    ruta = _ruta_config()
    datos = {}
    if ruta.exists():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            datos = {}
    datos["project"] = project_id
    ruta.write_text(json.dumps(datos, indent=2), encoding="utf-8")


def hay_project_configurado() -> bool:
    """Para que la UI (F3a) decida si mostrar el onboarding de project ANTES
    de llamar a `auth.asegurar_sesion` (que si no hay project, levanta `ErrorAuthGEE`)."""
    return leer_project() is not None
