"""Helpers comunes a ambos dialectos."""
import json
from app.dominio.receta import Composicion


def geojson_py(geom: dict) -> str:
    return repr(geom)               # dict literal válido en Python


def geojson_js(geom: dict) -> str:
    return json.dumps(geom)         # JSON ⊂ JS: objeto literal válido


def reductor(comp: Composicion) -> str:
    return {Composicion.MEDIANA: "median()", Composicion.MEDIA: "mean()",
            Composicion.MAXIMO: "max()", Composicion.MINIMO: "min()",
            Composicion.MOSAICO: "mosaic()"}[comp]
