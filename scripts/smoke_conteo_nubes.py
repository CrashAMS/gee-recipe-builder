"""Smoke real: conteo de escenas (total y con < X % nubes) S2 + caso MODIS. Headless - F4.

Requiere cuenta GEE del usuario. Compara los numeros con el Code Editor si dudas.
"""
import argparse
import os
import sys

import ee

from app.dominio import catalogo
from app.gee.auth import asegurar_sesion
from app.gee.ejecutor import SolicitudEjecucion, contar_imagenes

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir caracteres no ASCII.
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")


def _sol(collection_id: str, aoi) -> SolicitudEjecucion:
    return SolicitudEjecucion(
        collection_id=collection_id,
        aoi=aoi,
        fecha_inicio="2024-01-01",
        fecha_fin="2024-03-31",
        indice="NDVI",
        mascara_nubes=False,
        reduccion="median",
        scale=20,
        propiedad_nubes=catalogo.propiedad_nubes(collection_id),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke conteo de escenas con filtro de nubes")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--umbral", type=int, default=20, help="X de '< X %% nubes' (default 20)")
    args = ap.parse_args()

    project = asegurar_sesion(args.project)
    print(f"[auth] sesion GEE lista con project '{project}'")

    aoi = ee.Geometry.Rectangle([-68.85, -32.92, -68.82, -32.90])  # ~3x2 km, Mendoza

    total, pocas = contar_imagenes(_sol("COPERNICUS/S2_SR_HARMONIZED", aoi), args.umbral)
    print(f"[S2] total={total} con_pocas_nubes(<{args.umbral}%)={pocas}")
    assert pocas is not None, "S2 debe informar el conteo con pocas nubes"
    assert 0 <= pocas <= total, "con_pocas_nubes debe ser <= total"

    total_m, pocas_m = contar_imagenes(_sol("MODIS/061/MOD09GA", aoi), args.umbral)
    print(f"[MODIS] total={total_m} con_pocas_nubes={pocas_m}")
    assert pocas_m is None, "MODIS no tiene propiedad de nubes: debe devolver None"
    print("[smoke] OK")


if __name__ == "__main__":
    main()
