"""Modelo de receta: el input único del CompiladorReceta."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Composicion(str, Enum):
    MEDIANA = "median"
    MEDIA = "mean"
    MAXIMO = "max"
    MINIMO = "min"
    MOSAICO = "mosaic"


class Salida(str, Enum):
    DESCARGA = "descarga"      # getDownloadURL (<=32MB)
    DRIVE = "drive"            # Export.image.toDrive
    PREVIEW = "preview"        # Map.addLayer / getMapId


@dataclass(frozen=True)
class Receta:
    sensor: str                     # collection ID exacto
    indice: str                     # short_name ASI
    geometria: dict                 # GeoJSON geometry dict (salida de FuenteAOI)
    fecha_inicio: str               # 'YYYY-MM-DD'
    fecha_fin: str
    mascara_nubes: bool
    composicion: Composicion
    salida: Salida
    escala: int = 10                # scale en metros
    parametros: dict[str, float] = field(default_factory=dict)  # overrides de defaults

    def __post_init__(self):
        """Coacciona `composicion`/`salida` a sus enums si llegan como str desde la UI
        (F3a arma la Receta con valores de widgets, no siempre con el enum en mano).
        `object.__setattr__` porque la dataclass es frozen."""
        if not isinstance(self.composicion, Composicion):
            object.__setattr__(self, "composicion", Composicion(self.composicion))
        if not isinstance(self.salida, Salida):
            object.__setattr__(self, "salida", Salida(self.salida))
