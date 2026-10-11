"""Serialización pura de `Receta` a/desde JSON (formato v1). Sin Qt ni GEE.

Shape: {"version": 1, "receta": {<campos de Receta>}, "aoi": <descriptor | null>}.
Los campos de `Receta` se obtienen por introspección (`dataclasses.fields`), no con una
lista a mano: un campo con default agregado después viaja solo, sin tocar este módulo."""
from __future__ import annotations

import json
from datetime import date
from dataclasses import MISSING, dataclass, fields
from enum import Enum

from app.dominio.errores import RecetaJSONInvalida
from app.dominio.receta import Receta

VERSION = 1


@dataclass(frozen=True)
class RecetaCargada:
    receta: Receta
    descriptor_aoi: dict | None = None


def a_json(receta: Receta, descriptor_aoi: dict | None = None) -> str:
    campos = {}
    for f in fields(Receta):
        valor = getattr(receta, f.name)
        campos[f.name] = valor.value if isinstance(valor, Enum) else valor
    return json.dumps({"version": VERSION, "receta": campos, "aoi": descriptor_aoi},
                      indent=2, ensure_ascii=False)


def _validar_tipos(k: dict) -> None:
    for nombre in ("sensor", "fecha_inicio", "fecha_fin", "composicion", "salida"):
        if not isinstance(k[nombre], str):
            raise RecetaJSONInvalida(f"'{nombre}' debe ser texto (se recibió {k[nombre]!r}).")
    ind = k["indices"]
    if not isinstance(ind, list) or not ind or not all(isinstance(i, str) for i in ind):
        raise RecetaJSONInvalida(
            f"'indices' debe ser una lista no vacía de nombres de índice (se recibió {ind!r}).")
    if "producto" in k and not isinstance(k["producto"], str):
        raise RecetaJSONInvalida(f"'producto' debe ser texto (se recibió {k['producto']!r}).")
    if "periodo" in k and k["periodo"] is not None and not isinstance(k["periodo"], str):
        raise RecetaJSONInvalida(f"'periodo' debe ser texto o null (se recibió {k['periodo']!r}).")
    for nombre in ("fecha_inicio", "fecha_fin"):
        try:
            date.fromisoformat(k[nombre])
        except ValueError as e:
            raise RecetaJSONInvalida(f"'{nombre}' debe ser una fecha yyyy-MM-dd ({k[nombre]!r}).") from e
    if not isinstance(k["mascara_nubes"], bool):
        raise RecetaJSONInvalida("'mascara_nubes' debe ser true o false.")
    if "escala" in k and (isinstance(k["escala"], bool) or not isinstance(k["escala"], int)):
        raise RecetaJSONInvalida(f"'escala' debe ser un entero (se recibió {k['escala']!r}).")
    if "parametros" in k:
        p = k["parametros"]
        if not isinstance(p, dict) or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in p.values()):
            raise RecetaJSONInvalida("'parametros' debe ser un objeto nombre -> número.")


def _traducir_indice_legado(datos: dict) -> dict:
    """Recetas previas a F6b guardaban `"indice": "X"` → `indices=["X"]`. Si vienen las
    dos claves, deben coincidir con el shim (`indices[0] == indice`)."""
    if "indice" not in datos:
        return datos
    legado = datos["indice"]
    if not isinstance(legado, str):
        raise RecetaJSONInvalida(f"'indice' debe ser texto (se recibió {legado!r}).")
    datos = {k: v for k, v in datos.items() if k != "indice"}
    if "indices" not in datos:
        datos["indices"] = [legado]
    elif not (isinstance(datos["indices"], list) and datos["indices"][:1] == [legado]):
        raise RecetaJSONInvalida(
            f"'indice' ({legado!r}) e 'indices' ({datos['indices']!r}) no coinciden; "
            "dejá solo 'indices'.")
    return datos


def desde_json(texto: str) -> RecetaCargada:
    try:
        raiz = json.loads(texto)
    except json.JSONDecodeError as e:
        raise RecetaJSONInvalida(f"El archivo no es un JSON válido ({e.msg}, línea {e.lineno}).") from e
    if not isinstance(raiz, dict):
        raise RecetaJSONInvalida("Se esperaba un objeto JSON con 'version' y 'receta'.")

    version = raiz.get("version")
    if version is None:
        raise RecetaJSONInvalida("Falta el campo 'version'; no parece una receta de esta app.")
    if isinstance(version, bool) or not isinstance(version, int):
        raise RecetaJSONInvalida(f"'version' debe ser un entero (se recibió {version!r}).")
    if version > VERSION:
        raise RecetaJSONInvalida(
            f"Receta versión {version}: fue generada con una versión más nueva de la app "
            f"(esta lee hasta la versión {VERSION}).")
    if version != VERSION:
        raise RecetaJSONInvalida(f"Versión de receta no soportada: {version}.")

    datos = raiz.get("receta")
    if not isinstance(datos, dict):
        raise RecetaJSONInvalida("Falta el objeto 'receta'.")
    geom = datos.get("geometria")
    if not isinstance(geom, dict) or "type" not in geom:
        raise RecetaJSONInvalida(
            "Falta la geometría de la receta ('geometria' debe ser un GeoJSON con 'type').")

    datos = _traducir_indice_legado(datos)
    kwargs = {}
    for f in fields(Receta):
        if f.name in datos:
            kwargs[f.name] = datos[f.name]
        elif f.default is MISSING and f.default_factory is MISSING:
            raise RecetaJSONInvalida(f"Falta el campo obligatorio '{f.name}' en la receta.")
    _validar_tipos(kwargs)
    try:                      # campos desconocidos del JSON se ignoran (forward-compat)
        receta = Receta(**kwargs)
    except (ValueError, TypeError) as e:
        raise RecetaJSONInvalida(f"Valor inválido en la receta: {e}") from e

    aoi = raiz.get("aoi")
    if aoi is not None and not isinstance(aoi, dict):
        raise RecetaJSONInvalida("'aoi' debe ser un objeto descriptor o null.")
    return RecetaCargada(receta, aoi)
