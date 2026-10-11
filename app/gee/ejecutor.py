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
    indices: list[str]                   # short_names ASI = bandas de salida, en orden
    mascara_nubes: bool
    reduccion: str
    scale: float
    crs: str = "EPSG:4326"
    params_indice: dict = field(default_factory=dict)
    propiedad_nubes: str | None = None   # propiedad GEE de % nubes (viene del perfil de sensor)
    max_nubes_pct: int | None = None     # descarta escenas con nubes >= X %; None = sin filtro


def _coleccion_base(sol: SolicitudEjecucion) -> "ee.ImageCollection":
    """Colección filtrada por bounds + fechas (sin filtro de nubes, sin máscara)."""
    return (
        ee.ImageCollection(sol.collection_id)
        .filterBounds(sol.aoi)
        .filterDate(sol.fecha_inicio, sol.fecha_fin)
    )


def construir_coleccion(sol: SolicitudEjecucion) -> "ee.ImageCollection":
    """Todo lo previo a la reducción (F8): bounds + fechas → filtro de nubes → mask →
    scale → índices (por imagen). Lo comparten `construir_imagen` y la serie temporal."""
    col = _coleccion_base(sol)
    if sol.max_nubes_pct is not None and sol.propiedad_nubes:
        col = col.filter(ee.Filter.lt(sol.propiedad_nubes, sol.max_nubes_pct))
    if sol.mascara_nubes:
        col = col.maskClouds()
    col = col.scaleAndOffset()
    return col.spectralIndices(list(sol.indices), **sol.params_indice)


def _validar_reduccion(sol: SolicitudEjecucion) -> None:
    if sol.reduccion not in _REDUCTORES:
        raise ValueError(f"Reducción no soportada: {sol.reduccion!r} (opciones: {list(_REDUCTORES)})")


def construir_imagen(sol: SolicitudEjecucion) -> ee.Image:
    """Pipeline [decisión #9]: mask → scale → index (por imagen) → reduce → select → clip."""
    _validar_reduccion(sol)
    col = construir_coleccion(sol)
    imagen = _REDUCTORES[sol.reduccion](col).select(list(sol.indices))
    return imagen.clip(sol.aoi)


def serie_periodo(col: "ee.ImageCollection", sol: SolicitudEjecucion, ini: str,
                  fin: str) -> tuple[int, dict[str, float | None]]:
    """Un período de la serie temporal (F8) sobre la colección de `construir_coleccion`:
    filtra `[ini, fin)`, compone con `sol.reduccion` y promedia cada índice sobre el AOI.
    `size` y medias se resuelven en UN solo `getInfo`. Sin imágenes no reduce
    (`ee.Algorithms.If` server-side) y las medias son None; una clave ausente en
    `reduceRegion` (todo enmascarado) también es None."""
    _validar_reduccion(sol)
    sub = col.filterDate(ini, fin)
    n = sub.size()
    medias = _REDUCTORES[sol.reduccion](sub).select(list(sol.indices)).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=sol.aoi, scale=sol.scale, maxPixels=1e9)
    res = ee.Dictionary({"n": n, "medias": ee.Algorithms.If(n.gt(0), medias, ee.Dictionary({}))}
                        ).getInfo()
    n_imagenes = int(res.get("n") or 0)
    valores = res.get("medias") or {}
    return n_imagenes, {i: (valores.get(i) if n_imagenes else None) for i in sol.indices}


def contar_imagenes(sol: SolicitudEjecucion, umbral: int) -> tuple[int, int | None]:
    """(total, con_pocas_nubes) de escenas en bounds+fechas, en UNA sola ida a GEE.
    Ignora `sol.max_nubes_pct`: `umbral` es el X de "< X % nubes". Sin propiedad de
    nubes en el sensor (MODIS) el segundo valor es None."""
    col = _coleccion_base(sol)
    partes = {"total": col.size()}
    if sol.propiedad_nubes:
        partes["pocas"] = col.filter(ee.Filter.lt(sol.propiedad_nubes, umbral)).size()
    res = ee.Dictionary(partes).getInfo()
    return int(res["total"]), (int(res["pocas"]) if "pocas" in res else None)


# Alias público: F3b (mapa interactivo, getMapId) y F4 (export a Drive) solo
# necesitan la ee.Image ya compuesta, no la descarga a disco. `construir_imagen`
# se mantiene como nombre interno; `imagen_indice` es el punto de entrada estable
# para consumidores fuera de este módulo.
imagen_indice = construir_imagen


def verificar_banda_presente(imagen: ee.Image, bandas_esperadas: list[str]) -> None:
    """Convierte el fallo silencioso de eemont [HALLAZGO-2.3] en error ruidoso.
    Un solo `getInfo` para todas las bandas; el mensaje nombra todas las faltantes."""
    bandas = imagen.bandNames().getInfo()
    faltantes = [b for b in bandas_esperadas if b not in bandas]
    if faltantes:
        nombres = ", ".join(f"'{b}'" for b in faltantes)
        raise BandaAusente(
            f"{'El índice' if len(faltantes) == 1 else 'Los índices'} {nombres} no "
            f"{'está' if len(faltantes) == 1 else 'están'} en la imagen (bandas presentes: {bandas}). "
            "Probable incompatibilidad índice+sensor que el pre-chequeo del catálogo debió filtrar."
        )


def ejecutar_a_disco(sol: SolicitudEjecucion, ruta_destino: str) -> str:
    """Corre la receta y baja el .tif. Pre-chequea tamaño (F1) y banda presente."""
    imagen = construir_imagen(sol)
    verificar_banda_presente(imagen, sol.indices)  # [decisión #6]

    # Pre-chequeo proactivo de tamaño [decisión #4 / HALLAZGO-1.4].
    # estimador.estimar_tamano_descarga es dominio puro (F1) y NO acepta ee.Geometry:
    # resolvemos el bbox lon/lat client-side (.bounds().getInfo()) ANTES de llamarlo.
    coords = sol.aoi.bounds().getInfo()["coordinates"][0]
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    bbox_lonlat = (min(lons), min(lats), max(lons), max(lats))
    est = estimador.estimar_tamano_descarga(
        bbox_lonlat=bbox_lonlat, escala_m=sol.scale, n_bandas=len(sol.indices), dtype="float32"
    )
    if est.excede:
        raise DescargaExcedeLimite(
            f"La descarga estimada excede el límite (32MB/10000px): "
            f"{est.ancho_px}x{est.alto_px}px ≈ {est.bytes_estimados} bytes "
            f"(excede_bytes={est.excede_bytes}, excede_lado={est.excede_lado}). "
            "Usá el export a Google Drive (Salida: Drive / Cloud) o subí `scale` / achicá el AOI."
        )

    return descargar_imagen(imagen, sol.aoi, sol.scale, sol.crs, ruta_destino)
