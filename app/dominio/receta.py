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


class Producto(str, Enum):
    IMAGEN = "imagen"                      # GeoTIFF (una banda por índice)
    SERIE_TEMPORAL = "serie_temporal"      # serie por período (F8)
    TABLA_POLIGONOS = "tabla_poligonos"    # estadística por polígono (F9)


# Períodos de agregación de la serie temporal (solo con producto == serie_temporal).
PERIODOS: tuple[str, ...] = ("mensual", "16_dias", "anual")


def nombre_bandas(indices) -> str:
    """Nombre compuesto de las bandas: `'-'.join(indices)`. Con un solo índice es
    el short_name tal cual ('-' deja '_' libre para separar fechas en el nombre)."""
    return "-".join(indices)


@dataclass(frozen=True)
class Receta:
    sensor: str                     # collection ID exacto
    indices: list[str]              # short_names ASI, en orden de bandas de salida
    geometria: dict                 # GeoJSON geometry dict (salida de FuenteAOI)
    fecha_inicio: str               # 'YYYY-MM-DD'
    fecha_fin: str
    mascara_nubes: bool
    composicion: Composicion
    salida: Salida
    escala: int = 10                # scale en metros
    parametros: dict[str, float] = field(default_factory=dict)  # overrides de defaults
    max_nubes_pct: int | None = None  # descarta escenas con nubes >= X %; None = sin filtro
    producto: Producto = Producto.IMAGEN
    periodo: str | None = None      # uno de PERIODOS sii producto == serie_temporal
    # FeatureCollection GeoJSON (4326) con los polígonos de la tabla; solo con tabla_poligonos.
    # `geometria` sigue siendo la unión disuelta (filterBounds/clip).
    features: dict | None = None

    def __post_init__(self):
        """Coacciona `composicion`/`salida`/`producto` a sus enums si llegan como str
        desde la UI (F3a arma la Receta con valores de widgets, no siempre con el enum
        en mano). Normaliza `indices` a list. `object.__setattr__` porque es frozen."""
        ind = self.indices
        if isinstance(ind, str):
            raise ValueError(
                f"indices debe ser una lista de short_names (ej. ['{ind}']), no un str suelto.")
        if not isinstance(ind, (list, tuple)):
            raise ValueError(f"indices debe ser una lista de short_names; recibí {ind!r}.")
        if not ind:
            raise ValueError("indices no puede estar vacía: elegí al menos un índice.")
        if not all(isinstance(i, str) for i in ind):
            raise ValueError(f"indices solo admite short_names (str); recibí {list(ind)!r}.")
        repetidos = sorted({i for i in ind if list(ind).count(i) > 1})
        if repetidos:
            raise ValueError(f"indices tiene duplicados: {', '.join(repetidos)}.")
        if not isinstance(ind, list):
            object.__setattr__(self, "indices", list(ind))
        m = self.max_nubes_pct
        if m is not None and (isinstance(m, bool) or not isinstance(m, int) or not 0 <= m <= 100):
            raise ValueError(
                f"max_nubes_pct debe ser un entero entre 0 y 100 (o None para no filtrar); recibí {m!r}.")
        if not isinstance(self.composicion, Composicion):
            object.__setattr__(self, "composicion", Composicion(self.composicion))
        if not isinstance(self.salida, Salida):
            object.__setattr__(self, "salida", Salida(self.salida))
        if not isinstance(self.producto, Producto):
            object.__setattr__(self, "producto", Producto(self.producto))
        if self.producto is Producto.SERIE_TEMPORAL:
            if self.periodo not in PERIODOS:
                raise ValueError(
                    f"La serie temporal necesita un periodo entre {', '.join(PERIODOS)}; "
                    f"recibí {self.periodo!r}.")
        elif self.periodo is not None:
            raise ValueError(
                f"periodo solo aplica a la serie temporal; con producto "
                f"'{self.producto.value}' debe ser None (recibí {self.periodo!r}).")
        if self.features is not None:
            fc = self.features
            if not (isinstance(fc, dict) and fc.get("type") == "FeatureCollection"
                    and isinstance(fc.get("features"), list)):
                raise ValueError("features debe ser una FeatureCollection GeoJSON.")
            if self.producto is not Producto.TABLA_POLIGONOS:
                raise ValueError(
                    f"features solo aplica a la tabla por polígono; con producto "
                    f"'{self.producto.value}' debe ser None.")
