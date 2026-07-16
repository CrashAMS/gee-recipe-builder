"""Receta -> script JS (Code Editor + módulo users/dmlmont/spectral).

Paridad dura con el dialecto Python (decisión de producto, cierre de
gee-recipe-builder): el script JS tiene que ser numéricamente equivalente al
que emite `dialecto_python.compilar` (`col.maskClouds().scaleAndOffset()`).
Los snippets de `MASCARA_JS`/`ESCALA_JS` son transcripciones literales de
`ee_extra` (paquete pineado `2025.7.2`, mismo precedente que `sensores.py`):
- Máscara: `ee_extra.QA.clouds.maskClouds` (bits/bandas por plataforma).
- Escala: `ee_extra.STAC.core.scaleAndOffset` + `data/ee-catalog-scale.json` /
  `ee-catalog-offset.json` (factores multiply/add por banda y colección).
CONFIRMAR el texto exacto contra el estándar del Code Editor al integrar con
GEE en vivo — el contrato lo fija el golden test, no la fidelidad runtime.
"""
from app.dominio.receta import Receta, Salida
from app.dominio.catalogo.sensores import PERFILES
from app.dominio.catalogo.indices import cargar_catalogo
from app.dominio.compilador.base import geojson_js, reductor
from app.dominio.errores import MascaraNoDisponibleJS

# --- Máscara de nubes por collection ID (ee_extra.QA.clouds.maskClouds, lookup). ---
# Cubre los 32 IDs con soporta_mascara=True de sensores.py. Defaults de
# eemont.ImageCollection.maskClouds() (maskShadows=True, maskCirrus=True) —
# mismos que usa dialecto_python vía `col.maskClouds()` sin overrides.
MASCARA_JS: dict[str, str] = {
    # S2 SR — método 'cloud_prob' (default de eemont/ee_extra para S2): join
    # con COPERNICUS/S2_CLOUD_PROBABILITY + sombras proyectadas + buffer.
    # Opera sobre la COLECCIÓN (necesita el join), no imagen a imagen — ver
    # _MASCARAS_NIVEL_COLECCION. Solo SR: los IDs TOA (COPERNICUS/S2[_HARMONIZED])
    # NO están en el lookup de ee_extra (maskClouds es no-op para ellos en
    # Python, y la lógica de sombras usa la banda SCL, exclusiva de SR).
    "COPERNICUS/S2_SR": "maskS2clouds",
    "COPERNICUS/S2_SR_HARMONIZED": "maskS2clouds",
    # Landsat C2 L2 — QA_PIXEL bits 2 (cirrus), 3 (nube), 4 (sombra).
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
    # Landsat 8 C1 SR — pixel_qa bit 5 (nube), bit 3 (sombra). Función "L8" de
    # ee_extra/QA/clouds.py (distinta de L457: sin combinar con bit 7).
    "LANDSAT/LC08/C01/T1_SR": "maskLandsatC1SR_L8",
    "LANDSAT/LC08/C01/T2_SR": "maskLandsatC1SR_L8",
    # Landsat 4/5/7 C1 SR — pixel_qa: nube = bit5 AND bit7, sombra = bit3;
    # más `mask2 = img.mask().reduce(min)` (función "L457" de ee_extra).
    "LANDSAT/LE07/C01/T1_SR": "maskLandsatC1SR_L457",
    "LANDSAT/LE07/C01/T2_SR": "maskLandsatC1SR_L457",
    "LANDSAT/LT05/C01/T1_SR": "maskLandsatC1SR_L457",
    "LANDSAT/LT05/C01/T2_SR": "maskLandsatC1SR_L457",
    "LANDSAT/LT04/C01/T1_SR": "maskLandsatC1SR_L457",
    "LANDSAT/LT04/C01/T2_SR": "maskLandsatC1SR_L457",
    # MODIS GA (500m diario) y A1 (500m 8-day) — misma lógica de bits sobre
    # bandas QA distintas ("state_1km" vs "StateQA"): bit0 nube, bit2 sombra,
    # bit8 cirrus (función "MOD09GA"/"MOD09A1" de ee_extra).
    "MODIS/006/MOD09GA": "maskModisGA",
    "MODIS/006/MYD09GA": "maskModisGA",
    "MODIS/061/MOD09GA": "maskModisGA",
    "MODIS/061/MYD09GA": "maskModisGA",
    "MODIS/006/MOD09A1": "maskModisA1",
    "MODIS/006/MYD09A1": "maskModisA1",
    "MODIS/061/MOD09A1": "maskModisA1",
    "MODIS/061/MYD09A1": "maskModisA1",
    # MODIS Q1 (250m 8-day) — banda "State", mismos bits 0/2/8 (función
    # "MOD09Q1" de ee_extra; distinta de GQ, que NO soporta máscara).
    "MODIS/006/MOD09Q1": "maskModisQ1",
    "MODIS/006/MYD09Q1": "maskModisQ1",
    "MODIS/061/MOD09Q1": "maskModisQ1",
    "MODIS/061/MYD09Q1": "maskModisQ1",
}
# Funciones de máscara que operan sobre la ImageCollection entera (necesitan
# un join previo) — compilar() emite `col = fn(col);` en vez de `col.map(fn)`.
_MASCARAS_NIVEL_COLECCION = frozenset({"maskS2clouds"})

