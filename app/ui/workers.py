"""Workers de fondo para no bloquear el hilo Qt — patrón reutilizado por F3b y F4."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.dominio.receta import Receta
from app.gee import auth, ejecutor
from app.gee.auth import ErrorAuthGEE
from app.gee.errores import ErrorEjecucionGEE
from app.gee.exportador import ConfigExport, ExportadorGEE, es_error_de_cuota


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


class WorkerPreview(QRunnable):
    """Genera la URL de tiles del preview (F3b) en QThreadPool — mismo patrón robusto
    que WorkerDescarga. Todo el pipeline GEE (auth + imagen + stretch + getMapId) corre
    en este único hilo. `terminado` emite la url_format lista para L.tileLayer."""

    def __init__(self, receta: Receta, project_id: str | None = None) -> None:
        super().__init__()
        self.receta = receta
        self.project_id = project_id
        self.senales = SenalesWorker()

    @Slot()
    def run(self) -> None:
        try:
            from app.mapa.preview import url_tiles_para

            auth.asegurar_sesion(self.project_id)
            sol = solicitud_desde_receta(self.receta)
            imagen = ejecutor.construir_imagen(sol)
            url = url_tiles_para(imagen)
            self.senales.terminado.emit(url)
        except ErrorAuthGEE as e:
            self.senales.error.emit("auth", str(e))
        except ErrorEjecucionGEE as e:
            self.senales.error.emit(type(e).__name__, str(e))
        except Exception as e:  # noqa: BLE001
            self.senales.error.emit("inesperado", str(e))
        finally:
            self.senales.finalizado.emit()


class WorkerConstruirImagenExport(QRunnable):
    """Punto de entrada del camino Drive (F4, DEC-2 de F0): asegura sesión y
    construye la ee.Image de la receta vía `ejecutor.imagen_indice` (el alias
    estable que F2 dejó para consumidores fuera del módulo, sin recomputar
    nada aparte del pipeline puro y determinístico de la receta actual).
    Mismo patrón robusto que WorkerDescarga/WorkerPreview: `terminado` emite
    `(imagen, region)` listo para abrir `DialogoExportDrive` en el hilo Qt."""

    def __init__(self, receta: Receta, project_id: str | None = None) -> None:
        super().__init__()
        self.receta = receta
        self.project_id = project_id
        self.senales = SenalesWorker()

    @Slot()
    def run(self) -> None:
        try:
            auth.asegurar_sesion(self.project_id)
            sol = solicitud_desde_receta(self.receta)
            imagen = ejecutor.imagen_indice(sol)
            self.senales.terminado.emit((imagen, sol.aoi))
        except ErrorAuthGEE as e:
            self.senales.error.emit("auth", str(e))
        except ErrorEjecucionGEE as e:
            self.senales.error.emit(type(e).__name__, str(e))
        except Exception as e:  # noqa: BLE001
            self.senales.error.emit("inesperado", str(e))
        finally:
            self.senales.finalizado.emit()


_INTERVALO_POLL_MS = 10_000  # 10 s entre consultas de status (DEC-4 de F0). Configurable.
_PASO_SLEEP_MS = 500         # granularidad del sleep interrumpible


class SenalesExport(QObject):
    """Señales del polling de export. QRunnable no puede tener señales propias."""
    iniciado = Signal(str)        # task_id, cuando el task arranca OK
    progreso = Signal(object)     # ProgresoExport en cada poll
    completado = Signal(object)   # ProgresoExport terminal OK
    fallo = Signal(str)           # mensaje de error (cuota / FAILED / cancelado / red)
    finalizado = Signal()         # se emite SIEMPRE (éxito o error) para rehabilitar la UI


class ExportPollingWorker(QRunnable):
    """Arranca un export y poolea su estado en QThreadPool, emitiendo señales Qt.

    Todo el ciclo de red vive acá (DEC-4 de F0): task.start() incluido, para que
    los errores de cuota de arranque salgan por `fallo` sin congelar la UI.
    Usa QRunnable + QThreadPool (no QThread manual): el QThread manual perdía
    señales y dejaba botones colgados (bug real de F3b) — `finalizado` emitido
    en `finally` SIEMPRE rehabilita la UI, sea cual sea el desenlace."""

    def __init__(self, image, cfg: ConfigExport, exportador: ExportadorGEE | None = None,
                 intervalo_ms: int = _INTERVALO_POLL_MS) -> None:
        super().__init__()
        # El diálogo retiene `self._worker` para poder cancelar (B3 del audit de
        # cierre): sin esto, el pool borra el QRunnable C++ apenas `run()`
        # termina y un clic en "Cancelar" en esa ventana pega contra un objeto
        # ya destruido (RuntimeError sin capturar). El diálogo es dueño del
        # ciclo de vida; nadie más llama a `deleteLater()` sobre este worker.
        self.setAutoDelete(False)
        self._image = image
        self._cfg = cfg
        self._exportador = exportador or ExportadorGEE()
        self._intervalo_ms = intervalo_ms
        self._cancelado = threading.Event()
        self.senales = SenalesExport()

    def solicitar_cancelacion(self) -> None:
        """Llamado desde el hilo Qt al presionar "Cancelar" (DEC-9 de F0)."""
        self._cancelado.set()

    def _dormir_interrumpible(self, ms: int) -> bool:
        """Duerme hasta `ms` en pasos chicos, chequeando cancelación. True si se canceló."""
        restante = ms
        while restante > 0:
            if self._cancelado.is_set():
                return True
            paso = min(_PASO_SLEEP_MS, restante)
            time.sleep(paso / 1000)
            restante -= paso
        return False

    @Slot()
    def run(self) -> None:
        try:
            try:
                task = self._exportador.lanzar(self._image, self._cfg)
            except Exception as exc:
                if es_error_de_cuota(exc):
                    self.senales.fallo.emit(
                        "Cuota de tasks de GEE excedida. Esperá a que terminen tasks "
                        f"en curso o cancelá alguna e intentá de nuevo.\n\nDetalle: {exc}"
                    )
                else:
                    self.senales.fallo.emit(str(exc))
                return

            self.senales.iniciado.emit(getattr(task, "id", "") or "")

            while True:
                if self._cancelado.is_set():
                    self._exportador.cancelar(task)  # cancela server-side (DEC-9)
                    self.senales.fallo.emit("Export cancelado por el usuario.")
                    return
                prog = self._exportador.estado(task)
                self.senales.progreso.emit(prog)
                if prog.ok:
                    self.senales.completado.emit(prog)
                    return
                if prog.terminal:  # FAILED / CANCELLED
                    self.senales.fallo.emit(prog.mensaje_error or f"Export {prog.crudo}")
                    return
                if self._dormir_interrumpible(self._intervalo_ms):
                    self._exportador.cancelar(task)
                    self.senales.fallo.emit("Export cancelado por el usuario.")
                    return
        except Exception as exc:  # noqa: BLE001 — red caída / status ilegible a mitad del poll
            self.senales.fallo.emit(f"Se perdió el seguimiento del export: {exc}")
        finally:
            self.senales.finalizado.emit()
