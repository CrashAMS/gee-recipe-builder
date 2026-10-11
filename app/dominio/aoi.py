"""FuenteAOI — normaliza entradas heterogéneas a un GeoJSON geometry dict (EPSG:4326).

Nunca devuelve `ee.Geometry` (objeto de servidor) — eso rompería la pureza del
dominio. Es exactamente lo que `ee.Geometry(dict)` consume aguas abajo en F2/F3b."""
from __future__ import annotations
import datetime as dt
import math
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box, shape, mapping
from shapely.ops import unary_union

from app.dominio.errores import FuenteAOIError

CRS_SALIDA = "EPSG:4326"


def desde_bbox(minx: float, miny: float, maxx: float, maxy: float) -> dict:
    """bbox lon/lat -> Polygon dict (anillo cerrado, [lon,lat], lo hace shapely)."""
    return mapping(box(minx, miny, maxx, maxy))


def desde_geojson_dict(gj: dict) -> dict:
    """Acepta Geometry, Feature o FeatureCollection -> geometry dict único (disuelto)."""
    tipo = gj.get("type")
    if tipo == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in gj["features"]]
    elif tipo == "Feature":
        geoms = [shape(gj["geometry"])]
    elif tipo in {"Polygon", "MultiPolygon", "GeometryCollection", "Point", "LineString"}:
        geoms = [shape(gj)]
    else:
        raise FuenteAOIError(f"GeoJSON no interpretable: type={tipo!r}")
    return mapping(unary_union(geoms))


def desde_archivo(ruta: str | Path) -> dict:
    """Shapefile (.shp con sidecars, o .zip) -> geometry dict en 4326."""
    ruta = Path(ruta)
    try:
        if ruta.suffix == ".zip":
            gdf = gpd.read_file(f"zip://{ruta}", engine="pyogrio")
        else:
            gdf = gpd.read_file(ruta, engine="pyogrio")
    except Exception as exc:
        raise FuenteAOIError(f"{ruta.name}: no se pudo leer el archivo ({exc})") from exc
    if gdf.crs is None:
        raise FuenteAOIError(f"{ruta.name}: falta CRS (¿shapefile sin .prj?); no se puede reproyectar")
    gdf = gdf.to_crs(CRS_SALIDA)
    return mapping(unary_union(list(gdf.geometry)))


def _valor_json(v):
    """Valor de una property -> tipo JSON estándar: fechas a ISO, NaN/inf/NaT/pd.NA a
    None, escalares numpy a nativos (vía `.item()`; datetime64 vía `pd.Timestamp`)."""
    import numpy as np
    import pandas as pd
    if v is None:
        return None
    if isinstance(v, (list, tuple, dict, set)):
        return str(v)
    try:
        if pd.isna(v):                                             # NaN, NaT, pd.NA
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, np.datetime64):
        v = pd.Timestamp(v)
    elif isinstance(v, np.generic):                                # numpy scalar
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (dt.datetime, dt.date, dt.time)):             # incluye pandas.Timestamp
        return v.isoformat()
    if isinstance(v, (str, bool, int, float)):
        return v
    return str(v)


def desde_archivo_features(ruta: str | Path) -> dict:
    """Shapefile (.shp con sidecars, o .zip) -> FeatureCollection en EPSG:4326 que
    conserva cada feature y sus properties (JSON-serializables), SIN disolver.
    Sin tope de cantidad (el umbral local/Drive es de F9). Levanta FuenteAOIError
    si el archivo no se lee, no tiene CRS, no tiene features o alguna geometría es nula."""
    ruta = Path(ruta)
    try:
        if ruta.suffix == ".zip":
            gdf = gpd.read_file(f"zip://{ruta}", engine="pyogrio")
        else:
            gdf = gpd.read_file(ruta, engine="pyogrio")
    except Exception as exc:
        raise FuenteAOIError(f"{ruta.name}: no se pudo leer el archivo ({exc})") from exc
    if gdf.crs is None:
        raise FuenteAOIError(f"{ruta.name}: falta CRS (¿shapefile sin .prj?); no se puede reproyectar")
    if len(gdf) == 0:
        raise FuenteAOIError(f"{ruta.name}: el archivo no tiene polígonos.")
    nulas = [i for i, g in enumerate(gdf.geometry) if g is None or g.is_empty]
    if nulas:
        raise FuenteAOIError(
            f"{ruta.name}: {len(nulas)} feature(s) sin geometría (filas {nulas[:5]}).")
    gdf = gdf.to_crs(CRS_SALIDA)
    # to_dict('records') conserva los nombres de columna tal cual (itertuples los renombra).
    filas = gdf.drop(columns=gdf.geometry.name).to_dict("records")
    features = [{"type": "Feature", "geometry": mapping(geom),
                 "properties": {str(k): _valor_json(v) for k, v in fila.items()}}
                for geom, fila in zip(gdf.geometry, filas)]
    return {"type": "FeatureCollection", "features": features}


def desde_descriptor(descriptor: dict) -> dict:
    """Punto de entrada único para consumidores que traen un AOI como *descriptor*
    en vez de llamar directo a una de las funciones de arriba (contrato compartido
    'FuenteAOI' entre F3a -bbox de un form- y F3b -dibujo/import del mapa-).
    Despacha por `descriptor['tipo']`:
      - 'bbox':          {'tipo':'bbox','oeste':..,'sur':..,'este':..,'norte':..}
      - 'geojson-dict':  {'tipo':'geojson-dict','geojson': {...}}
      - 'geojson' | 'shapefile': {'tipo':'geojson'|'shapefile','ruta': '...'}
    Devuelve SIEMPRE un GeoJSON geometry dict en EPSG:4326 — nunca un ee.Geometry
    (decisión 9). Levanta FuenteAOIError si el tipo no se reconoce."""
    tipo = descriptor.get("tipo")
    if tipo == "bbox":
        return desde_bbox(descriptor["oeste"], descriptor["sur"],
                           descriptor["este"], descriptor["norte"])
    if tipo == "geojson-dict":
        return desde_geojson_dict(descriptor["geojson"])
    if tipo in {"geojson", "shapefile"}:
        return desde_archivo(descriptor["ruta"])
    raise FuenteAOIError(f"descriptor de AOI no reconocido: tipo={tipo!r}")


def bbox_de(geometria: dict) -> tuple[float, float, float, float]:
    """GeoJSON geometry dict -> (minx, miny, maxx, maxy). Sin GEE (shapely .bounds)."""
    return tuple(shape(geometria).bounds)


class FuenteAOI:
    """Fachada de conveniencia — agrupa las funciones libres bajo un único nombre
    importable. Es sólo un namespace: no hay estado ni instancias, todo son
    staticmethods que delegan en las funciones libres de este módulo."""

    desde_bbox = staticmethod(desde_bbox)
    desde_geojson_dict = staticmethod(desde_geojson_dict)
    desde_archivo = staticmethod(desde_archivo)
    desde_archivo_features = staticmethod(desde_archivo_features)
    desde_descriptor = staticmethod(desde_descriptor)
    bbox_de = staticmethod(bbox_de)
