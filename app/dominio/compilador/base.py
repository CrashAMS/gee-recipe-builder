"""Helpers comunes a ambos dialectos."""
import json
from app.dominio.catalogo import propiedad_nubes
from app.dominio.errores import FiltroNubesNoDisponible
from app.dominio.receta import Composicion, Receta


def prop_nubes_filtro(r: Receta) -> str | None:
    """Propiedad GEE de % nubes si la receta pide filtrar; None si no hay filtro.
    Sensor sin propiedad (MODIS) con umbral seteado -> FiltroNubesNoDisponible."""
    if r.max_nubes_pct is None:
        return None
    prop = propiedad_nubes(r.sensor)
    if prop is None:
        raise FiltroNubesNoDisponible(
            f"El sensor {r.sensor} no tiene propiedad de % de nubes: no se puede filtrar por escena.")
    return prop


def geojson_py(geom: dict) -> str:
    return repr(geom)               # dict literal válido en Python


def js_str(s: str) -> str:
    """Literal JS entre comillas simples con escapes (strings libres en scripts JS)."""
    esc = (s.replace("\\", "\\\\").replace("'", "\\'")
           .replace("\n", "\\n").replace("\r", "\\r"))
    return f"'{esc}'"


def geojson_js(geom: dict) -> str:
    return json.dumps(geom)         # JSON ⊂ JS: objeto literal válido


def reductor(comp: Composicion) -> str:
    return {Composicion.MEDIANA: "median()", Composicion.MEDIA: "mean()",
            Composicion.MAXIMO: "max()", Composicion.MINIMO: "min()",
            Composicion.MOSAICO: "mosaic()"}[comp]
