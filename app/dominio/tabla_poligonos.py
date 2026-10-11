"""Tabla por polígono (F9): columnas, filas y CSV. Dominio puro, sin Qt ni GEE.

La tabla tiene una fila por feature del shapefile/GeoJSON: primero sus properties
(orden del primer feature, unión estable) y luego, por índice y en el orden de la
receta, `<indice>_mean, _min, _max, _std, _n`. Sin geometría ni `system:index`.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from app.dominio import serie_csv
from app.dominio.errores import ColumnaTablaEnConflicto, TablaSinPoligonos

# ≤ UMBRAL_TABLA_LOCAL features: getInfo + CSV local; más: Export.table.toDrive.
UMBRAL_TABLA_LOCAL = 500

# Sufijos de salida (orden fijo) y su nombre en el reducer combinado de GEE.
SUFIJOS: tuple[str, ...] = ("mean", "min", "max", "std", "n")
SALIDAS_REDUCER: tuple[str, ...] = ("mean", "min", "max", "stdDev", "count")


def columnas_estadistica(indice: str) -> list[str]:
    return [f"{indice}_{s}" for s in SUFIJOS]


def nombres_propiedades(fc: dict) -> list[str]:
    """Properties del shapefile: unión estable (orden de aparición, primer feature primero)."""
    vistos: dict[str, None] = {}
    for f in fc.get("features", []):
        for k in (f.get("properties") or {}):
            vistos.setdefault(k, None)
    return list(vistos)


def columnas_salida(props: Iterable[str], indices: Sequence[str]) -> list[str]:
    """Columnas del CSV/tabla. Una property que colisiona con una columna de estadística
    levanta `ColumnaTablaEnConflicto` (antes de tocar GEE)."""
    props = list(props)
    stats = [c for i in indices for c in columnas_estadistica(i)]
    choques = [p for p in props if p in set(stats)]
    if choques:
        raise ColumnaTablaEnConflicto(
            f"El archivo ya tiene columna(s) {', '.join(repr(c) for c in choques)}, que se "
            "usarían para las estadísticas: renombrala(s) en el shapefile.")
    return props + stats


def columnas_para(fc: dict, indices: Sequence[str]) -> list[str]:
    return columnas_salida(nombres_propiedades(fc), indices)


def es_local(fc: dict) -> bool:
    """True si la tabla cabe en la rama local (`getInfo` + CSV). Lee el umbral al llamar."""
    return len(fc.get("features", [])) <= UMBRAL_TABLA_LOCAL


def exigir_poligonos(fc: dict | None) -> dict:
    if not isinstance(fc, dict) or not fc.get("features"):
        raise TablaSinPoligonos(
            "La tabla por polígono necesita un shapefile o GeoJSON con polígonos "
            "(no sirve un rectángulo ni un dibujo).")
    return fc


def filas_desde_info(fc_info: dict, columnas: Sequence[str]) -> list[list]:
    """`getInfo` de la FeatureCollection ya seleccionada -> filas en el orden de `columnas`.
    Una columna ausente o nula (polígono sin píxeles) queda `None` (celda vacía)."""
    filas = []
    for f in fc_info.get("features", []):
        props = f.get("properties") or {}
        filas.append([props.get(c) for c in columnas])
    return filas


def filas_a_texto(filas: Iterable[Sequence], columnas: Sequence[str]) -> str:
    """CSV (coma, punto decimal, `None` -> vacío); el escritor a disco es `serie_csv.escribir_csv`."""
    return serie_csv.filas_a_texto(columnas, filas)
