"""Resolución de símbolos kernel (application_domain='kernel') a bandas reales + parámetros.

Transcripto de `ee_extra.Spectral.utils._get_kernel_parameters` (paquete `ee_extra`,
versión pineada `2025.7.2` — fuente descargada del wheel de PyPI, el repo
`davemlz/ee_extra` en GitHub ya no existe). Esa función arma 14 combinaciones
kXY = kernel(a, b) donde a/b son cada uno un símbolo de banda (N, G, B, R) o la
constante 'L' (canopy background adjustment de EVI, ya vendorizada en constants.json).
Sólo bandas reales cuentan como `bandas_requeridas`; 'L' es un parámetro ajustable,
no una banda del sensor.

El catálogo v1 (tag 0.11.0 de ASI) sólo usa kNN/kNR/kNB/kNL (kEVI, kNDVI, kIPVI, kRVI)
y kGG/kGR/kGB (kVARI) — se listan las 14 combinaciones completas para robustez ante
un futuro bump del snapshot.
"""
from __future__ import annotations

_BANDA = {"N", "G", "B", "R"}   # letras de _get_kernel_parameters que son bandas reales
_CONSTANTE = {"L"}              # letras que son constantes (de constants.json), no bandas

_OPERANDOS: dict[str, tuple[str, str]] = {
    "kNN": ("N", "N"), "kNR": ("N", "R"), "kNB": ("N", "B"), "kNL": ("N", "L"),
    "kGG": ("G", "G"), "kGR": ("G", "R"), "kGB": ("G", "B"),
    "kBB": ("B", "B"), "kBR": ("B", "R"), "kBL": ("B", "L"),
    "kRR": ("R", "R"), "kRB": ("R", "B"), "kRL": ("R", "L"),
    "kLL": ("L", "L"),
}


def es_simbolo_kernel(s: str) -> bool:
    return s in _OPERANDOS


def resolver_kernel(s: str, constantes: dict) -> tuple[set[str], dict[str, float]]:
    """Devuelve (bandas_reales_requeridas, {simbolo_constante: default}).

    Todo símbolo kernel requiere 'sigma' (parámetro RBF, ya en constants.json,
    default 0.5). Si alguno de los dos operandos es 'L' (constante), se agrega
    también con su default de constants.json (1.0)."""
    a, b = _OPERANDOS[s]
    bandas = {x for x in (a, b) if x in _BANDA}
    params = {"sigma": constantes["sigma"]["default"]}
    for x in (a, b):
        if x in _CONSTANTE:
            params[x] = constantes[x]["default"]
    return bandas, params
