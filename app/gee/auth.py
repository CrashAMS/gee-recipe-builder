"""Onboarding OAuth + Cloud project + persistencia — F2 [decisión #2]."""
import ee

from . import config


class ErrorAuthGEE(Exception):
    """No se pudo dejar una sesión de GEE inicializada."""


def intentar_inicializar(project_id: str) -> bool:
    """Prueba ee.Initialize con el project dado. True si quedó lista la sesión."""
    try:
        ee.Initialize(project=project_id)
        return True
    except Exception:
        return False


def autenticar_localhost() -> None:
    """Flujo OAuth de escritorio: abre el browser, sin copiar/pegar [HALLAZGO-1.5]."""
    ee.Authenticate(auth_mode="localhost")


def asegurar_sesion(project_id: str | None = None) -> str:
    """Deja una sesión de GEE inicializada y devuelve el project usado.

    Orden [decisión #2]: project provisto > persistido; Initialize primero;
    Authenticate(localhost) solo si Initialize falla; persiste el project al final.
    """
    project = project_id or config.leer_project()
    if project is None:
        raise ErrorAuthGEE(
            "No hay Google Cloud project configurado. Pasá --project <id> "
            "(registrá uno noncommercial en code.earthengine.google.com/register "
            "y habilitá la Earth Engine API)."
        )

    if intentar_inicializar(project):
        config.guardar_project(project)
        return project

    # Initialize falló → credenciales ausentes/vencidas: autenticar y reintentar.
    autenticar_localhost()
    if intentar_inicializar(project):
        config.guardar_project(project)
        return project

    raise ErrorAuthGEE(
        f"No se pudo inicializar GEE con el project '{project}' aún después de "
        "autenticar. Verificá que el project exista y tenga la Earth Engine API habilitada."
    )
