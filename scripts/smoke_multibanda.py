"""Smoke real: NDVI+EVI+NDWI Sentinel-2 SR AOI chica -> UN .tif multibanda - F7.

Verifica (1) bandNames == [NDVI, EVI, NDWI] a nivel ee.Image, (2) que la descarga directa
(filePerBand=False) deje UN solo .tif con 3 bandas (tag TIFF 277 SamplesPerPixel, leido con
struct de stdlib) y (3) opcionalmente --drive lanza el export a Drive. Los NOMBRES de banda
dentro del GeoTIFF no se pueden leer sin GDAL: revisarlos a mano en QGIS.
Requiere cuenta GEE. NO se corre en CI."""
import argparse
import os
import struct
import sys

import ee

from app.gee.auth import asegurar_sesion
from app.gee.ejecutor import SolicitudEjecucion, construir_imagen, ejecutar_a_disco

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir caracteres no ASCII.
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")

INDICES = ["NDVI", "EVI", "NDWI"]
TAG_SAMPLES_PER_PIXEL = 277


def samples_per_pixel(ruta: str) -> int:
    """Lee SamplesPerPixel (tag 277) del primer IFD de un TIFF clasico o BigTIFF."""
    with open(ruta, "rb") as f:
        cab = f.read(16)
        end = "<" if cab[:2] == b"II" else ">"
        magic = struct.unpack(end + "H", cab[2:4])[0]
        if magic == 42:                       # TIFF clasico
            off = struct.unpack(end + "I", cab[4:8])[0]
            f.seek(off)
            n = struct.unpack(end + "H", f.read(2))[0]
            entradas = f.read(12 * n)
            tam, fmt_ent = 12, end + "HHI4s"
        elif magic == 43:                     # BigTIFF
            off = struct.unpack(end + "Q", cab[8:16])[0]
            f.seek(off)
            n = struct.unpack(end + "Q", f.read(8))[0]
            entradas = f.read(20 * n)
            tam, fmt_ent = 20, end + "HHQ8s"
        else:
            raise ValueError(f"No parece un TIFF (magic={magic})")
        for i in range(n):
            tag, tipo, _cuenta, valor = struct.unpack(fmt_ent, entradas[i * tam:(i + 1) * tam])
            if tag == TAG_SAMPLES_PER_PIXEL:
                return struct.unpack(end + ("H" if tipo == 3 else "I"), valor[: 2 if tipo == 3 else 4])[0]
    raise ValueError("El TIFF no trae el tag SamplesPerPixel (277)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke multibanda S2 -> UN .tif con 3 bandas")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--out", default="smoke_multibanda_s2.tif")
    ap.add_argument("--drive", action="store_true", help="ademas lanza el export a Drive")
    args = ap.parse_args()

    project = asegurar_sesion(args.project)
    print(f"[auth] sesion GEE lista con project '{project}'")

    aoi = ee.Geometry.Rectangle([-68.85, -32.92, -68.82, -32.90])  # ~3x2 km, Mendoza
    sol = SolicitudEjecucion(
        collection_id="COPERNICUS/S2_SR_HARMONIZED", aoi=aoi,
        fecha_inicio="2024-01-01", fecha_fin="2024-03-31",
        indices=list(INDICES), mascara_nubes=True, reduccion="median", scale=20,
    )
    imagen = construir_imagen(sol)
    bandas = imagen.bandNames().getInfo()
    print(f"[smoke] bandNames = {bandas}")
    assert bandas == INDICES, f"Se esperaban {INDICES} en ese orden; llego {bandas}"

    ruta = ejecutar_a_disco(sol, args.out)
    n = samples_per_pixel(ruta)
    print(f"[smoke] {ruta} ({os.path.getsize(ruta)} bytes), SamplesPerPixel={n}")
    assert n == len(INDICES), f"El .tif tiene {n} bandas; se esperaban {len(INDICES)}"

    if args.drive:
        task = ee.batch.Export.image.toDrive(
            image=imagen, description="smoke_multibanda", fileNamePrefix="smoke_multibanda",
            region=aoi, scale=20, crs="EPSG:4326", maxPixels=1e9)
        task.start()
        print(f"[drive] export lanzado: task {task.id}")

    print("[smoke] OK. REVISAR EN QGIS que las bandas se llamen NDVI, EVI, NDWI "
          "(propiedades de capa > Simbologia/Informacion): si no aparecen, avisar para decidir "
          "entre sidecar .json con el orden de bandas o documentarlo.")


if __name__ == "__main__":
    main()
