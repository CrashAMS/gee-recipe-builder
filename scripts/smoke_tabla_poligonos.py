"""Smoke real de F9: tabla por polígono (reduceRegions) con 3 polígonos de prueba.

Uso: python -m scripts.smoke_tabla_poligonos [--project ID] [--drive] [--carpeta NOMBRE]
Requiere credenciales OAuth de GEE. Crea un shapefile TEMPORAL de 3 lotes con properties
(`lote`, `ha`), arma la receta tabla (NDVI, S2, ene-mar 2024) y:
  - sin flag (rama local): corre `WorkerTabla` en modo local, escribe un CSV temporal e
    imprime columnas y filas. Comparar mean/min/max/std/n con el Code Editor (script de la
    app con el mismo shapefile).
  - `--drive` (fuerza umbral 0): lanza `Export.table.toDrive` por `ExportadorGEE.lanzar_tabla`,
    lo registra en un `exports.json` TEMPORAL y lo sigue por id con `PollerTask` hasta
    imprimir `TERMINAL=<state>` (COMPLETED esperado).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Consolas Windows con codepage no-UTF8 (cp1252) rompen al imprimir caracteres no ASCII.
if sys.stdout.encoding is None or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")


def _shapefile_de_prueba(dir_: Path) -> Path:
    import geopandas as gpd
    from shapely.geometry import box

    lotes = [box(-58.45 + i * 0.015, -34.62, -58.44 + i * 0.015, -34.61) for i in range(3)]
    ruta = dir_ / "lotes_smoke.shp"
    gpd.GeoDataFrame({"lote": ["Lote 1", "Lote 2", "Ñandú"], "ha": [10.5, 20.0, 7.25]},
                     geometry=lotes, crs="EPSG:4326").to_file(ruta, engine="pyogrio")
    return ruta


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke F9: tabla por polígono (local o --drive)")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--drive", action="store_true",
                    help="Fuerza umbral 0: lanza Export.table.toDrive y sigue el task por id")
    ap.add_argument("--carpeta", default="GEE_smoke", help="Carpeta destino en Drive (con --drive)")
    ap.add_argument("--intervalo-ms", type=int, default=10_000, help="Intervalo de polling (--drive)")
    args = ap.parse_args()

    # Imports pesados recién acá: `--help` no necesita ee ni Qt.
    from PySide6.QtCore import QCoreApplication

    from app.dominio import tabla_poligonos
    from app.dominio.aoi import FuenteAOI
    from app.dominio.receta import Receta
    from app.gee.auth import asegurar_sesion
    from app.gee.exportador import ConfigExportTabla, ExportadorGEE
    from app.gee.registro_exports import RegistroExports, nueva_entrada
    from app.ui.workers import PollerTask, WorkerTabla

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)  # noqa: F841
    project = asegurar_sesion(args.project)
    print(f"[auth] sesión GEE lista con project '{project}'")

    tmp = Path(tempfile.mkdtemp(prefix="smoke_f9_"))
    shp = _shapefile_de_prueba(tmp)
    fc = FuenteAOI.desde_archivo_features(shp)
    receta = Receta(
        sensor="COPERNICUS/S2_SR_HARMONIZED", indices=["NDVI"],
        geometria=FuenteAOI.desde_archivo(shp), fecha_inicio="2024-01-01", fecha_fin="2024-03-01",
        mascara_nubes=True, composicion="median", salida="descarga", escala=10,
        producto="tabla_poligonos", features=fc)
    columnas = tabla_poligonos.columnas_para(fc, receta.indices)
    print(f"[smoke] columnas esperadas: {columnas}")

    if not args.drive:
        ruta = tmp / "tabla.csv"
        w = WorkerTabla(receta, "local", ruta, project_id=project)
        resultado = {}
        w.senales.terminado.connect(lambda r: resultado.update(ok=r))
        w.senales.error.connect(lambda t, m: resultado.update(error=(t, m)))
        w.run()   # en el hilo actual: el smoke es headless
        if "error" in resultado:
            print(f"[smoke] ERROR {resultado['error']}")
            return 1
        print(f"[smoke] CSV: {resultado['ok']}")
        print(Path(resultado["ok"]).read_text(encoding="utf-8-sig"))
        return 0

    tabla_poligonos.UMBRAL_TABLA_LOCAL = 0     # fuerza la rama Drive
    assert not tabla_poligonos.es_local(fc)
    w = WorkerTabla(receta, "drive", project_id=project)
    resultado = {}
    w.senales.terminado.connect(lambda r: resultado.update(fc=r))
    w.senales.error.connect(lambda t, m: resultado.update(error=(t, m)))
    w.run()
    if "error" in resultado:
        print(f"[smoke] ERROR {resultado['error']}")
        return 1
    cfg = ConfigExportTabla("smoke_f9_tabla", "smoke_f9_tabla", args.carpeta, tuple(columnas))
    registro = RegistroExports(tmp / "exports.json")
    task = ExportadorGEE().lanzar_tabla(resultado["fc"], cfg)
    task_id = task.id
    registro.agregar(nueva_entrada(task_id, cfg.descripcion, cfg.destino_registro, args.carpeta))
    print(f"[smoke] task lanzado id={task_id} · registro temporal: {registro.ruta}")

    poller = PollerTask(task_id, project_id=project, intervalo_ms=args.intervalo_ms)
    ultimo = {}

    def on_progreso(tid, prog):
        registro.actualizar_estado(tid, prog.estado.value, prog.mensaje_error, list(prog.uris_destino))
        ultimo["prog"] = prog
        print(f"[smoke] estado={prog.estado.value} crudo={prog.crudo}")

    poller.senales.progreso.connect(on_progreso)
    poller.senales.fallo.connect(lambda tid, msg: print(f"[smoke] FALLO seguimiento: {msg}"))
    poller.run()
    prog = ultimo.get("prog")
    if prog is None:
        print("[smoke] TERMINAL=SIN_ESTADO")
        return 1
    print(f"[smoke] TERMINAL={prog.crudo} error={prog.mensaje_error} uris={prog.uris_destino}")
    return 0 if prog.ok else 1


if __name__ == "__main__":
    sys.exit(main())