_DEFS_MASCARA: dict[str, str] = {
    # Transcripción del branch S2/'cloud_prob' de ee_extra.QA.clouds.maskClouds
    # con los defaults de eemont (prob=60, maskShadows=true, scaledImage=false
    # -> umbral dark*1e4 sobre B8 crudo, dark=0.15, cloudDist=1000 -> dDT 100,
    # buffer=250 -> focal_max 50 m, cdi=null -> sin CDI; maskCirrus se ignora
    # en este método — solo aplica a method='qa').
    "maskS2clouds": (
        "function maskS2clouds(col){\n"
        "  var s2Clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY');\n"
        "  var fil = ee.Filter.equals({leftField: 'system:index', rightField: 'system:index'});\n"
        "  col = ee.ImageCollection(ee.Join.saveFirst('cloud_mask').apply(col, s2Clouds, fil));\n"
        "  return col.map(function(img){\n"
        "    var clouds = ee.Image(img.get('cloud_mask')).select('probability');\n"
        "    img = img.addBands(clouds.gte(60).rename('CLOUD_MASK'));\n"
        "    var notWater = img.select('SCL').neq(6);\n"
        "    var darkPixels = img.select('B8').lt(0.15 * 1e4).multiply(notWater);\n"
        "    var shadowAzimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')));\n"
        "    var cloudProjection = img.select('CLOUD_MASK')\n"
        "      .directionalDistanceTransform(shadowAzimuth, 100)\n"
        "      .reproject({crs: img.select(0).projection(), scale: 10})\n"
        "      .select('distance').mask();\n"
        "    img = img.addBands(cloudProjection.multiply(darkPixels).rename('SHADOW_MASK'));\n"
        "    var isCloudShadow = img.select('CLOUD_MASK').add(img.select('SHADOW_MASK')).gt(0)\n"
        "      .focalMin(20, 'circle', 'meters').focalMax(50, 'circle', 'meters')\n"
        "      .rename('CLOUD_SHADOW_MASK');\n"
        "    return img.addBands(isCloudShadow).updateMask(isCloudShadow.not());\n"
        "  });\n"
        "}"
    ),
    "maskLandsatC2": (
        "function maskLandsatC2(img){var qa=img.select('QA_PIXEL');"
        "var m=qa.bitwiseAnd(1<<2).eq(0).and(qa.bitwiseAnd(1<<3).eq(0))"
        ".and(qa.bitwiseAnd(1<<4).eq(0));"
        "return img.updateMask(m);}"
    ),
    "maskLandsatC1SR_L8": (
        "function maskLandsatC1SR_L8(img){var qa=img.select('pixel_qa');"
        "var m=qa.bitwiseAnd(1<<5).eq(0).and(qa.bitwiseAnd(1<<3).eq(0));"
        "return img.updateMask(m);}"
    ),
    "maskLandsatC1SR_L457": (
        "function maskLandsatC1SR_L457(img){var qa=img.select('pixel_qa');"
        "var cloud=qa.bitwiseAnd(1<<5).and(qa.bitwiseAnd(1<<7)).or(qa.bitwiseAnd(1<<3));"
        "var mask2=img.mask().reduce(ee.Reducer.min());"
        "return img.updateMask(cloud.not()).updateMask(mask2);}"
    ),
    "maskModisGA": (
        "function maskModisGA(img){var qa=img.select('state_1km');"
        "var m=qa.bitwiseAnd(1<<0).eq(0).and(qa.bitwiseAnd(1<<2).eq(0))"
        ".and(qa.bitwiseAnd(1<<8).eq(0));"
        "return img.updateMask(m);}"
    ),
    "maskModisA1": (
        "function maskModisA1(img){var qa=img.select('StateQA');"
        "var m=qa.bitwiseAnd(1<<0).eq(0).and(qa.bitwiseAnd(1<<2).eq(0))"
        ".and(qa.bitwiseAnd(1<<8).eq(0));"
        "return img.updateMask(m);}"
    ),
    "maskModisQ1": (
        "function maskModisQ1(img){var qa=img.select('State');"
        "var m=qa.bitwiseAnd(1<<0).eq(0).and(qa.bitwiseAnd(1<<2).eq(0))"
        ".and(qa.bitwiseAnd(1<<8).eq(0));"
        "return img.updateMask(m);}"
    ),
}

