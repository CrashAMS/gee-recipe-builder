"""Preview del índice: getMapId → PreviewResultado, con auto-ajuste de la paleta al rango real.

El getMapId corre en un worker de fondo (`WorkerPreview` en `app.ui.workers`, sobre
QThreadPool — el mismo patrón que la descarga de F2, robusto y ya probado). Todo el
pipeline GEE (auth + construir imagen + stretch + getMapId) corre en ese único hilo:
partirlo entre dos hilos cuelga `getMapId` indefinidamente (visto en vivo).

Este módulo expone solo las funciones puras de armado del preview; el worker Qt vive
en `app.ui.workers` para no arrastrar dependencia de UI acá."""
from __future__ import annotations

from dataclasses import dataclass

# Paleta default (decisión #13). El min/max se AUTO-AJUSTA al rango real del índice por
# defecto (ver `estirar_vis_al_rango`): una rampa fija 0→1 deja casi todos los índices
# reales (que viven en sub-rangos angostos: NDVI de invierno 0.16–0.34, AFRI1600
# 0.13–0.50, …) como un lavado pálido invisible. El criterio del workflow exige ver
# *cualquier* índice del catálogo.
VIS_PARAMS_DEFAULT = {"min": 0, "max": 1, "palette": ["white", "green"]}

# Escala (m) del reduceRegion que estima el rango para el stretch. Grosera a propósito:
# el preview solo necesita un min/max aproximado, no precisión — así es rápido.
_ESCALA_STRETCH_M = 100

# Paletas predefinidas (solo UI: no entran en Receta ni en los scripts). Hex sin '#' (formato GEE).
PALETAS: dict[str, list[str]] = {
    "vegetación": ["FFFFFF", "CE7E45", "FCD163", "66A000", "207401", "056201", "011301"],
    "agua": ["FFFFFF", "C6DBEF", "6BAED6", "2171B5", "08306B"],
    "quemado": ["FFFFB2", "FECC5C", "FD8D3C", "E31A1C", "800026"],
    "suelo": ["FFF7EC", "FDD49E", "FC8D59", "B30000", "7F2704"],
    "nieve": ["000000", "3182BD", "9ECAE1", "DEEBF7", "FFFFFF"],
    "genérica": ["440154", "3B528B", "21908C", "5DC863", "FDE725"],
}
PALETA_GENERICA = "genérica"
_PALETA_POR_DOMINIO = {
    "vegetation": "vegetación", "water": "agua", "burn": "quemado",
    "soil": "suelo", "snow": "nieve",
}


@dataclass(frozen=True)
class PreviewResultado:
    """Lo que el worker entrega a la UI: tiles + el vis realmente usado + si el rango
    es el estimado por percentiles (False = fallback/override, no es un rango medido)."""
    url: str
    vis: dict
    estirado: bool


def paleta_por_dominio(dominio: str | None) -> str:
    """Nombre de la paleta default para un `application_domain`; genérica si no hay una."""
    return _PALETA_POR_DOMINIO.get(dominio or "", PALETA_GENERICA)


def vis_para_leyenda(vis: dict) -> dict:
    """Copia del vis con los colores listos para CSS: hex (3/6/8 dígitos) con prefijo '#',
    nombres CSS ('white') intactos. La normalización vive acá para que el JS quede tonto."""
    salida = dict(vis)
    salida["palette"] = [_color_css(c) for c in vis.get("palette", [])]
    return salida


def _color_css(c: str) -> str:
    c = str(c).strip()
    if c.startswith("#"):
        return c
    if len(c) in (3, 6, 8) and all(ch in "0123456789abcdefABCDEF" for ch in c):
        return "#" + c
    return c


def estirar_vis_al_rango(imagen, vis: dict) -> tuple[dict, bool]:
    """Devuelve (copia de `vis` con min/max en los percentiles 2-98 del índice sobre el AOI,
    estirado). `estirado` es False si el cálculo falla o es degenerado (p2 >= p98): en ese caso
    el vis sale sin tocar (fallback best-effort: el stretch nunca debe romper el preview) y la
    UI no debe presentarlo como rango real."""
    import ee

    vis = dict(vis)
    try:
        stats = imagen.reduceRegion(
            reducer=ee.Reducer.percentile([2, 98]),
            geometry=imagen.geometry(),
            scale=_ESCALA_STRETCH_M,
            maxPixels=int(1e9),
            bestEffort=True,
        ).getInfo() or {}
        lo = [v for k, v in stats.items() if k.endswith("_p2") and v is not None]
        hi = [v for k, v in stats.items() if k.endswith("_p98") and v is not None]
        if lo and hi and hi[0] > lo[0]:
            vis["min"], vis["max"] = lo[0], hi[0]
            return vis, True
    except Exception:  # noqa: BLE001 — best-effort; nunca romper el preview por el stretch
        pass
    return vis, False


def url_tiles_para(imagen, vis_params: dict | None = None, auto_stretch: bool = True) -> PreviewResultado:
    """Dada una ee.Image ya compuesta, devuelve `PreviewResultado(url, vis, estirado)` con la
    URL de tiles (`tile_fetcher.url_format`) lista para `L.tileLayer`. Con `auto_stretch`
    estira min/max por percentiles; sin él (override manual) usa `vis_params` tal cual y
    `estirado` queda False. Debe llamarse dentro del worker (hace I/O de red)."""
    import ee

    imagen = ee.Image(imagen)
    vis = dict(vis_params or VIS_PARAMS_DEFAULT)
    estirado = False
    if auto_stretch:
        vis, estirado = estirar_vis_al_rango(imagen, vis)
    url = imagen.getMapId(vis)["tile_fetcher"].url_format   # patrón exacto de geemap
    return PreviewResultado(url=url, vis=vis, estirado=estirado)
