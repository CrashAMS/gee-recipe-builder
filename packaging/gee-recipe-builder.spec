# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para gee-recipe-builder.

Build:  pyinstaller packaging/gee-recipe-builder.spec --noconfirm
Salida: dist/gee-recipe-builder/gee-recipe-builder.exe

Modo onedir (no onefile) a propósito: QtWebEngine — que el mapa interactivo
necesita — arranca un proceso helper (QtWebEngineProcess.exe) y en onefile eso
implica re-extraer ~400 MB en cada arranque, además de romperse seguido.
Para distribuir un solo archivo, comprimir `dist/gee-recipe-builder/` en un zip.

`GRB_CONSOLE=1` en el entorno construye la variante con consola, útil para ver
tracebacks cuando el .exe muere sin decir nada.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = Path(SPECPATH).parent
CON_CONSOLA = os.environ.get("GRB_CONSOLE") == "1"

# --- Datos ---------------------------------------------------------------
# El código resuelve estos assets con `Path(__file__).parent / ...`, que en el
# bundle apunta a la copia extraída; por eso el destino replica el layout del
# repo tal cual.
datas = [
    (str(RAIZ / "app" / "dominio" / "catalogo" / "vendor"), "app/dominio/catalogo/vendor"),
    (str(RAIZ / "app" / "mapa" / "assets"), "app/mapa/assets"),
]

# Catálogos JSON que eemont/ee_extra leen en runtime desde su propio paquete,
# y el bundle de CAs de certifi (requests lo necesita para hablar con GEE).
for paquete in ("eemont", "ee_extra", "certifi"):
    datas += collect_data_files(paquete)

# --- Imports que el análisis estático no ve ------------------------------
# ee_extra despacha por plataforma con importlib, así que ningún import literal
# delata sus submódulos.
hiddenimports = collect_submodules("ee_extra") + [
    "eemont",
    "pyogrio._geometry",
    "pyogrio._io",
]

# Pesan cientos de MB y no se usan: matplotlib entra por geopandas.plot(),
# tkinter por la stdlib, el resto por dependencias de dependencias.
excludes = [
    "tkinter",
    "matplotlib",
    "IPython",
    "notebook",
    "jupyter",
    "pytest",
    "pytest_qt",
    "PyQt5",
    "PyQt6",
    "PySide2",
]

a = Analysis(
    [str(RAIZ / "packaging" / "launcher.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gee-recipe-builder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CON_CONSOLA,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RAIZ / "packaging" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="gee-recipe-builder",
)
