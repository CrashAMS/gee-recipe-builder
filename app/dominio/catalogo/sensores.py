"""Perfiles de sensor: collection ID exacto -> mapa símbolo ASI -> nombre de banda GEE.

Transcripto de `ee_extra.Spectral.utils._get_expression_map` (bandas/índices) y
`ee_extra.QA.clouds.maskClouds` (compatibilidad de máscara — tabla DISTINTA e
independiente, [HALLAZGO-2.4]). Paquete `ee_extra` versión pineada `2025.7.2`
(descargado del wheel de PyPI — el repo `davemlz/ee_extra` en GitHub ya no existe).

Sólo ópticos ([F0] decisión 2): S2 ×4, Landsat 4-9 C1 SR / C2 L2, MODIS GQ/GA/MCD43A4
en /006/ y /061/. SAR excluido (S1_GRD, PALSAR). Sentinel-3 no soporta índices (sólo
aparece en maskClouds del lado de ee_extra, no en lookupPlatform de índices)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class PerfilSensor:
    collection_id: str
    display_name: str
    bandas: dict[str, str]        # símbolo ASI -> nombre de banda GEE (N -> 'B8')
    soporta_mascara: bool         # de ee_extra/QA/clouds.py (tabla distinta, decisión F0)
    escala_nativa_m: int | None = None   # resolución nativa en metros
    fecha_inicio: str | None = None      # ISO yyyy-MM-dd, primer dato de la colección
    fecha_fin: str | None = None         # ISO; None = activa hoy (o fin no verificado)
    prop_nubes: str | None = None        # propiedad GEE de % nubes; None = sin propiedad (MODIS)

    @property
    def simbolos_disponibles(self) -> frozenset[str]:
        return frozenset(self.bandas.keys())


_S2 = {"A": "B1", "B": "B2", "G": "B3", "R": "B4", "RE1": "B5", "RE2": "B6",
       "RE3": "B7", "N": "B8", "N2": "B8A", "WV": "B9", "S1": "B11", "S2": "B12"}

_L8 = {"A": "B1", "B": "B2", "G": "B3", "R": "B4", "N": "B5",
       "S1": "B6", "S2": "B7", "T1": "B10", "T2": "B11"}

_L8C2 = {"A": "SR_B1", "B": "SR_B2", "G": "SR_B3", "R": "SR_B4", "N": "SR_B5",
         "S1": "SR_B6", "S2": "SR_B7", "T1": "ST_B10"}          # sin T2 ([HALLAZGO-2.5])

_L45 = {"B": "B1", "G": "B2", "R": "B3", "N": "B4",
        "S1": "B5", "T1": "B6", "S2": "B7"}

_L45C2 = {"B": "SR_B1", "G": "SR_B2", "R": "SR_B3", "N": "SR_B4",
          "S1": "SR_B5", "T1": "ST_B6", "S2": "SR_B7"}

_L7 = {"B": "B1", "G": "B2", "R": "B3", "N": "B4",
       "S1": "B5", "T1": "B6", "S2": "B7"}

_L7C2 = {"B": "SR_B1", "G": "SR_B2", "R": "SR_B3", "N": "SR_B4",
         "S1": "SR_B5", "T1": "ST_B6", "S2": "SR_B7"}

_MOD09GQ = {"R": "sur_refl_b01", "N": "sur_refl_b02"}

_MOD09GA = {"B": "sur_refl_b03", "G": "sur_refl_b04", "R": "sur_refl_b01",
            "N": "sur_refl_b02", "S1": "sur_refl_b06", "S2": "sur_refl_b07"}

_MCD43A4 = {"B": "Nadir_Reflectance_Band3", "G": "Nadir_Reflectance_Band4",
            "R": "Nadir_Reflectance_Band1", "N": "Nadir_Reflectance_Band2",
            "S1": "Nadir_Reflectance_Band6", "S2": "Nadir_Reflectance_Band7"}

# collection IDs con maskClouds disponible (ee_extra/QA/clouds.py::maskClouds lookup).
# NOTA: S2 TOA (COPERNICUS/S2, COPERNICUS/S2_HARMONIZED) NO está acá — soporta índices
# pero no máscara ([HALLAZGO-2.4]). MOD09GQ/MYD09GQ tampoco (sólo Q1/A1/GA de MODIS).
_CON_MASCARA = frozenset({
    "COPERNICUS/S2_SR", "COPERNICUS/S2_SR_HARMONIZED",
    "LANDSAT/LC08/C01/T1_SR", "LANDSAT/LC08/C01/T2_SR",
    "LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC08/C02/T2_L2",
    "LANDSAT/LC09/C02/T1_L2", "LANDSAT/LC09/C02/T2_L2",
    "LANDSAT/LE07/C01/T1_SR", "LANDSAT/LE07/C01/T2_SR",
    "LANDSAT/LE07/C02/T1_L2", "LANDSAT/LE07/C02/T2_L2",
    "LANDSAT/LT05/C01/T1_SR", "LANDSAT/LT05/C01/T2_SR",
    "LANDSAT/LT05/C02/T1_L2", "LANDSAT/LT05/C02/T2_L2",
    "LANDSAT/LT04/C01/T1_SR", "LANDSAT/LT04/C01/T2_SR",
    "LANDSAT/LT04/C02/T1_L2", "LANDSAT/LT04/C02/T2_L2",
    "MODIS/006/MOD09GA", "MODIS/006/MYD09GA", "MODIS/006/MOD09Q1", "MODIS/006/MYD09Q1",
    "MODIS/006/MOD09A1", "MODIS/006/MYD09A1",
    "MODIS/061/MOD09GA", "MODIS/061/MYD09GA", "MODIS/061/MOD09Q1", "MODIS/061/MYD09Q1",
    "MODIS/061/MOD09A1", "MODIS/061/MYD09A1",
})


# --- Escala nativa, rango de fechas y propiedad de nubes (tablas paralelas por familia) ---
# fecha_fin None = activa hoy. Las colecciones deprecadas (Landsat C1, MODIS 006) dejan fin
# None: un fin None nunca bloquea al usuario, uno inventado sí.   # verificar en catálogo GEE
_ESCALA_FRAGMENTOS = (          # (fragmento del cid, escala m)
    ("COPERNICUS/S2", 10), ("LANDSAT/", 30),
    ("MOD09GQ", 250), ("MYD09GQ", 250), ("MOD09Q1", 250), ("MYD09Q1", 250),
    ("MOD09GA", 500), ("MYD09GA", 500), ("MOD09A1", 500), ("MYD09A1", 500),
    ("MCD43A4", 500),
)
_PROP_NUBES = {"COPERNICUS/S2": "CLOUDY_PIXEL_PERCENTAGE", "LANDSAT/": "CLOUD_COVER"}

_INICIO_EXACTO = {              # cid exacto -> inicio ISO
    "COPERNICUS/S2": "2015-06-23", "COPERNICUS/S2_HARMONIZED": "2015-06-23",
    "COPERNICUS/S2_SR": "2017-03-28", "COPERNICUS/S2_SR_HARMONIZED": "2017-03-28",
}
_INICIO_LANDSAT = {"LC09": "2021-10-31", "LC08": "2013-03-18", "LE07": "1999-01-01",
                   "LT05": "1984-03-16", "LT04": "1982-08-22"}
_FIN_LANDSAT = {"LT05": "2012-05-05", "LT04": "1993-12-14"}   # verificar en catálogo GEE
_INICIO_MODIS = {"MOD09GQ": "2000-02-24", "MYD09GQ": "2002-07-04",
                 "MOD09Q1": "2000-02-18", "MYD09Q1": "2002-07-04",
                 "MOD09GA": "2000-02-24", "MYD09GA": "2002-07-04",
                 "MOD09A1": "2000-02-18", "MYD09A1": "2002-07-04",
                 "MCD43A4": "2000-02-16"}


def _fechas(cid: str) -> tuple[str | None, str | None]:
    if cid in _INICIO_EXACTO:
        return _INICIO_EXACTO[cid], None
    if cid.startswith("LANDSAT/"):
        sat = cid.split("/")[1]
        return _INICIO_LANDSAT.get(sat), _FIN_LANDSAT.get(sat)
    if cid.startswith("MODIS/"):
        return _INICIO_MODIS.get(cid.split("/")[2]), None
    return None, None


def _perfil(cid: str, nombre: str, bandas: dict[str, str]) -> PerfilSensor:
    ini, fin = _fechas(cid)
    escala = next((v for k, v in _ESCALA_FRAGMENTOS if k in cid), None)
    prop = next((v for k, v in _PROP_NUBES.items() if cid.startswith(k)), None)
    return PerfilSensor(cid, nombre, bandas, soporta_mascara=cid in _CON_MASCARA,
                        escala_nativa_m=escala, fecha_inicio=ini, fecha_fin=fin,
                        prop_nubes=prop)


PERFILES: dict[str, PerfilSensor] = {}


def _agregar(cid: str, nombre: str, bandas: dict[str, str]) -> None:
    PERFILES[cid] = _perfil(cid, nombre, bandas)


# --- Sentinel-2 (x4) ---
_agregar("COPERNICUS/S2", "Sentinel-2 TOA", _S2)
_agregar("COPERNICUS/S2_HARMONIZED", "Sentinel-2 TOA (harmonizado)", _S2)
_agregar("COPERNICUS/S2_SR", "Sentinel-2 SR", _S2)
_agregar("COPERNICUS/S2_SR_HARMONIZED", "Sentinel-2 SR (harmonizado)", _S2)

# --- Landsat 8/9 — C1 SR (T1/T2) + C2 L2 (T1/T2) ---
_agregar("LANDSAT/LC08/C01/T1_SR", "Landsat 8 C1 SR (T1)", _L8)
_agregar("LANDSAT/LC08/C01/T2_SR", "Landsat 8 C1 SR (T2)", _L8)
_agregar("LANDSAT/LC08/C02/T1_L2", "Landsat 8 C2 L2 (T1)", _L8C2)
_agregar("LANDSAT/LC08/C02/T2_L2", "Landsat 8 C2 L2 (T2)", _L8C2)
_agregar("LANDSAT/LC09/C02/T1_L2", "Landsat 9 C2 L2 (T1)", _L8C2)
_agregar("LANDSAT/LC09/C02/T2_L2", "Landsat 9 C2 L2 (T2)", _L8C2)

# --- Landsat 7 — C1 SR + C2 L2 ---
_agregar("LANDSAT/LE07/C01/T1_SR", "Landsat 7 C1 SR (T1)", _L7)
_agregar("LANDSAT/LE07/C01/T2_SR", "Landsat 7 C1 SR (T2)", _L7)
_agregar("LANDSAT/LE07/C02/T1_L2", "Landsat 7 C2 L2 (T1)", _L7C2)
_agregar("LANDSAT/LE07/C02/T2_L2", "Landsat 7 C2 L2 (T2)", _L7C2)

# --- Landsat 5 — C1 SR + C2 L2 ---
_agregar("LANDSAT/LT05/C01/T1_SR", "Landsat 5 C1 SR (T1)", _L45)
_agregar("LANDSAT/LT05/C01/T2_SR", "Landsat 5 C1 SR (T2)", _L45)
_agregar("LANDSAT/LT05/C02/T1_L2", "Landsat 5 C2 L2 (T1)", _L45C2)
_agregar("LANDSAT/LT05/C02/T2_L2", "Landsat 5 C2 L2 (T2)", _L45C2)

# --- Landsat 4 — C1 SR + C2 L2 ---
_agregar("LANDSAT/LT04/C01/T1_SR", "Landsat 4 C1 SR (T1)", _L45)
_agregar("LANDSAT/LT04/C01/T2_SR", "Landsat 4 C1 SR (T2)", _L45)
_agregar("LANDSAT/LT04/C02/T1_L2", "Landsat 4 C2 L2 (T1)", _L45C2)
_agregar("LANDSAT/LT04/C02/T2_L2", "Landsat 4 C2 L2 (T2)", _L45C2)

# --- MODIS GQ/GA/MCD43A4 — /006/ y /061/ ---
for _coleccion in ("006", "061"):
    _agregar(f"MODIS/{_coleccion}/MOD09GQ", f"MODIS Terra 250m ({_coleccion})", _MOD09GQ)
    _agregar(f"MODIS/{_coleccion}/MYD09GQ", f"MODIS Aqua 250m ({_coleccion})", _MOD09GQ)
    _agregar(f"MODIS/{_coleccion}/MOD09Q1", f"MODIS Terra 250m 8-day ({_coleccion})", _MOD09GQ)
    _agregar(f"MODIS/{_coleccion}/MYD09Q1", f"MODIS Aqua 250m 8-day ({_coleccion})", _MOD09GQ)
    _agregar(f"MODIS/{_coleccion}/MOD09GA", f"MODIS Terra 500m ({_coleccion})", _MOD09GA)
    _agregar(f"MODIS/{_coleccion}/MYD09GA", f"MODIS Aqua 500m ({_coleccion})", _MOD09GA)
    _agregar(f"MODIS/{_coleccion}/MOD09A1", f"MODIS Terra 500m 8-day ({_coleccion})", _MOD09GA)
    _agregar(f"MODIS/{_coleccion}/MYD09A1", f"MODIS Aqua 500m 8-day ({_coleccion})", _MOD09GA)
    _agregar(f"MODIS/{_coleccion}/MCD43A4", f"MODIS Terra+Aqua BRDF/Albedo ({_coleccion})", _MCD43A4)


def sensores_compatibles(bandas_requeridas: frozenset[str]) -> list[str]:
    """Collection IDs cuyo perfil provee TODAS las bandas requeridas ([HALLAZGO-2.1/2.2])."""
    return [cid for cid, p in PERFILES.items()
            if bandas_requeridas <= p.simbolos_disponibles]


def sensores_con_mascara() -> frozenset[str]:
    """Subconjunto que soporta maskClouds (tabla propia, independiente de índices — [HALLAZGO-2.4])."""
    return frozenset(cid for cid, p in PERFILES.items() if p.soporta_mascara)
