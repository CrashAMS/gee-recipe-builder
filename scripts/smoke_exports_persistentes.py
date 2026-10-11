"""Smoke real de F5: export persistente por task_id (reinicio simulado) + cancelación.

Uso: python -m scripts.smoke_exports_persistentes [--project ID] [--carpeta NOMBRE] [--cancelar]
Requiere credenciales OAuth de GEE (flujo de F2). Lanza un export NDVI chico a Drive,
lo registra en un `exports.json` TEMPORAL (no toca el registro real de la app), descarta
el objeto Task (= "reinicio") y lo sigue con un `PollerTask` NUEVO solo por id
(`ee.data.getTaskStatus`), como hace la app al abrir. Con `--cancelar` el poller pide
`cancelar_por_id` antes del primer poll. Imprime `TERMINAL=<state>`
(COMPLETED esperado sin flag; CANCELLED con `--cancelar`).
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke F5: export persistente por id (+ --cancelar)")
    ap.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                    help="Google Cloud project ID (o env GEE_PROJECT)")
    ap.add_argument("--carpeta", default="GEE_smoke", help="Carpeta destino en la raíz de Drive")
    ap.add_argument("--cancelar", action="store_true",
                    help="Cancela el task por id (cancelar_por_id) en vez de esperar a que termine")
    ap.add_argument("--intervalo-ms", type=int, default=10_000, help="Intervalo de polling")
    args = ap.parse_args()

    # Imports pesados recién acá: `--help` no necesita ee ni Qt.
    import ee
    from PySide6.QtCore import QCoreApplication

    from app.gee.auth import asegurar_sesion
    from app.gee.exportador import ConfigExport, DestinoExport, ExportadorGEE
    from app.gee.registro_exports import RegistroExports, nueva_entrada
    from app.ui.workers import PollerTask

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)  # noqa: F841
    project = asegurar_sesion(args.project)
    print(f"[auth] sesión GEE lista con project '{project}'")

    aoi = ee.Geometry.Rectangle([-58.45, -34.62, -58.40, -34.58])  # ~CABA chica
    imagen = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
              .filterDate("2024-01-01", "2024-03-01").median()
              .normalizedDifference(["B8", "B4"]).rename("NDVI"))
    cfg = ConfigExport(descripcion="smoke_f5_persistente", prefijo_archivo="smoke_f5_persistente",
                       destino=DestinoExport.DRIVE, region=aoi, carpeta_drive=args.carpeta, scale=10)

    registro = RegistroExports(Path(tempfile.mkdtemp(prefix="smoke_f5_")) / "exports.json")
    task = ExportadorGEE().lanzar(imagen, cfg)
    task_id = task.id
    registro.agregar(nueva_entrada(task_id, cfg.descripcion, cfg.destino.value, args.carpeta))
    del task   # "reinicio": desde acá solo existe el id del registro
    print(f"[smoke] task lanzado id={task_id} · registro temporal: {registro.ruta}")

    pendientes = [e["task_id"] for e in registro.pendientes()]
    assert pendientes == [task_id], pendientes
    poller = PollerTask(task_id, project_id=project, intervalo_ms=args.intervalo_ms)
    ultimo = {}

    def on_progreso(tid, prog):
        registro.actualizar_estado(tid, prog.estado.value, prog.mensaje_error, list(prog.uris_destino))
        ultimo["prog"] = prog
        print(f"[smoke] estado={prog.estado.value} crudo={prog.crudo}")

    poller.senales.progreso.connect(on_progreso)
    poller.senales.fallo.connect(lambda tid, msg: print(f"[smoke] FALLO seguimiento: {msg}"))
    if args.cancelar:
        print("[smoke] pidiendo cancelar_por_id…")
        poller.solicitar_cancelacion()
    poller.run()   # en el hilo actual: el smoke es headless

    prog = ultimo.get("prog")
    if prog is None:
        print("[smoke] TERMINAL=SIN_ESTADO")
        return 1
    e = registro.obtener(task_id)
    print(f"[smoke] TERMINAL={prog.crudo} error={prog.mensaje_error} uris={prog.uris_destino} "
          f"registro.estado={e['estado']}")
    esperado = "cancelado" if args.cancelar else "completado"
    return 0 if prog.estado.value == esperado else 1


if __name__ == "__main__":
    sys.exit(main())
