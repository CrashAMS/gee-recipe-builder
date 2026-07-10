"""API pública del CatálogoÍndices — lo único que F3a debe importar."""
from app.dominio.catalogo.indices import cargar_catalogo, sensores_de_indice, Indice, ParametroAjustable
from app.dominio.catalogo.sensores import PERFILES, sensores_con_mascara, PerfilSensor


def listar_indices() -> list[Indice]:
    """Todos los índices del catálogo (values de cargar_catalogo(), no dict)."""
    return list(cargar_catalogo().values())


def sensores_para(indice: Indice | str) -> list[PerfilSensor]:
    """Objetos PerfilSensor compatibles con el índice (no collection IDs sueltos)."""
    short_name = indice.short_name if isinstance(indice, Indice) else indice
    return [PERFILES[cid] for cid in sensores_de_indice(short_name)]


def soporta_mascara(collection_id: str) -> bool:
    """True si ese collection ID tiene maskClouds disponible ([HALLAZGO-2.4])."""
    return collection_id in sensores_con_mascara()
