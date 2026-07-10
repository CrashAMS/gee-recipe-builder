"""Receta -> script Python (earthengine-api + eemont)."""
from app.dominio.receta import Receta, Salida
from app.dominio.compilador.base import geojson_py, reductor


def _params_kwargs(params: dict) -> str:
    return "".join(f", {k}={v}" for k, v in sorted(params.items())) if params else ""


def _cola_salida(r: Receta) -> list[str]:
    banda = f"img.select({r.indice!r})"
    if r.salida is Salida.DESCARGA:
        return [f"url = {banda}.getDownloadURL("
                f"{{'scale': {r.escala}, 'region': aoi, 'format': 'GEO_TIFF'}})",
                "print(url)"]
    if r.salida is Salida.DRIVE:
        return [f"task = ee.batch.Export.image.toDrive("
                f"image={banda}, region=aoi, scale={r.escala}, description={r.indice!r})",
                "task.start()"]
    return [f"# preview: {banda}.getMapId(vis_params) -> tile URL (lo consume F3b)"]


def compilar(r: Receta) -> str:
    L = ["import ee, eemont", "ee.Initialize()", "",
         f"aoi = ee.Geometry({geojson_py(r.geometria)})",
         f"col = (ee.ImageCollection({r.sensor!r})",
         "       .filterBounds(aoi)",
         f"       .filterDate({r.fecha_inicio!r}, {r.fecha_fin!r}))"]
    L.append("col = col." + ("maskClouds()." if r.mascara_nubes else "") + "scaleAndOffset()")
    L.append(f"col = col.spectralIndices([{r.indice!r}]{_params_kwargs(r.parametros)})")
    L.append(f"img = col.{reductor(r.composicion)}.clip(aoi)")
    L += _cola_salida(r)
    return "\n".join(L)
