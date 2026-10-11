"""Helpers comunes a ambos dialectos."""
import json
from app.dominio.catalogo import propiedad_nubes
from app.dominio.tabla_poligonos import SALIDAS_REDUCER, columnas_estadistica
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


def reducer_tabla_js(indice: str, sangria: str = "    ") -> list[str]:
    """Reducer combinado de la tabla (mean+min+max+stdDev+count sobre la misma entrada) con
    sus salidas renombradas a `<indice>_mean/_min/_max/_std/_n`. Líneas JS, la 1ª sin sangría."""
    lineas = ["ee.Reducer.mean()"]
    for nombre in SALIDAS_REDUCER[1:]:
        lineas.append(f"{sangria}.combine({{reducer2: ee.Reducer.{nombre}(), sharedInputs: true}})")
    salidas = ", ".join(js_str(c) for c in columnas_estadistica(indice))
    lineas.append(f"{sangria}.setOutputs([{salidas}])")
    return lineas


def reducer_tabla_py(indice: str, sangria: str = "         ") -> list[str]:
    """Idem `reducer_tabla_js` en Python (earthengine-api)."""
    lineas = ["ee.Reducer.mean()"]
    for nombre in SALIDAS_REDUCER[1:]:
        lineas.append(f"{sangria}.combine(ee.Reducer.{nombre}(), sharedInputs=True)")
    lineas.append(f"{sangria}.setOutputs({columnas_estadistica(indice)!r})")
    return lineas
