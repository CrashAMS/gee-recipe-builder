"""Receta -> script JS (Code Editor + módulo users/dmlmont/spectral)."""
from app.dominio.receta import Receta, Salida
from app.dominio.catalogo.sensores import PERFILES
from app.dominio.catalogo.indices import cargar_catalogo
from app.dominio.compilador.base import geojson_js, reductor
from app.dominio.errores import MascaraNoDisponibleJS

# Snippets de máscara por collection ID. v1: sembrar S2 SR y Landsat C2 L2 (QA_PIXEL).
# CONFIRMAR el texto exacto contra el estándar del Code Editor al integrar con GEE en vivo
# (F2/F3a) — el contrato lo fija el golden test, no la fidelidad runtime contra GEE.
MASCARA_JS: dict[str, str] = {
    "COPERNICUS/S2_SR": "maskS2clouds",
    "COPERNICUS/S2_SR_HARMONIZED": "maskS2clouds",
    "LANDSAT/LC08/C02/T1_L2": "maskLandsatC2",
    "LANDSAT/LC08/C02/T2_L2": "maskLandsatC2",
    "LANDSAT/LC09/C02/T1_L2": "maskLandsatC2",
    "LANDSAT/LC09/C02/T2_L2": "maskLandsatC2",
    "LANDSAT/LE07/C02/T1_L2": "maskLandsatC2",
    "LANDSAT/LE07/C02/T2_L2": "maskLandsatC2",
    "LANDSAT/LT05/C02/T1_L2": "maskLandsatC2",
    "LANDSAT/LT05/C02/T2_L2": "maskLandsatC2",
    "LANDSAT/LT04/C02/T1_L2": "maskLandsatC2",
    "LANDSAT/LT04/C02/T2_L2": "maskLandsatC2",
}
_DEFS_MASCARA: dict[str, str] = {
    "maskS2clouds": (
        "function maskS2clouds(img){var qa=img.select('QA60');"
        "var m=qa.bitwiseAnd(1<<10).eq(0).and(qa.bitwiseAnd(1<<11).eq(0));"
        "return img.updateMask(m);}"
    ),
    "maskLandsatC2": (
        "function maskLandsatC2(img){var qa=img.select('QA_PIXEL');"
        "var m=qa.bitwiseAnd(parseInt('11111',2)).eq(0);"
        "return img.updateMask(m);}"
    ),
}


def _params_banda_js(r: Receta) -> str:
    perfil = PERFILES[r.sensor]
    idx = cargar_catalogo()[r.indice]
    pares = [f"{s!r}: img.select({perfil.bandas[s]!r})" for s in sorted(idx.bandas_requeridas)]
    pares += [f"{k!r}: {v}" for k, v in sorted(r.parametros.items())]
    return "{" + ", ".join(pares) + "}"


def _cola_salida(r: Receta) -> list[str]:
    banda = f"img.select('{r.indice}')"
    if r.salida is Salida.DESCARGA:
        return [f"var url = {banda}.getDownloadURL("
                f"{{scale: {r.escala}, region: aoi, format: 'GEO_TIFF'}});", "print(url);"]
    if r.salida is Salida.DRIVE:
        return [f"Export.image.toDrive({{image: {banda}, region: aoi, "
                f"scale: {r.escala}, description: '{r.indice}'}});"]
    return [f"Map.addLayer({banda}, {{}}, '{r.indice}');", "Map.centerObject(aoi);"]


def compilar(r: Receta) -> str:
    L = ["var spectral = require('users/dmlmont/spectral:spectral');"]
    if r.mascara_nubes:
        fn = MASCARA_JS.get(r.sensor)
        if fn is None:
            raise MascaraNoDisponibleJS(r.sensor)
        L.append(_DEFS_MASCARA[fn])
    L += [f"var aoi = ee.Geometry({geojson_js(r.geometria)});",
          f"var col = ee.ImageCollection('{r.sensor}')",
          "  .filterBounds(aoi)",
          f"  .filterDate('{r.fecha_inicio}', '{r.fecha_fin}');"]
    if r.mascara_nubes:
        L.append(f"col = col.map({MASCARA_JS[r.sensor]});")
    L += ["col = col.map(function(img){",
          f"  return spectral.computeIndex(img, ['{r.indice}'], {_params_banda_js(r)});",
          "});",
          f"var img = col.{reductor(r.composicion)}.clip(aoi);"]
    L += _cola_salida(r)
    return "\n".join(L)
