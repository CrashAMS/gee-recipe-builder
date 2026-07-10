"""Descarga directa .tif a disco con earthengine-api puro — F2 [DEC-F2]."""
import io
import zipfile

import ee
import requests

from .errores import clasificar_error


def extraer_tif_de_zip(contenido_zip: bytes, ruta_destino: str) -> str:
    """Extrae el .tif de un ZIPPED_GEO_TIFF de GEE al `ruta_destino`."""
    with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
        tifs = [n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff"))]
        if not tifs:
            raise ValueError(
                f"El ZIP de GEE no contiene ningún .tif (contenido: {zf.namelist()})"
            )
        datos = zf.read(tifs[0])
    with open(ruta_destino, "wb") as f:
        f.write(datos)
    return ruta_destino


def descargar_imagen(imagen: "ee.Image", region, scale, crs, ruta_destino, timeout=300) -> str:
    """Genera la URL de descarga, baja el ZIP y extrae el .tif. Los errores de
    límite (cómputo / 32MB) surgen en getDownloadURL y se clasifican [HALLAZGO-1.1]."""
    params = {"scale": scale, "region": region, "crs": crs, "format": "ZIPPED_GEO_TIFF"}
    try:
        url = imagen.getDownloadURL(params)
    except ee.EEException as exc:
        raise clasificar_error(exc) from exc
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return extraer_tif_de_zip(resp.content, ruta_destino)
