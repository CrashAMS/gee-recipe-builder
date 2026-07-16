"""ExportadorGEE — arma y lanza tasks de export asíncrono a Drive / Cloud Storage
vía ee.batch.Export.image, y traduce el estado del task para la UI.

Adapter fino sobre earthengine-api (DEC-F2 / DEC-1 de F0): NO reimplementa
polling ni reintentos (eso lo orquesta el worker Qt) — solo construye el task,
lo arranca, traduce su estado y lo cancela.

Auth (DEC-3 de F0): toDrive corre server-side bajo la identidad EE del usuario
autenticado (las MISMAS credenciales OAuth de F2) y escribe en SU Drive. El
cliente nunca toca la Drive API ni pide scopes extra. `folder` es un nombre de
carpeta plano en la raíz del Drive (GEE la crea si no existe; sin paths anidados).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import ee


class DestinoExport(str, Enum):
    DRIVE = "drive"
    CLOUD_STORAGE = "cloud_storage"


class EstadoExport(str, Enum):
    PENDIENTE = "pendiente"    # UNSUBMITTED / READY
    CORRIENDO = "corriendo"    # RUNNING
    COMPLETADO = "completado"  # COMPLETED
    FALLIDO = "fallido"        # FAILED
    CANCELADO = "cancelado"    # CANCEL_REQUESTED / CANCELLED


# Estados crudos de ee.batch.Task.State -> estado de dominio de la app.
_MAPA_ESTADOS = {
    "UNSUBMITTED": EstadoExport.PENDIENTE,
    "READY": EstadoExport.PENDIENTE,
    "RUNNING": EstadoExport.CORRIENDO,
    "COMPLETED": EstadoExport.COMPLETADO,
    "FAILED": EstadoExport.FALLIDO,
    "CANCEL_REQUESTED": EstadoExport.CANCELADO,
    "CANCELLED": EstadoExport.CANCELADO,
}

_TERMINALES = {EstadoExport.COMPLETADO, EstadoExport.FALLIDO, EstadoExport.CANCELADO}

# Patrones de error de cuota / límite de la Task API (aparecen tanto en la
# EEException de task.start() como en error_message de un status FAILED).
_PATRONES_CUOTA = re.compile(
    r"too many tasks|quota|concurrent|rate limit|user memory limit|"
    r"limit.*exceeded|exceeded.*limit",
    re.IGNORECASE,
)

# description del task: GEE solo acepta [a-zA-Z0-9_-], máx 100 chars.
_SANITIZA_DESC = re.compile(r"[^a-zA-Z0-9_-]")


@dataclass(frozen=True)
class ProgresoExport:
    """Snapshot inmutable del estado de un task, listo para la UI."""
    estado: EstadoExport
    crudo: str                    # state original de GEE (para logs)
    mensaje_error: str | None     # error_message si FAILED
    task_id: str | None
    uris_destino: tuple[str, ...] = ()  # destination_uris (link a Drive al completar)

    @property
    def terminal(self) -> bool:
        return self.estado in _TERMINALES

    @property
    def ok(self) -> bool:
        return self.estado is EstadoExport.COMPLETADO


@dataclass(frozen=True)
class ConfigExport:
    """Parámetros de un export. `region` es una ee.Geometry (de FuenteAOI/F1)."""
    descripcion: str                     # nombre visible del task
    prefijo_archivo: str                 # fileNamePrefix (nombre del .tif)
    destino: DestinoExport
    region: "ee.Geometry"
    carpeta_drive: str | None = None     # folder (solo Drive)
    bucket: str | None = None            # bucket (solo Cloud Storage)
    scale: float = 30.0
    crs: str = "EPSG:4326"
    max_pixels: int = 1_000_000_000      # 1e9: exports grandes son el caso de esta fase


def sanitizar_descripcion(nombre: str) -> str:
    """Deja `description` en el charset que GEE acepta ([a-zA-Z0-9_-], <=100)."""
    limpio = _SANITIZA_DESC.sub("_", (nombre or "").strip())
    return (limpio or "export_gee")[:100]


def interpretar_estado(status: dict) -> ProgresoExport:
    """Traduce el dict de task.status() a ProgresoExport. Función pura."""
    crudo = status.get("state", "UNSUBMITTED")
    return ProgresoExport(
        estado=_MAPA_ESTADOS.get(crudo, EstadoExport.PENDIENTE),
        crudo=crudo,
        mensaje_error=status.get("error_message"),
        task_id=status.get("id"),
        uris_destino=tuple(status.get("destination_uris") or ()),
    )


def es_error_de_cuota(exc: Exception | str) -> bool:
    """True si el mensaje matchea patrones de cuota/límite de la Task API. Pura."""
    return bool(_PATRONES_CUOTA.search(str(exc)))


def construir_task(image: "ee.Image", cfg: ConfigExport) -> "ee.batch.Task":
    """Arma el ee.batch.Task según destino. NO lo arranca (eso es .start()).

    Firmas oficiales (earthengine-api):
      ee.batch.Export.image.toDrive(image, description, folder, fileNamePrefix,
          region, scale, crs, maxPixels, fileFormat, ...)
      ee.batch.Export.image.toCloudStorage(image, description, bucket,
          fileNamePrefix, region, scale, crs, maxPixels, fileFormat, ...)
    """
    comun = dict(
        image=image,
        description=sanitizar_descripcion(cfg.descripcion),
        fileNamePrefix=sanitizar_descripcion(cfg.prefijo_archivo),
        region=cfg.region,
        scale=cfg.scale,
        crs=cfg.crs,
        maxPixels=cfg.max_pixels,
        fileFormat="GeoTIFF",
    )
    if cfg.destino is DestinoExport.DRIVE:
        return ee.batch.Export.image.toDrive(folder=cfg.carpeta_drive, **comun)
    return ee.batch.Export.image.toCloudStorage(bucket=cfg.bucket, **comun)


class ExportadorGEE:
    """Adapter sin estado: construye/arranca/consulta/cancela tasks de export."""

    def lanzar(self, image: "ee.Image", cfg: ConfigExport) -> "ee.batch.Task":
        """Construye y arranca el task. Puede levantar EEException (cuota / inválido)."""
        task = construir_task(image, cfg)
        task.start()
        return task

    @staticmethod
    def estado(task: "ee.batch.Task") -> ProgresoExport:
        return interpretar_estado(task.status())

    @staticmethod
    def cancelar(task: "ee.batch.Task") -> None:
        """Cancela el task server-side. Best-effort (no re-levanta)."""
        try:
            task.cancel()
        except Exception:
            pass
