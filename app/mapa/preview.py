"""Preview del índice: getMapId → url_format, con auto-ajuste de la paleta al rango real.

El getMapId corre en un worker de fondo (`WorkerPreview` en `app.ui.workers`, sobre
QThreadPool — el mismo patrón que la descarga de F2, robusto y ya probado). Todo el
pipeline GEE (auth + construir imagen + stretch + getMapId) corre en ese único hilo:
partirlo entre dos hilos cuelga `getMapId` indefinidamente (visto en vivo).

Este módulo expone solo las funciones puras de armado del preview; el worker Qt vive
en `app.ui.workers` para no arrastrar dependencia de UI acá."""

# Paleta default (decisión #13). El min/max se AUTO-AJUSTA al rango real del índice por
# defecto (ver `estirar_vis_al_rango`): una rampa fija 0→1 deja casi todos los índices
# reales (que viven en sub-rangos angostos: NDVI de invierno 0.16–0.34, AFRI1600
# 0.13–0.50, …) como un lavado pálido invisible. El criterio del workflow exige ver
# *cualquier* índice del catálogo.
VIS_PARAMS_DEFAULT = {"min": 0, "max": 1, "palette": ["white", "green"]}

# Escala (m) del reduceRegion que estima el rango para el stretch. Grosera a propósito:
# el preview solo necesita un min/max aproximado, no precisión — así es rápido.
_ESCALA_STRETCH_M = 100


def estirar_vis_al_rango(imagen, vis: dict) -> dict:
    """Devuelve una copia de `vis` con min/max estirados al rango real del índice sobre
    el AOI. Si el cálculo falla o es degenerado (min==max), devuelve el vis sin tocar
    (fallback best-effort: el stretch nunca debe romper el preview)."""
    import ee

    vis = dict(vis)
    try:
        stats = imagen.reduceRegion(
            reducer=ee.Reducer.minMax(),
            geometry=imagen.geometry(),
            scale=_ESCALA_STRETCH_M,
            maxPixels=int(1e9),
            bestEffort=True,
        ).getInfo() or {}
        mins = [v for k, v in stats.items() if k.endswith("_min") and v is not None]
        maxs = [v for k, v in stats.items() if k.endswith("_max") and v is not None]
        if mins and maxs and maxs[0] > mins[0]:
            vis["min"], vis["max"] = mins[0], maxs[0]
    except Exception:  # noqa: BLE001 — best-effort; nunca romper el preview por el stretch
        pass
    return vis


def url_tiles_para(imagen, vis_params: dict | None = None, auto_stretch: bool = True) -> str:
    """Dada una ee.Image ya compuesta, devuelve la URL de tiles (`tile_fetcher.url_format`)
    lista para `L.tileLayer`. Aplica auto-stretch de la paleta por defecto. Debe llamarse
    dentro del worker (hace I/O de red: reduceRegion + getMapId)."""
    import ee

    imagen = ee.Image(imagen)
    vis = dict(vis_params or VIS_PARAMS_DEFAULT)
    if auto_stretch:
        vis = estirar_vis_al_rango(imagen, vis)
    return imagen.getMapId(vis)["tile_fetcher"].url_format   # patrón exacto de geemap
