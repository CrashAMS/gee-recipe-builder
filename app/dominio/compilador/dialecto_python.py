"""Receta -> script Python (earthengine-api + eemont), renderizando el plan neutral."""
from app.dominio.receta import Receta
from app.dominio.receta import Salida as DestinoSalida
from app.dominio.compilador.base import geojson_py, reductor
from app.dominio.compilador.plan import (
    PlanCompilacion, Segmento, TipoPaso, construir_plan, unir)


def _params_kwargs(parametros: tuple[tuple[str, float], ...]) -> str:
    return "".join(f", {k}={v}" for k, v in parametros)


def _banda(bandas: tuple[str, ...]) -> str:
    if len(bandas) != 1:
        raise NotImplementedError("select multi-banda llega en F6b")
    return f"img.select({bandas[0]!r})"


def _cola_salida(plan: PlanCompilacion) -> list[str]:
    s = plan.paso(TipoPaso.SALIDA)
    banda = _banda(s.bandas)
    if s.tipo is DestinoSalida.DESCARGA:
        return [f"url = {banda}.getDownloadURL("
                f"{{'scale': {s.escala_m}, 'region': aoi, 'format': 'GEO_TIFF'}})",
                "print(url)"]
    if s.tipo is DestinoSalida.DRIVE:
        return [f"task = ee.batch.Export.image.toDrive("
                f"image={banda}, region=aoi, scale={s.escala_m}, description={s.descripcion!r})",
                "task.start()"]
    return [f"# preview: {banda}.getMapId(vis_params) -> tile URL (lo consume F3b)"]


def segmentos(plan: PlanCompilacion) -> list[Segmento]:
    fuente = plan.paso(TipoPaso.FUENTE)
    fechas = plan.paso(TipoPaso.FILTRO_FECHAS)
    nubes = plan.paso(TipoPaso.FILTRO_NUBES)
    mascara = plan.paso(TipoPaso.MASCARA)
    indices = plan.paso(TipoPaso.INDICES)
    segs: list[Segmento] = [((), ["import ee, eemont", "ee.Initialize()", ""])]

    # Fuente + fechas + nubes son una sola cadena: el cierre `)` va en el último filtro.
    filtro_fecha = f"       .filterDate({fechas.inicio!r}, {fechas.fin!r})"
    cadena = [f"aoi = ee.Geometry({geojson_py(fuente.geometria)})",
              f"col = (ee.ImageCollection({fuente.coleccion!r})",
              "       .filterBounds(aoi)"]
    if nubes:
        cadena += [filtro_fecha, f"       .filter(ee.Filter.lt({nubes.propiedad!r}, {nubes.umbral})))"]
        segs.append(((TipoPaso.FUENTE, TipoPaso.FILTRO_FECHAS, TipoPaso.FILTRO_NUBES), cadena))
    else:
        cadena.append(filtro_fecha + ")")
        segs.append(((TipoPaso.FUENTE, TipoPaso.FILTRO_FECHAS), cadena))

    # eemont encadena máscara y escala en una línea.
    tipos_me = ((TipoPaso.MASCARA,) if mascara else ()) + (TipoPaso.ESCALA,)
    segs.append((tipos_me, ["col = col." + ("maskClouds()." if mascara else "") + "scaleAndOffset()"]))
    nombres = ", ".join(repr(n) for n in indices.nombres)
    segs.append(((TipoPaso.INDICES,),
                 [f"col = col.spectralIndices([{nombres}]{_params_kwargs(indices.parametros)})"]))
    segs.append(((TipoPaso.REDUCTOR,),
                 [f"img = col.{reductor(plan.paso(TipoPaso.REDUCTOR).composicion)}.clip(aoi)"]))
    segs.append(((TipoPaso.SALIDA,), _cola_salida(plan)))
    return segs


def compilar(r: Receta) -> str:
    return unir(segmentos(construir_plan(r)))
