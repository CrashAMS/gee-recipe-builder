"""Preview del índice: construir la imagen + getMapId, todo en el mismo QThread
(HALLAZGO-2.3, 2.4).

El cliente `ee` no tolera bien repartir `asegurar_sesion`/construcción de la imagen en
un hilo y `getMapId` en otro: se observó en vivo que `getMapId` queda colgado
indefinidamente (0% CPU, sin excepción) al partir el pipeline en dos hilos distintos.
Por eso `PreviewWorker` recibe un *callable* que arma la ee.Image (auth incluida) y lo
ejecuta en el mismo hilo que `getMapId` — mismo patrón de hilo único que `WorkerDescarga`
(F2), que sí funciona end-to-end."""
from PySide6.QtCore import QObject, Signal

# Paleta default (decisión #13). El min/max se AUTO-AJUSTA al rango real del índice por
# defecto (ver `auto_stretch`): una rampa fija 0→1 deja casi todos los índices reales
# (que viven en sub-rangos angostos: NDVI de invierno 0.16–0.34, AFRI1600 0.13–0.50, …)
# como un lavado pálido invisible. El criterio del workflow exige ver *cualquier* índice.
VIS_PARAMS_DEFAULT = {"min": 0, "max": 1, "palette": ["white", "green"]}

# Escala (m) del reduceRegion que estima el rango para el stretch. Grosera a propósito:
# el preview solo necesita un min/max aproximado, no precisión — así es rápido.
_ESCALA_STRETCH_M = 100


class PreviewWorker(QObject):
    """Corre en un QThread (mismo patrón de red que EjecutorGEE, F2)."""

    listo = Signal(str)    # tile_fetcher.url_format
    error = Signal(str)

    def __init__(self, construir_imagen, vis_params=None, auto_stretch=True):
        """`construir_imagen`: callable sin argumentos que asegura la sesión GEE y
        devuelve la ee.Image ya armada — se llama DENTRO de este hilo.
        `auto_stretch`: si True, estira min/max de la paleta al rango real del índice."""
        super().__init__()
        self._construir_imagen = construir_imagen
        self._vis = dict(vis_params or VIS_PARAMS_DEFAULT)
        self._auto_stretch = auto_stretch

    def _estirar_al_rango_real(self, imagen) -> None:
        """Sobrescribe vis['min']/['max'] con el min/max real del índice sobre el AOI.
        Si el cálculo falla o es degenerado, deja el vis como está (fallback silencioso)."""
        import ee

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
                self._vis["min"], self._vis["max"] = mins[0], maxs[0]
        except Exception:  # noqa: BLE001 — el stretch es best-effort; nunca debe romper el preview
            pass

    def run(self):
        try:
            import ee
            imagen = ee.Image(self._construir_imagen())
            if self._auto_stretch:
                self._estirar_al_rango_real(imagen)
            map_id = imagen.getMapId(self._vis)
            self.listo.emit(map_id["tile_fetcher"].url_format)   # patrón exacto de geemap
        except Exception as exc:                                  # noqa: BLE001 — reportar crudo al UI
            self.error.emit(str(exc))
