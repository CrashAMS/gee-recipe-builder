"""Smoke real: NDVI+EVI+NDWI Sentinel-2 SR AOI chica → .tif multibanda en disco — F6b.

Verifica que la imagen tenga exactamente las bandas NDVI, EVI, NDWI en ese orden
(Story 9: varios índices → un GeoTIFF multibanda). Requiere cuenta GEE."""
import argparse
import os
import sys

import ee

from app.gee.auth import asegurar_sesion
from app.gee.ejecutor import SolicitudEjecucion, construir_imagen, ejecutar_a_disco

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir "→".
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")

INDICES = ["NDVI", "EVI", "NDWI"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke multi-índice S2 -> .tif multibanda")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--out", default="smoke_multiindice_s2.tif")
    args = ap.parse_args()

    project = asegurar_sesion(args.project)
    print(f"[auth] sesión GEE lista con project '{project}'")

    aoi = ee.Geometry.Rectangle([-68.85, -32.92, -68.82, -32.90])  # ~3x2 km, Mendoza
    sol = SolicitudEjecucion(
        collection_id="COPERNICUS/S2_SR_HARMONIZED",
        aoi=aoi,
        fecha_inicio="2024-01-01",
        fecha_fin="2024-03-31",
        indices=list(INDICES),
        mascara_nubes=True,
        reduccion="median",
        scale=20,
    )
    bandas = construir_imagen(sol).bandNames().getInfo()
    print(f"[smoke] bandNames = {bandas}")
    assert bandas == INDICES, f"Se esperaban exactamente {INDICES} en ese orden; llegó {bandas}"

    ruta = ejecutar_a_disco(sol, args.out)
    tam = os.path.getsize(ruta)
    assert tam > 0, "El .tif quedó vacío"
    print(f"[smoke] OK → {ruta} ({tam} bytes, {len(bandas)} bandas)")


if __name__ == "__main__":
    main()
