"""Workers de fondo para no bloquear el hilo Qt — patrón reutilizado por F3b y F4."""
from __future__ import annotations

import threading
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.dominio import catalogo
from app.dominio.errores import FiltroNubesNoDisponible
from app.dominio.receta import Receta
from app.gee import auth, config, ejecutor
from app.gee.auth import ErrorAuthGEE
from app.gee.errores import ErrorEjecucionGEE
from app.gee.exportador import ConfigExport, ExportadorGEE, es_error_de_cuota


def solicitud_desde_receta(receta: Receta) -> "ejecutor.SolicitudEjecucion":
    """Adapter Receta (F1) → SolicitudEjecucion (F2) — decisión #8 de F2 lo asigna a F3a.

    Único lugar donde el GeoJSON dict de F1 se convierte a ee.Geometry.
    Requiere sesión GEE ya inicializada (llamar después de auth.asegurar_sesion).
    """
    import ee  # import tardío: solo cuando ya hay sesión GEE

    prop_nubes = catalogo.propiedad_nubes(receta.sensor)
    if receta.max_nubes_pct is not None and prop_nubes is None:
        raise FiltroNubesNoDisponible(
            f"El sensor {receta.sensor} no tiene propiedad de % de nubes: no se puede filtrar por escena.")

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
        propiedad_nubes=prop_nubes,
        max_nubes_pct=receta.max_nubes_pct,
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
    en este único hilo. `terminado` emite un `PreviewResultado(url, vis, estirado)`.
    `vis_params` (min/max/palette) es el override manual de la UI: con él no se estira
    (se re-pide getMapId tal cual). Sin él se estira por percentiles usando `paleta`."""

    def __init__(self, receta: Receta, project_id: str | None = None,
                 vis_params: dict | None = None, paleta: list[str] | None = None) -> None:
        super().__init__()
        self.receta = receta
        self.project_id = project_id
        self.vis_params = vis_params
        self.paleta = paleta
        self.senales = SenalesWorker()

    @Slot()
    def run(self) -> None:
        try:
            from app.mapa.preview import VIS_PARAMS_DEFAULT, url_tiles_para

            auth.asegurar_sesion(self.project_id)
            sol = solicitud_desde_receta(self.receta)
            imagen = ejecutor.construir_imagen(sol)
            if self.vis_params is not None:
                resultado = url_tiles_para(imagen, self.vis_params, auto_stretch=False)
            else:
                base = dict(VIS_PARAMS_DEFAULT)
                if self.paleta:
                    base["palette"] = list(self.paleta)
                resultado = url_tiles_para(imagen, base, auto_stretch=True)
            self.senales.terminado.emit(resultado)
        except ErrorAuthGEE as e:
            self.senales.error.emit("auth", str(e))
        except ErrorEjecucionGEE as e:
            self.senales.error.emit(type(e).__name__, str(e))
        except Exception as e:  # noqa: BLE001
            self.senales.error.emit("inesperado", str(e))
        finally:
            self.senales.finalizado.emit()


class SenalesConteo(SenalesWorker):
    """Suma `error_gen(generacion, tipo, mensaje)` para conectar a un slot ligado (hilo GUI)."""
    error_gen = Signal(int, str, str)


class WorkerConteo(QRunnable):
    """Cuenta escenas de la receta (total y con < `umbral` % nubes) en QThreadPool.
    `terminado` emite `(generacion, total, con_pocas_nubes)`; la ventana descarta las
    respuestas cuyo token `generacion` ya no es el vigente."""

    def __init__(self, receta: Receta, generacion: int, umbral: int,
                 project_id: str | None = None) -> None:
        super().__init__()
        self.receta = receta
        self.generacion = generacion
        self.umbral = umbral
        self.project_id = project_id
        self.senales = SenalesConteo()

    def _fallo(self, tipo: str, mensaje: str) -> None:
        self.senales.error.emit(tipo, mensaje)
        self.senales.error_gen.emit(self.generacion, tipo, mensaje)

    @Slot()
    def run(self) -> None:
        try:
            auth.asegurar_sesion(self.project_id)
            sol = solicitud_desde_receta(self.receta)
            total, pocas = ejecutor.contar_imagenes(sol, self.umbral)
            self.senales.terminado.emit((self.generacion, total, pocas))
        except ErrorAuthGEE as e:
            self._fallo("auth", str(e))
        except ErrorEjecucionGEE as e:
            self._fallo(type(e).__name__, str(e))
        except Exception as e:  # noqa: BLE001
            self._fallo("inesperado", str(e))
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

# Varios PollerTask recuperados al abrir la app arrancan a la vez: serializar la sesión
# evita Initialize concurrentes y más de un flujo OAuth en el browser.
_LOCK_SESION = threading.Lock()

_MSG_CUOTA = ("Cuota de tasks de GEE excedida. Esperá a que terminen tasks "
              "en curso o cancelá alguna e intentá de nuevo.\n\nDetalle: {exc}")


class SenalesExport(QObject):
    """Señales de lanzamiento/polling de export (F5: cada emisión identifica su task o worker).
    Conectarlas a métodos de un QObject del hilo Qt (GestorExports): así la conexión
    es encolada y el registro en disco solo se escribe desde el hilo Qt."""
    iniciado = Signal(str, object)   # (task_id, ConfigExport) — el task arrancó OK
    progreso = Signal(str, object)   # (task_id, ProgresoExport) en cada poll
    fallo = Signal(str, str)         # PollerTask: (task_id, msg) · WorkerLanzarExport: (clave, msg)
    finalizado = Signal(str)         # (clave del worker) — SIEMPRE, sea cual sea el desenlace
    sin_sesion = Signal(str)         # PollerTask no interactivo: (task_id) — no hay sesión GEE, sin OAuth


class WorkerLanzarExport(QRunnable):
    """Solo lanza el task (red incluida, para no congelar la UI) y emite `iniciado`
    con su id; el seguimiento lo hace `PollerTask`. Requiere sesión ya inicializada
    (la imagen viene de WorkerConstruirImagenExport). `clave` identifica al worker
    en `fallo`/`finalizado` (todavía no hay task_id cuando falla el lanzamiento)."""

    def __init__(self, image, cfg: ConfigExport, exportador: ExportadorGEE | None = None,
                 clave: str | None = None) -> None:
        super().__init__()
        self.setAutoDelete(False)   # el gestor retiene la referencia hasta `finalizado`
        self._image = image
        self._cfg = cfg
        self._exportador = exportador or ExportadorGEE()
        self.clave = clave or uuid.uuid4().hex
        self.task_id = ""           # se fija antes de emitir `iniciado`
        self.senales = SenalesExport()

    @Slot()
    def run(self) -> None:
        try:
            try:
                task = self._exportador.lanzar(self._image, self._cfg)
            except Exception as exc:  # noqa: BLE001
                mensaje = _MSG_CUOTA.format(exc=exc) if es_error_de_cuota(exc) else str(exc)
                self.senales.fallo.emit(self.clave, mensaje)
                return
            task_id = getattr(task, "id", "") or ""
            if not task_id:
                self.senales.fallo.emit(self.clave,
                                        "GEE no devolvió el id del task: no se puede seguir.")
                return
            self.task_id = task_id
            self.senales.iniciado.emit(task_id, self._cfg)
        finally:
            self.senales.finalizado.emit(self.clave)


class PollerTask(QRunnable):
    """Sigue un task por id hasta estado terminal (sirve tras reiniciar la app).
    Interactivo (default, export lanzado por el usuario): `auth.asegurar_sesion` antes de
    consultar (puede abrir el login OAuth). No interactivo (`recuperar()` al abrir la app):
    solo `auth.intentar_inicializar`; sin sesión emite `sin_sesion` y termina sin fallar el
    task ni abrir el browser. Dos flags distintos (decisión 6 F5):
    `detener()` solo corta el polling local (cerrar app) — el task sigue server-side;
    `solicitar_cancelacion()` cancela server-side (`cancelar_por_id`) y sigue poleando
    hasta ver el estado terminal. `finalizado(task_id)` siempre en `finally`."""

    def __init__(self, task_id: str, project_id: str | None = None,
                 exportador: ExportadorGEE | None = None,
                 intervalo_ms: int = _INTERVALO_POLL_MS, interactivo: bool = True) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.task_id = task_id
        self.clave = task_id
        self.project_id = project_id
        self.interactivo = interactivo
        self._exportador = exportador or ExportadorGEE()
        self._intervalo_ms = intervalo_ms
        self._detener = threading.Event()
        self._cancelar = threading.Event()
        self._despertar = threading.Event()
        self._terminado = threading.Event()
        self.senales = SenalesExport()

    def detener(self) -> None:
        self._detener.set()
        self._despertar.set()

    def solicitar_cancelacion(self) -> None:
        self._cancelar.set()
        self._despertar.set()

    def ha_terminado(self) -> bool:
        return self._terminado.is_set()

    def _dormir_interrumpible(self, ms: int) -> None:
        restante = ms
        while restante > 0 and not self._despertar.is_set():
            paso = min(_PASO_SLEEP_MS, restante)
            self._despertar.wait(paso / 1000)
            restante -= paso
        self._despertar.clear()

    @Slot()
    def run(self) -> None:
        cancel_enviado = False
        try:
            with _LOCK_SESION:
                if self.interactivo:
                    auth.asegurar_sesion(self.project_id)
                else:
                    project = self.project_id or config.leer_project()
                    if not project or not auth.intentar_inicializar(project):
                        self.senales.sin_sesion.emit(self.task_id)
                        return
            while not self._detener.is_set():
                if self._cancelar.is_set() and not cancel_enviado:
                    try:
                        self._exportador.cancelar_por_id(self.task_id)
                    except Exception as exc:  # noqa: BLE001 — el task sigue vivo: seguir poleando
                        self.senales.fallo.emit(self.task_id, f"No se pudo cancelar: {exc}")
                    cancel_enviado = True
                prog = self._exportador.estado_por_id(self.task_id)
                self.senales.progreso.emit(self.task_id, prog)
                if prog.terminal:
                    return
                self._dormir_interrumpible(self._intervalo_ms)
        except ErrorAuthGEE as exc:
            self.senales.fallo.emit(self.task_id, f"Sin sesión GEE: {exc}")
        except Exception as exc:  # noqa: BLE001 — red caída / status ilegible a mitad del poll
            self.senales.fallo.emit(self.task_id, f"Se perdió el seguimiento del export: {exc}")
        finally:
            self._terminado.set()
            self.senales.finalizado.emit(self.clave)
