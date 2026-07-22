"""Entrypoint del ejecutable congelado (PyInstaller).

Equivale a `python -m app`, pero con dos cuidados propios del binario:

- `multiprocessing.freeze_support()` antes de cualquier otra cosa: sin esto, un
  subproceso creado por una dependencia relanza el .exe en bucle.
- en build windowed (`console=False`) `sys.stdout`/`stderr` son None, y
  cualquier `print()` de una dependencia revienta con AttributeError.
"""
from __future__ import annotations

import multiprocessing
import os
import sys


def _silenciar_stdio_si_falta() -> None:
    for nombre in ("stdout", "stderr"):
        if getattr(sys, nombre, None) is None:
            setattr(sys, nombre, open(os.devnull, "w", encoding="utf-8"))


def _smoke(reportar) -> int:
    """Verifica sin abrir la UI que el bundle trae todo lo que se carga en runtime.

    Cubre lo que un arranque de la ventana no toca: el catálogo vendorizado, los
    assets del mapa, y sobre todo pyogrio/GDAL, que sólo entra en juego al abrir
    un shapefile y falla en silencio si el bundle quedó sin sus DLLs.
    """
    from pathlib import Path

    from app.dominio.catalogo import indices, sensores

    fallas = []

    catalogo = indices.cargar_catalogo()
    if not catalogo:
        fallas.append("catálogo de índices vacío")
    if "NDVI" not in catalogo:
        fallas.append("NDVI ausente del catálogo")
    elif not indices.sensores_de_indice("NDVI"):
        fallas.append("ningún sensor resuelto para NDVI")
    if not sensores.sensores_con_mascara():
        fallas.append("catálogo de sensores vacío")

    import app.mapa.widget_mapa as wm

    for rel in ("index.html", "mapa.js", "leaflet/leaflet.js", "geoman/leaflet-geoman.min.js"):
        if not (Path(wm.__file__).parent / "assets" / rel).exists():
            fallas.append(f"asset del mapa faltante: {rel}")

    import geopandas as gpd
    import pyogrio
    import shapely.geometry

    if "ESRI Shapefile" not in pyogrio.list_drivers():
        fallas.append("pyogrio sin driver de shapefile (GDAL incompleto en el bundle)")

    # Reproyección real: es lo que carga proj.db, y sin él `to_crs` revienta
    # recién cuando el usuario abre un shapefile que no está en 4326.
    gdf = gpd.GeoDataFrame(
        geometry=[shapely.geometry.box(500000, 6000000, 501000, 6001000)], crs="EPSG:32721"
    ).to_crs("EPSG:4326")
    lon, lat = gdf.geometry.iloc[0].centroid.coords[0]
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        fallas.append(f"reproyección a 4326 dio coordenadas inválidas: {lon}, {lat}")

    import ee  # noqa: F401
    import eemont  # noqa: F401

    from PySide6 import QtWebEngineWidgets  # noqa: F401

    for f in fallas:
        reportar(f"FALLA: {f}")
    reportar("SMOKE OK" if not fallas else "SMOKE FAIL")
    return 1 if fallas else 0


def _correr_smoke() -> int:
    """En build windowed no hay consola donde leer el resultado: además de
    imprimirlo, lo deja en `grb-smoke.log` junto al .exe."""
    from pathlib import Path

    lineas: list[str] = []

    def reportar(linea: str) -> None:
        lineas.append(linea)
        print(linea)

    try:
        return _smoke(reportar)
    except Exception:
        import traceback

        reportar(traceback.format_exc())
        reportar("SMOKE FAIL")
        return 1
    finally:
        log = Path(sys.executable).parent / "grb-smoke.log"
        try:
            log.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        except OSError:
            pass


def main() -> None:
    multiprocessing.freeze_support()
    _silenciar_stdio_si_falta()

    if "--smoke" in sys.argv:
        sys.exit(_correr_smoke())

    from app.ui.ventana_principal import main as arrancar_ui

    arrancar_ui()


if __name__ == "__main__":
    main()
