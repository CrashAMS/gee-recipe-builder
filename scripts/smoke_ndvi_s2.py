"""Smoke real: NDVI Sentinel-2 SR AOI chica → .tif en disco. Headless — F2."""
import argparse
import os
import sys

import ee

from app.gee.auth import asegurar_sesion
from app.gee.ejecutor import SolicitudEjecucion, ejecutar_a_disco

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir "→".
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke NDVI S2 -> .tif")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--out", default="smoke_ndvi_s2.tif")
    args = ap.parse_args()

    project = asegurar_sesion(args.project)
    print(f"[auth] sesión GEE lista con project '{project}'")

    aoi = ee.Geometry.Rectangle([-68.85, -32.92, -68.82, -32.90])  # ~3x2 km, Mendoza
    sol = SolicitudEjecucion(
        collection_id="COPERNICUS/S2_SR_HARMONIZED",
        aoi=aoi,
        fecha_inicio="2024-01-01",
        fecha_fin="2024-03-31",
        indice="NDVI",
        mascara_nubes=True,
        reduccion="median",
        scale=20,
    )
    ruta = ejecutar_a_disco(sol, args.out)
    tam = os.path.getsize(ruta)
    assert tam > 0, "El .tif quedó vacío"
    print(f"[smoke] OK → {ruta} ({tam} bytes)")


if __name__ == "__main__":
    main()
