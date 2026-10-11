"""Receta -> script Python (earthengine-api + eemont), renderizando el plan neutral."""
from app.dominio.receta import Receta
from app.dominio.receta import Salida as DestinoSalida
from app.dominio.compilador.base import geojson_py, reducer_tabla_py, reductor
from app.dominio.compilador.plan import (
    PlanCompilacion, Segmento, Serie, Tabla, TipoPaso, construir_plan, unir,
    verificar_tipos)


def _params_kwargs(parametros: tuple[tuple[str, float], ...]) -> str:
    return "".join(f", {k}={v}" for k, v in parametros)


# Tipos que este renderer sabe emitir (lista explícita: un TipoPaso nuevo falla ruidoso).
_RENDERIZA = frozenset({
    TipoPaso.FUENTE, TipoPaso.FILTRO_FECHAS, TipoPaso.FILTRO_NUBES, TipoPaso.MASCARA,
    TipoPaso.ESCALA, TipoPaso.INDICES, TipoPaso.REDUCTOR, TipoPaso.SALIDA, TipoPaso.SERIE,
    TipoPaso.TABLA})


def _banda(bandas: tuple[str, ...]) -> str:
    """Un índice -> select('X') (texto previo a F6b); varios -> select([...]) en orden."""
    if len(bandas) == 1:
        return f"img.select({bandas[0]!r})"
    return f"img.select({list(bandas)!r})"


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
    # Preview muestra solo el primer índice (F7 decide qué banda previsualizar).
    return [f"# preview: {_banda(s.bandas[:1])}.getMapId(vis_params) -> tile URL (lo consume F3b)"]


def _serie(s: Serie) -> list[str]:
    """Serie temporal (F8): períodos literales del generador -> FeatureCollection con las
    columnas del CSV de la app (`periodo_inicio`, `periodo_fin`, `<indice>_mean`, `n_imagenes`)."""
    lineas = ["periodos = ["] + [f"    ({ini!r}, {fin!r})," for ini, fin in s.periodos] + ["]", ""]
    bandas = list(s.indices)
    lineas += [
        "",
        "def fila(ini, fin):",
        "    sub = col.filterDate(ini, fin)",
        "    n = sub.size()",
        f"    medias = ee.Dictionary(ee.Algorithms.If(n.gt(0), sub.{reductor(s.reductor)}"
        f".select({bandas!r}).reduceRegion(",
        f"        reducer=ee.Reducer.mean(), geometry=aoi, scale={s.escala_m}, maxPixels=1e9), {{}}))",
        "    props = {'periodo_inicio': ini, 'periodo_fin': fin}",
    ]
    for i in s.indices:
        lineas.append(f"    props[{i + '_mean'!r}] = ee.Algorithms.If("
                      f"medias.contains({i!r}), medias.get({i!r}), None)")
    lineas += [
        "    props['n_imagenes'] = n",
        "    return ee.Feature(None, props)",
        "",
        "",
        "serie = ee.FeatureCollection([fila(ini, fin) for ini, fin in periodos])",
        "print(serie.getInfo())",
    ]
    return lineas


def _tabla(t: Tabla) -> list[str]:
    """Tabla por polígono (F9): un `reduceRegions` por índice encadenado sobre la FC, `select`
    sin geometría y cierre según rama (local: print · drive: Export.table.toDrive)."""
    columnas = list(t.columnas)
    lineas = [f"poligonos = ee.FeatureCollection({geojson_py(t.poligonos)})", "tabla = poligonos"]
    for i in t.indices:
        r = reducer_tabla_py(i)
        lineas += [f"tabla = img.select({i!r}).reduceRegions(",
                   "    collection=tabla,",
                   f"    reducer=({r[0]}"]
        lineas += [f"    {x}" for x in r[1:-1]]
        lineas += [f"    {r[-1]}),", f"    scale={t.escala_m})"]
    lineas.append(f"tabla = tabla.select({columnas!r}, None, False)")
    if t.rama == "local":
        lineas.append("print(tabla.getInfo())")
    else:
        lineas += [f"task = ee.batch.Export.table.toDrive(collection=tabla, description={t.descripcion!r}, "
                   f"fileFormat='CSV', selectors={columnas!r})",
                   "task.start()"]
    return lineas


def segmentos(plan: PlanCompilacion) -> list[Segmento]:
    verificar_tipos(plan, _RENDERIZA)
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
    serie = plan.paso(TipoPaso.SERIE)
    if serie:
        segs.append(((TipoPaso.SERIE,), _serie(serie)))
        return segs
    segs.append(((TipoPaso.REDUCTOR,),
                 [f"img = col.{reductor(plan.paso(TipoPaso.REDUCTOR).composicion)}.clip(aoi)"]))
    tabla = plan.paso(TipoPaso.TABLA)
    if tabla:
        segs.append(((TipoPaso.TABLA,), _tabla(tabla)))
        return segs
    segs.append(((TipoPaso.SALIDA,), _cola_salida(plan)))
    return segs


def compilar(r: Receta) -> str:
    return unir(segmentos(construir_plan(r)))
