"""Smoke real (F8): serie temporal NDVI S2 mensual de 3 meses sobre AOI chica → filas + CSV.

Recorre el mismo camino que `WorkerSerieTemporal`: `periodos` → `solicitud_desde_receta` →
`construir_coleccion` una vez → `serie_periodo` por período (un getInfo cada uno).
Comparar las medias con el script JS de la app corrido en el Code Editor.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

from app.dominio.aoi import desde_bbox
from app.dominio.periodos import periodos
from app.dominio.receta import Receta
from app.dominio.serie_csv import FilaSerie, escribir_csv, filas_a_csv
from app.gee import ejecutor
from app.gee.auth import asegurar_sesion
from app.ui.workers import solicitud_desde_receta

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir "→".
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke serie temporal NDVI S2 mensual -> CSV")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "smoke_serie_temporal.csv"))
    args = ap.parse_args()

    project = asegurar_sesion(args.project)
    print(f"[auth] sesión GEE lista con project '{project}'")

    receta = Receta(
        sensor="COPERNICUS/S2_SR_HARMONIZED", indices=["NDVI"],
        geometria=desde_bbox(-68.85, -32.92, -68.82, -32.90),   # ~3x2 km, Mendoza
        fecha_inicio="2024-01-01", fecha_fin="2024-04-01", mascara_nubes=True,
        composicion="median", salida="descarga", escala=20,
        producto="serie_temporal", periodo="mensual")
    lista = periodos(receta.fecha_inicio, receta.fecha_fin, receta.periodo)
    sol = solicitud_desde_receta(receta)
    col = ejecutor.construir_coleccion(sol)
    filas = []
    for i, (ini, fin) in enumerate(lista, start=1):
        n, medias = ejecutor.serie_periodo(col, sol, ini, fin)
        filas.append(FilaSerie(ini, fin, n, medias))
        print(f"[serie] {i}/{len(lista)} {ini} → {fin}: n_imagenes={n} NDVI_mean={medias['NDVI']}")

    assert len(filas) == 3, f"Se esperaban 3 filas mensuales, hubo {len(filas)}"
    assert all(f.n_imagenes >= 0 for f in filas), "n_imagenes negativo"
    escribir_csv(args.out, filas_a_csv(filas, receta.indices))
    print(f"[smoke] OK → {args.out}")


if __name__ == "__main__":
    main()
