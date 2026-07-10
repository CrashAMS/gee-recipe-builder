"""Workers de fondo para no bloquear el hilo Qt — patrón reutilizado por F3b y F4."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.dominio.receta import Receta
from app.gee import auth, ejecutor
from app.gee.auth import ErrorAuthGEE
from app.gee.errores import ErrorEjecucionGEE


def solicitud_desde_receta(receta: Receta) -> "ejecutor.SolicitudEjecucion":
    """Adapter Receta (F1) → SolicitudEjecucion (F2) — decisión #8 de F2 lo asigna a F3a.

    Único lugar donde el GeoJSON dict de F1 se convierte a ee.Geometry.
    Requiere sesión GEE ya inicializada (llamar después de auth.asegurar_sesion).
    """
    import ee  # import tardío: solo cuando ya hay sesión GEE

    return ejecutor.SolicitudEjecucion(
        collection_id=receta.sensor,
        aoi=ee.Geometry(receta.geometria),      # F1 entrega GeoJSON dict, nunca ee.Geometry
        fecha_inicio=receta.fecha_inicio,
        fecha_fin=receta.fecha_fin,
        indice=receta.indice,
        mascara_nubes=receta.mascara_nubes,
        reduccion=receta.composicion.value,     # enum de F1 → string que _REDUCTORES de F2 conoce
        scale=receta.escala,
        params_indice=dict(receta.parametros),
    )


class SenalesWorker(QObject):
    """Señales de un worker. QRunnable no puede tener señales propias, por eso este QObject."""
    terminado = Signal(object)   # payload de éxito (ej. ruta del .tif)
    error = Signal(str, str)     # (tipo, mensaje_accionable)
    finalizado = Signal()        # se emite SIEMPRE (éxito o error) para rehabilitar la UI


class WorkerDescarga(QRunnable):
    """Asegura sesión GEE y baja la receta a `destino`. Corre en QThreadPool."""

    def __init__(self, receta: Receta, destino: Path, project_id: str | None = None) -> None:
        super().__init__()
        self.receta = receta
        self.destino = destino
        self.project_id = project_id   # None → asegurar_sesion usa el project persistido en config
        self.senales = SenalesWorker()

    @Slot()
    def run(self) -> None:
        try:
            auth.asegurar_sesion(self.project_id)   # Initialize primero; browser solo la 1ª vez
            sol = solicitud_desde_receta(self.receta)
            ruta = ejecutor.ejecutar_a_disco(sol, str(self.destino))
            self.senales.terminado.emit(ruta)
        except ErrorAuthGEE as e:
            self.senales.error.emit("auth", str(e))
        except ErrorEjecucionGEE as e:
            self.senales.error.emit(type(e).__name__, str(e))
        except Exception as e:  # noqa: BLE001 — todo fallo vuelve a la UI, el worker no muere en silencio
            self.senales.error.emit("inesperado", str(e))
        finally:
            self.senales.finalizado.emit()
