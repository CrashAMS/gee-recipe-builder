"""Smoke real de F4: export chico a Drive, polling hasta estado terminal.

Uso: python -m app.scripts.smoke_export_drive [--project ID] [--carpeta NOMBRE]
Requiere: credenciales OAuth de GEE ya presentes (flujo de F2, mismo patrón que
`scripts/smoke_ndvi_s2.py`). Deja un .tif en la carpeta 'GEE_smoke' de tu Drive.
Imprime el estado terminal como `TERMINAL=<state>` (COMPLETED = ok).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import ee

from app.gee.auth import asegurar_sesion
from app.gee.exportador import ConfigExport, DestinoExport, ExportadorGEE

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir "→"/emojis.
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")

_INTERVALO_POLL_S = 10


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke F4: export NDVI -> Drive")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--carpeta", default="GEE_smoke",
                    help="Carpeta destino en la raíz de Drive")
    args = ap.parse_args()

    project = asegurar_sesion(args.project)
    print(f"[auth] sesión GEE lista con project '{project}'")

    aoi = ee.Geometry.Rectangle([-58.45, -34.62, -58.40, -34.58])  # ~CABA chica
    imagen = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate("2024-01-01", "2024-03-01")
        .median()
        .normalizedDifference(["B8", "B4"])  # NDVI
        .rename("NDVI")
    )
    cfg = ConfigExport(
        descripcion="smoke_f4_ndvi",
        prefijo_archivo="smoke_f4_ndvi",
        destino=DestinoExport.DRIVE,
        region=aoi,
        carpeta_drive=args.carpeta,
        scale=10,
    )

    exp = ExportadorGEE()
    task = exp.lanzar(imagen, cfg)
    print(f"[smoke] task lanzado id={task.id}")

    while True:
        prog = exp.estado(task)
        print(f"[smoke] estado={prog.estado.value} crudo={prog.crudo}")
        if prog.terminal:
            print(f"[smoke] TERMINAL={prog.crudo} error={prog.mensaje_error} "
                  f"uris={prog.uris_destino}")
            return 0 if prog.ok else 1
        time.sleep(_INTERVALO_POLL_S)


if __name__ == "__main__":
    sys.exit(main())
