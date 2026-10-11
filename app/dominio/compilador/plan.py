"""Plan de compilación neutral: Receta -> PlanCompilacion (sin dialecto).

`construir_plan` traduce la receta a una secuencia ordenada de pasos tipados
(`TipoPaso`) que `dialecto_js` y `dialecto_python` renderizan. El plan no sabe
de sintaxis: nada de nombres de funciones JS, eemont ni strings renderizados.
Los renderers devuelven segmentos `(tipos, lineas)`; `tipos_renderizados`
aplana sus tipos para verificar paridad estructural entre dialectos.

Validación neutral: `FiltroNubesNoDisponible` (sensor sin propiedad de % de
nubes con umbral seteado) sale de acá, antes de cualquier render. Consecuencia
aceptada: una receta doblemente inválida (sin máscara JS **y** sin propiedad de
nubes con umbral) levanta `FiltroNubesNoDisponible` también en JS, no
`MascaraNoDisponibleJS`.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Iterable, Union

from app.dominio.receta import Composicion, Receta
from app.dominio.receta import Salida as DestinoSalida
from app.dominio.compilador.base import prop_nubes_filtro


class TipoPaso(str, Enum):
    FUENTE = "fuente"
    FILTRO_FECHAS = "filtro_fechas"
    FILTRO_NUBES = "filtro_nubes"
    MASCARA = "mascara"
    ESCALA = "escala"
    INDICES = "indices"
    REDUCTOR = "reductor"
    SALIDA = "salida"


@dataclass(frozen=True)
class Fuente:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.FUENTE
    coleccion: str                  # collection ID GEE
    # Copia profunda del GeoJSON de la receta: fuera del hash (dict), sí en la igualdad.
    geometria: dict = field(hash=False)


@dataclass(frozen=True)
class FiltroFechas:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.FILTRO_FECHAS
    inicio: str                     # 'YYYY-MM-DD'
    fin: str


@dataclass(frozen=True)
class FiltroNubes:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.FILTRO_NUBES
    propiedad: str                  # propiedad de metadata con el % de nubes de la escena
    umbral: int                     # descarta escenas con propiedad >= umbral


@dataclass(frozen=True)
class Mascara:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.MASCARA
    coleccion: str                  # la máscara depende de la colección


@dataclass(frozen=True)
class Escala:
    """scaleAndOffset semántico: siempre presente (un dialecto puede no emitir texto)."""
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.ESCALA
    coleccion: str


@dataclass(frozen=True)
class Indices:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.INDICES
    nombres: tuple[str, ...]        # short_names ASI; hoy siempre (r.indice,)
    parametros: tuple[tuple[str, float], ...] = ()  # overrides globales, ordenados por clave


@dataclass(frozen=True)
class Reductor:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.REDUCTOR
    composicion: Composicion


@dataclass(frozen=True)
class Salida:
    tipo_paso: ClassVar[TipoPaso] = TipoPaso.SALIDA
    tipo: DestinoSalida             # descarga / drive / preview
    escala_m: int                   # scale en metros
    bandas: tuple[str, ...]         # == Indices.nombres
    descripcion: str                # nombre de la tarea / capa


Paso = Union[Fuente, FiltroFechas, FiltroNubes, Mascara, Escala, Indices, Reductor, Salida]
# Segmento renderizado: tipos de paso que cubre (vacío = preámbulo) + sus líneas.
Segmento = tuple[tuple[TipoPaso, ...], list[str]]


@dataclass(frozen=True)
class PlanCompilacion:
    pasos: tuple[Paso, ...]

    @property
    def tipos(self) -> tuple[TipoPaso, ...]:
        return tuple(p.tipo_paso for p in self.pasos)

    def paso(self, tipo: TipoPaso) -> Paso | None:
        """El paso de ese tipo, o None si el plan no lo tiene (opcionales)."""
        return next((p for p in self.pasos if p.tipo_paso is tipo), None)


def construir_plan(r: Receta) -> PlanCompilacion:
    """Orden fijo: Fuente → FiltroFechas → FiltroNubes? → Mascara? → Escala →
    Indices → Reductor → Salida. Levanta FiltroNubesNoDisponible (ver docstring
    del módulo)."""
    prop_nubes = prop_nubes_filtro(r)
    nombres = (r.indice,)
    pasos: list[Paso] = [Fuente(r.sensor, copy.deepcopy(r.geometria)), FiltroFechas(r.fecha_inicio, r.fecha_fin)]
    if prop_nubes:
        pasos.append(FiltroNubes(prop_nubes, r.max_nubes_pct))
    if r.mascara_nubes:
        pasos.append(Mascara(r.sensor))
    pasos += [Escala(r.sensor),
              Indices(nombres, tuple(sorted(r.parametros.items()))),
              Reductor(r.composicion),
              Salida(r.salida, r.escala, nombres, r.indice)]
    return PlanCompilacion(tuple(pasos))


def tipos_renderizados(segmentos: Iterable[Segmento]) -> tuple[TipoPaso, ...]:
    """Aplanado de los tipos que cubren los segmentos de un renderer, en orden."""
    return tuple(t for tipos, _ in segmentos for t in tipos)


def unir(segmentos: Iterable[Segmento]) -> str:
    return "\n".join(linea for _, lineas in segmentos for linea in lineas)
