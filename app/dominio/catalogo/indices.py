"""CatálogoÍndices — carga y modelo de los índices ASI vendorizados (tag 0.11.0)."""
from __future__ import annotations
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.dominio.errores import SimboloDesconocido
from app.dominio.catalogo.kernel import resolver_kernel, es_simbolo_kernel
from app.dominio.catalogo.sensores import sensores_compatibles

_VENDOR = Path(__file__).parent / "vendor"


@dataclass(frozen=True)
class ParametroAjustable:
    """Un parámetro ajustable de un índice, con lo que el form (F3a) necesita
    para renderizar nombre + default + tooltip sin ir a buscar el JSON de nuevo."""
    nombre: str
    default: float
    descripcion: str = ""


@dataclass(frozen=True)
class Indice:
    short_name: str
    long_name: str
    formula: str
    application_domain: str
    bandas_requeridas: frozenset[str]
    parametros_ajustables: tuple[ParametroAjustable, ...]
    platforms_texto: tuple[str, ...]
    es_kernel: bool


@lru_cache(maxsize=1)
def _cargar_json(nombre: str) -> dict:
    return json.loads((_VENDOR / nombre).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def simbolos_banda() -> frozenset[str]:
    return frozenset(_cargar_json("bands.json").keys())


@lru_cache(maxsize=1)
def _constantes() -> dict[str, dict]:
    return _cargar_json("constants.json")


def _clasificar(short_name: str, bands: list[str]) -> tuple[frozenset[str], dict[str, ParametroAjustable]]:
    """Devuelve (bandas_requeridas, {simbolo: ParametroAjustable}). Levanta ante símbolo desconocido."""
    bandas: set[str] = set()
    params: dict[str, ParametroAjustable] = {}
    reales = simbolos_banda()
    consts = _constantes()
    for s in bands:
        if s in reales:
            bandas.add(s)
        elif s in consts:
            params[s] = ParametroAjustable(s, consts[s]["default"], consts[s].get("description", ""))
        elif es_simbolo_kernel(s):
            b, p = resolver_kernel(s, consts)
            bandas |= b
            for k, v in p.items():
                params[k] = ParametroAjustable(k, v, consts.get(k, {}).get("description", ""))
        else:
            raise SimboloDesconocido(f"{short_name}: símbolo '{s}' no es banda, constante ni kernel")
    return frozenset(bandas), params


@lru_cache(maxsize=1)
def cargar_catalogo() -> dict[str, Indice]:
    """Carga el catálogo completo, EXCLUYENDO application_domain == 'radar' ([F0]
    decisión 2: SAR excluido — ningún sensor del catálogo lo soporta, y sus símbolos
    de banda VV/VH/HH/HV no están en bands.json/constants.json)."""
    crudo = _cargar_json("spectral-indices-dict.json")["SpectralIndices"]
    catalogo: dict[str, Indice] = {}
    for sn, e in crudo.items():
        if e["application_domain"] == "radar":
            continue
        bandas, params = _clasificar(sn, e["bands"])
        catalogo[sn] = Indice(
            short_name=sn,
            long_name=e["long_name"],
            formula=e["formula"],
            application_domain=e["application_domain"],
            bandas_requeridas=bandas,
            parametros_ajustables=tuple(sorted(params.values(), key=lambda p: p.nombre)),
            platforms_texto=tuple(e.get("platforms", [])),
            es_kernel=(e["application_domain"] == "kernel"),
        )
    return catalogo


def sensores_de_indice(short_name: str) -> list[str]:
    idx = cargar_catalogo()[short_name]
    return sensores_compatibles(idx.bandas_requeridas)


def buscar(texto: str) -> list[Indice]:
    t = texto.lower()
    return [i for i in cargar_catalogo().values()
            if t in i.short_name.lower() or t in i.long_name.lower()]