# --- Escala/offset por collection ID (ee_extra.STAC.core.scaleAndOffset). ---
# Decisión explícita para los 40 IDs de sensores.py: nombre de función JS, o
# `None` si ee_extra NO tiene entrada de escala para esa colección (Landsat
# C1 SR — `getScaleParams`/`getOffsetParams` devuelven None y
# `scaleAndOffset()` es un no-op también del lado Python: misma paridad).
ESCALA_JS: dict[str, str | None] = {
    # Sentinel-2 (las 4 variantes) — reflectancia *1e-4, offset 0.
    "COPERNICUS/S2": "escalarS2",
    "COPERNICUS/S2_HARMONIZED": "escalarS2",
    "COPERNICUS/S2_SR": "escalarS2",
    "COPERNICUS/S2_SR_HARMONIZED": "escalarS2",
    # Landsat C1 SR — sin entrada en ee-catalog-scale.json: scaleAndOffset()
    # es un no-op en Python también (ee_extra.getScaleParams devuelve None).
    "LANDSAT/LC08/C01/T1_SR": None,
    "LANDSAT/LC08/C01/T2_SR": None,
    "LANDSAT/LE07/C01/T1_SR": None,
    "LANDSAT/LE07/C01/T2_SR": None,
    "LANDSAT/LT05/C01/T1_SR": None,
    "LANDSAT/LT05/C01/T2_SR": None,
    "LANDSAT/LT04/C01/T1_SR": None,
    "LANDSAT/LT04/C01/T2_SR": None,
    # Landsat 8/9 C2 L2 — SR_B* *2.75e-05 -0.2, térmica ST_B10 *0.00341802 +149.
    "LANDSAT/LC08/C02/T1_L2": "escalarLandsatC2_T10",
    "LANDSAT/LC08/C02/T2_L2": "escalarLandsatC2_T10",
    "LANDSAT/LC09/C02/T1_L2": "escalarLandsatC2_T10",
    "LANDSAT/LC09/C02/T2_L2": "escalarLandsatC2_T10",
    # Landsat 4/5/7 C2 L2 — misma escala SR, térmica en ST_B6.
    "LANDSAT/LE07/C02/T1_L2": "escalarLandsatC2_T6",
    "LANDSAT/LE07/C02/T2_L2": "escalarLandsatC2_T6",
    "LANDSAT/LT05/C02/T1_L2": "escalarLandsatC2_T6",
    "LANDSAT/LT05/C02/T2_L2": "escalarLandsatC2_T6",
    "LANDSAT/LT04/C02/T1_L2": "escalarLandsatC2_T6",
    "LANDSAT/LT04/C02/T2_L2": "escalarLandsatC2_T6",
    # MODIS GQ/Q1 (250m) — sur_refl_b01/b02 *1e-4.
    "MODIS/006/MOD09GQ": "escalarModisGQ",
    "MODIS/006/MYD09GQ": "escalarModisGQ",
    "MODIS/006/MOD09Q1": "escalarModisGQ",
    "MODIS/006/MYD09Q1": "escalarModisGQ",
    "MODIS/061/MOD09GQ": "escalarModisGQ",
    "MODIS/061/MYD09GQ": "escalarModisGQ",
    "MODIS/061/MOD09Q1": "escalarModisGQ",
    "MODIS/061/MYD09Q1": "escalarModisGQ",
    # MODIS GA/A1 (500m) — sur_refl_b01..b07 (menos b05, no usado por el catálogo) *1e-4.
    "MODIS/006/MOD09GA": "escalarModisGA",
    "MODIS/006/MYD09GA": "escalarModisGA",
    "MODIS/006/MOD09A1": "escalarModisGA",
    "MODIS/006/MYD09A1": "escalarModisGA",
    "MODIS/061/MOD09GA": "escalarModisGA",
    "MODIS/061/MYD09GA": "escalarModisGA",
    "MODIS/061/MOD09A1": "escalarModisGA",
    "MODIS/061/MYD09A1": "escalarModisGA",
    # MODIS MCD43A4 (BRDF/Albedo) — Nadir_Reflectance_Band* *1e-4.
    "MODIS/006/MCD43A4": "escalarMcd43a4",
    "MODIS/061/MCD43A4": "escalarMcd43a4",
}
_DEFS_ESCALA: dict[str, str] = {
    "escalarS2": (
        "function escalarS2(img){"
        "var b=['B1','B2','B3','B4','B5','B6','B7','B8','B8A','B9','B11','B12'];"
        "return img.addBands(img.select(b).multiply(0.0001),null,true);}"
    ),
    "escalarLandsatC2_T10": (
        "function escalarLandsatC2_T10(img){"
        "var sr=['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7'];"
        "var s=img.select(sr).multiply(2.75e-05).add(-0.2);"
        "s=s.addBands(img.select(['ST_B10']).multiply(0.00341802).add(149));"
        "return img.addBands(s,null,true);}"
    ),
    "escalarLandsatC2_T6": (
        "function escalarLandsatC2_T6(img){"
        "var sr=['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7'];"
        "var s=img.select(sr).multiply(2.75e-05).add(-0.2);"
        "s=s.addBands(img.select(['ST_B6']).multiply(0.00341802).add(149));"
        "return img.addBands(s,null,true);}"
    ),
    "escalarModisGQ": (
        "function escalarModisGQ(img){var b=['sur_refl_b01','sur_refl_b02'];"
        "return img.addBands(img.select(b).multiply(0.0001),null,true);}"
    ),
    "escalarModisGA": (
        "function escalarModisGA(img){"
        "var b=['sur_refl_b01','sur_refl_b02','sur_refl_b03','sur_refl_b04',"
        "'sur_refl_b06','sur_refl_b07'];"
        "return img.addBands(img.select(b).multiply(0.0001),null,true);}"
    ),
    "escalarMcd43a4": (
        "function escalarMcd43a4(img){"
        "var b=['Nadir_Reflectance_Band1','Nadir_Reflectance_Band2',"
        "'Nadir_Reflectance_Band3','Nadir_Reflectance_Band4',"
        "'Nadir_Reflectance_Band6','Nadir_Reflectance_Band7'];"
        "return img.addBands(img.select(b).multiply(0.0001),null,true);}"
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
        fn_mascara = MASCARA_JS.get(r.sensor)
        if fn_mascara is None:
            raise MascaraNoDisponibleJS(r.sensor)
        L.append(_DEFS_MASCARA[fn_mascara])
    fn_escala = ESCALA_JS.get(r.sensor)
    if fn_escala:
        L.append(_DEFS_ESCALA[fn_escala])
    L += [f"var aoi = ee.Geometry({geojson_js(r.geometria)});",
          f"var col = ee.ImageCollection('{r.sensor}')",
          "  .filterBounds(aoi)",
          f"  .filterDate('{r.fecha_inicio}', '{r.fecha_fin}');"]
    if r.mascara_nubes:
        if fn_mascara in _MASCARAS_NIVEL_COLECCION:
            L.append(f"col = {fn_mascara}(col);")
        else:
            L.append(f"col = col.map({fn_mascara});")
    if fn_escala:
        L.append(f"col = col.map({fn_escala});")
    L += ["col = col.map(function(img){",
          f"  return spectral.computeIndex(img, ['{r.indice}'], {_params_banda_js(r)});",
          "});",
          f"var img = col.{reductor(r.composicion)}.clip(aoi);"]
    L += _cola_salida(r)
    return "\n".join(L)
