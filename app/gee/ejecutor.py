"""EjecutorGEE síncrono: pipeline eemont → descarga .tif — F2."""
from dataclasses import dataclass, field

import ee
import eemont  # noqa: F401  (monkeypatcha ee.ImageCollection / ee.Image)

from app.dominio import estimador  # F1 [HALLAZGO-1.4] — ver nota abajo
from .descarga import descargar_imagen
from .errores import DescargaExcedeLimite, ErrorEjecucionGEE

_REDUCTORES = {
    "median": lambda c: c.median(),
    "mean": lambda c: c.mean(),
    "min": lambda c: c.min(),
    "max": lambda c: c.max(),
    "mosaic": lambda c: c.mosaic(),
}


class BandaAusente(ErrorEjecucionGEE):
    """El índice no quedó en la imagen (fallo silencioso de eemont, [HALLAZGO-2.3])."""


@dataclass
class SolicitudEjecucion:
    collection_id: str
    aoi: "ee.Geometry"
    fecha_inicio: str
    fecha_fin: str
    indice: str
    mascara_nubes: bool
    reduccion: str
    scale: float
    crs: str = "EPSG:4326"
    params_indice: dict = field(default_factory=dict)


def construir_imagen(sol: SolicitudEjecucion) -> ee.Image:
    """Pipeline [decisión #9]: mask → scale → index (por imagen) → reduce → select → clip."""
    if sol.reduccion not in _REDUCTORES:
        raise ValueError(f"Reducción no soportada: {sol.reduccion!r} (opciones: {list(_REDUCTORES)})")
    col = (
        ee.ImageCollection(sol.collection_id)
        .filterBounds(sol.aoi)
        .filterDate(sol.fecha_inicio, sol.fecha_fin)
    )
    if sol.mascara_nubes:
        col = col.maskClouds()
    col = col.scaleAndOffset()
    col = col.spectralIndices([sol.indice], **sol.params_indice)
    imagen = _REDUCTORES[sol.reduccion](col).select(sol.indice)
    return imagen.clip(sol.aoi)


# Alias público: F3b (mapa interactivo, getMapId) y F4 (export a Drive) solo
# necesitan la ee.Image ya compuesta, no la descarga a disco. `construir_imagen`
# se mantiene como nombre interno; `imagen_indice` es el punto de entrada estable
# para consumidores fuera de este módulo.
imagen_indice = construir_imagen


def verificar_banda_presente(imagen: ee.Image, banda: str) -> None:
    """Convierte el fallo silencioso de eemont [HALLAZGO-2.3] en error ruidoso."""
    bandas = imagen.bandNames().getInfo()
    if banda not in bandas:
        raise BandaAusente(
            f"El índice '{banda}' no está en la imagen (bandas presentes: {bandas}). "
            "Probable incompatibilidad índice+sensor que el pre-chequeo de F1 debió filtrar."
        )


def ejecutar_a_disco(sol: SolicitudEjecucion, ruta_destino: str) -> str:
    """Corre la receta y baja el .tif. Pre-chequea tamaño (F1) y banda presente."""
    imagen = construir_imagen(sol)
    verificar_banda_presente(imagen, sol.indice)  # [decisión #6]

    # Pre-chequeo proactivo de tamaño [decisión #4 / HALLAZGO-1.4].
    # estimador.estimar_tamano_descarga es dominio puro (F1) y NO acepta ee.Geometry:
    # resolvemos el bbox lon/lat client-side (.bounds().getInfo()) ANTES de llamarlo.
    coords = sol.aoi.bounds().getInfo()["coordinates"][0]
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    bbox_lonlat = (min(lons), min(lats), max(lons), max(lats))
    est = estimador.estimar_tamano_descarga(
        bbox_lonlat=bbox_lonlat, escala_m=sol.scale, n_bandas=1, dtype="float32"
    )
    if est.excede:
        raise DescargaExcedeLimite(
            f"La descarga estimada excede el límite (32MB/10000px): "
            f"{est.ancho_px}x{est.alto_px}px ≈ {est.bytes_estimados} bytes "
            f"(excede_bytes={est.excede_bytes}, excede_lado={est.excede_lado}). "
            "Usá el export a Drive (F4) o subí `scale` / achicá el AOI."
        )

    return descargar_imagen(imagen, sol.aoi, sol.scale, sol.crs, ruta_destino)
