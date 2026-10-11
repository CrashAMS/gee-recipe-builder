"""CSV de la serie temporal (F8) y escritor único de CSV del producto (F9 lo reusa).

`filas_a_texto(encabezado, filas)` es el formateador genérico (coma, punto
decimal, `None` -> celda vacía); `filas_a_csv(filas, indices)` arma el de la
serie con columnas `periodo_inicio, periodo_fin, <indice>_mean..., n_imagenes`.
`escribir_csv(ruta, texto)` escribe con BOM (`utf-8-sig`, Excel lo abre bien).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class FilaSerie:
    """Un período de la serie: medias por índice (`None` = sin imágenes / sin dato)."""
    periodo_inicio: str
    periodo_fin: str
    n_imagenes: int
    medias: dict = field(default_factory=dict)   # {indice: float | None}


def columna_media(indice: str) -> str:
    return f"{indice}_mean"


def encabezado_serie(indices: Sequence[str]) -> list[str]:
    return ["periodo_inicio", "periodo_fin", *(columna_media(i) for i in indices), "n_imagenes"]


def _celda(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)              # punto decimal siempre (independiente del locale)
    return str(v)


def filas_a_texto(encabezado: Sequence[str], filas: Iterable[Sequence]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=",", lineterminator="\r\n")
    w.writerow(list(encabezado))
    for fila in filas:
        w.writerow([_celda(v) for v in fila])
    return buf.getvalue()


def filas_a_csv(filas: Iterable[FilaSerie], indices: Sequence[str]) -> str:
    return filas_a_texto(
        encabezado_serie(indices),
        ([f.periodo_inicio, f.periodo_fin, *(f.medias.get(i) for i in indices), f.n_imagenes]
         for f in filas))


def escribir_csv(ruta: str | Path, texto: str) -> None:
    """Único escritor de CSV del producto: utf-8 con BOM, coma, sin traducir saltos."""
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(texto)
