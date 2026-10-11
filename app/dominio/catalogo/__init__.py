"""API pública del CatálogoÍndices — lo único que F3a debe importar."""
from app.dominio.catalogo.indices import (
    cargar_catalogo, sensores_de_indice, Indice, ParametroAjustable,
    buscar, listar_dominios, etiqueta_dominio, ETIQUETAS_DOMINIO,
)
from app.dominio.catalogo.sensores import PERFILES, sensores_con_mascara, PerfilSensor


def listar_indices() -> list[Indice]:
    """Todos los índices del catálogo (values de cargar_catalogo(), no dict)."""
    return list(cargar_catalogo().values())


def sensores_para(indice: Indice | str) -> list[PerfilSensor]:
    """Objetos PerfilSensor compatibles con el índice (no collection IDs sueltos)."""
    short_name = indice.short_name if isinstance(indice, Indice) else indice
    return [PERFILES[cid] for cid in sensores_de_indice(short_name)]


def sensores_para_indices(indices: list[str]) -> list[PerfilSensor]:
    """Intersección de `sensores_para` de cada índice (decisión F0 6), en el orden de
    `sensores_para(indices[0])`. Lista vacía → []. Short_name inexistente → KeyError claro."""
    if not indices:
        return []
    cat = cargar_catalogo()
    for sn in indices:
        if sn not in cat:
            raise KeyError(f"Índice '{sn}' no existe en el catálogo")
    comunes = set.intersection(*(set(sensores_de_indice(sn)) for sn in indices))
    return [s for s in sensores_para(indices[0]) if s.collection_id in comunes]


def soporta_mascara(collection_id: str) -> bool:
    """True si ese collection ID tiene maskClouds disponible ([HALLAZGO-2.4])."""
    return collection_id in sensores_con_mascara()


def escala_nativa(collection_id: str) -> int | None:
    """Escala nativa (m) del sensor, o None si no hay dato."""
    return PERFILES[collection_id].escala_nativa_m


def rango_fechas(collection_id: str) -> tuple[str | None, str | None]:
    """(inicio, fin) ISO del sensor; fin None = activa hoy."""
    p = PERFILES[collection_id]
    return p.fecha_inicio, p.fecha_fin


def propiedad_nubes(collection_id: str) -> str | None:
    """Propiedad GEE de % nubes de la colección; None si no tiene (MODIS)."""
    return PERFILES[collection_id].prop_nubes
