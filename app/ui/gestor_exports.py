"""GestorExports (F5) — dueño del ciclo de vida de los exports a nivel ventana.

Lanza (WorkerLanzarExport), registra el task_id en `exports.json` apenas arranca y lo
sigue con un PollerTask por id. Al abrir la app, `recuperar()` retoma los no terminales.
Todos los slots corren en el hilo Qt (conexiones encoladas a métodos de este QObject),
así el registro nunca se escribe desde hilos del pool. Cerrar diálogo o app NO cancela:
`detener_todo()` solo corta el polling local; cancelar server-side es `cancelar(id)`.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from app.gee.exportador import ConfigExport, ConfigExportTabla, ExportadorGEE, ProgresoExport
from app.gee.registro_exports import RegistroExports, nueva_entrada
from app.ui.workers import (
    _INTERVALO_POLL_MS, PollerTask, WorkerLanzarExport, WorkerLanzarExportTabla)

AVISO_SIN_SESION = "Sin sesión GEE: los exports pendientes se retoman al autenticarte"

# Los PollerTask duermen entre consultas ocupando un hilo: van a un pool PROPIO y acotado
# para que el pool global quede libre para preview/conteo/serie/tabla/descarga (PERF-1).
MAX_HILOS_POLLERS = 4


class GestorExports(QObject):
    cambio = Signal(str)                    # task_id cuyo estado/aviso cambió
    lanzado = Signal(str, str)              # (clave del lanzamiento, task_id)
    fallo_lanzamiento = Signal(str, str)    # (clave del lanzamiento, mensaje)

    def __init__(self, registro: RegistroExports | None = None,
                 exportador: ExportadorGEE | None = None, pool=None,
                 intervalo_ms: int = _INTERVALO_POLL_MS, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.registro = registro or RegistroExports()
        self._exportador = exportador or ExportadorGEE()
        self._pool = pool
        if pool is None:
            self._pool_pollers = QThreadPool(self)
            self._pool_pollers.setMaxThreadCount(MAX_HILOS_POLLERS)
        else:
            self._pool_pollers = pool   # tests: un pool fake para todo
        self._intervalo_ms = intervalo_ms
        self._lanzadores: dict[str, WorkerLanzarExport] = {}
        self._pollers: dict[str, PollerTask] = {}
        self._sin_sesion: set[str] = set()  # pollers de recuperar() que no hallaron sesión GEE
        self._avisos: dict[str, str] = {}   # último error de seguimiento por task (no persiste)

    def _start(self, worker) -> None:
        if isinstance(worker, PollerTask):
            self._pool_pollers.start(worker)
        else:
            (self._pool or QThreadPool.globalInstance()).start(worker)

    # ---- API ----
    def lanzar(self, image, cfg: ConfigExport, clave: str | None = None) -> str:
        """Lanza en el pool y devuelve la clave del lanzamiento (para filtrar
        `lanzado`/`fallo_lanzamiento`; el llamador puede fijarla de antemano)."""
        w = WorkerLanzarExport(image, cfg, exportador=self._exportador, clave=clave)
        w.senales.iniciado.connect(self._on_iniciado)
        w.senales.fallo.connect(self._on_fallo_lanzamiento)
        w.senales.finalizado.connect(self._on_lanzador_finalizado)
        self._lanzadores[w.clave] = w
        self._start(w)
        return w.clave

    def lanzar_tabla(self, fc, cfg_tabla: ConfigExportTabla, clave: str | None = None) -> str:
        """Como `lanzar`, para `Export.table.toDrive` (F9). Se registra con `destino="drive-tabla"`."""
        w = WorkerLanzarExportTabla(fc, cfg_tabla, exportador=self._exportador, clave=clave)
        w.senales.iniciado.connect(self._on_iniciado)
        w.senales.fallo.connect(self._on_fallo_lanzamiento)
        w.senales.finalizado.connect(self._on_lanzador_finalizado)
        self._lanzadores[w.clave] = w
        self._start(w)
        return w.clave

    def recuperar(self) -> int:
        """Arranca un poller por cada entrada no terminal del registro. Devuelve cuántas."""
        pendientes = self.registro.pendientes()
        for e in pendientes:
            self._pollear(e["task_id"], interactivo=False)   # sin OAuth sorpresa al abrir
        return len(pendientes)

    def reintentar_recuperacion(self) -> int:
        """Retoma los pollers que quedaron sin sesión (llamar cuando una sesión se establece)."""
        ids = [t for t in self._sin_sesion if not self.siguiendo(t)]
        self._sin_sesion.clear()
        for t in ids:
            self._avisos.pop(t, None)
            self._pollear(t, interactivo=False)
        return len(ids)

    def cancelar(self, task_id: str) -> None:
        """Cancelación explícita (botón del panel): server-side vía el poller del task."""
        self._avisos.pop(task_id, None)
        self._pollear(task_id, cancelar=True)
        self.cambio.emit(task_id)

    def detener_todo(self) -> None:
        """Cierre de la app: corta el polling local SIN cancelar nada server-side."""
        for p in self._pollers.values():
            p.detener()
            self._desconectar(p)
        for w in self._lanzadores.values():
            # Un lanzamiento en vuelo igual arranca el task server-side; sin gestor
            # escuchando no queda en el registro (ventana de ms al cerrar la app).
            self._desconectar(w)
        self._pollers.clear()
        self._lanzadores.clear()

    def siguiendo(self, task_id: str) -> bool:
        p = self._pollers.get(task_id)
        return p is not None and not p.ha_terminado()

    def aviso(self, task_id: str) -> str | None:
        return self._avisos.get(task_id)

    # ---- internos ----
    def _pollear(self, task_id: str, cancelar: bool = False, interactivo: bool = True) -> None:
        actual = self._pollers.get(task_id)
        if actual is not None and not actual.ha_terminado():
            if cancelar:
                actual.solicitar_cancelacion()
            return
        p = PollerTask(task_id, exportador=self._exportador, intervalo_ms=self._intervalo_ms,
                       interactivo=interactivo)
        if cancelar:
            p.solicitar_cancelacion()
        p.senales.progreso.connect(self._on_progreso)
        p.senales.fallo.connect(self._on_fallo_poller)
        p.senales.sin_sesion.connect(self._on_sin_sesion)
        p.senales.finalizado.connect(self._on_poller_finalizado)
        self._pollers[task_id] = p
        self._start(p)

    def _desconectar(self, w) -> None:
        """Que un worker que sigue corriendo no le hable más al gestor."""
        if isinstance(w, PollerTask):
            pares = ((w.senales.progreso, self._on_progreso),
                     (w.senales.fallo, self._on_fallo_poller),
                     (w.senales.sin_sesion, self._on_sin_sesion),
                     (w.senales.finalizado, self._on_poller_finalizado))
        else:
            pares = ((w.senales.iniciado, self._on_iniciado),
                     (w.senales.fallo, self._on_fallo_lanzamiento),
                     (w.senales.finalizado, self._on_lanzador_finalizado))
        for senal, slot in pares:
            try:
                senal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    @Slot(str, object)
    def _on_iniciado(self, task_id: str, cfg: ConfigExport | ConfigExportTabla) -> None:
        carpeta = cfg.carpeta_drive if cfg.carpeta_drive is not None else cfg.bucket
        destino = (cfg.destino_registro if isinstance(cfg, ConfigExportTabla)
                   else cfg.destino.value)
        try:
            self.registro.agregar(nueva_entrada(task_id, cfg.descripcion, destino, carpeta))
        except OSError as exc:   # disco lleno / permisos: el task igual corre, se sigue en memoria
            self._avisos[task_id] = f"No se pudo guardar en el registro: {exc}"
        self.cambio.emit(task_id)
        self.reintentar_recuperacion()   # lanzar exitoso ⇒ hay sesión: retomar los sin sesión
        clave = next((c for c, w in self._lanzadores.items() if w.task_id == task_id), "")
        self.lanzado.emit(clave, task_id)
        self._pollear(task_id)

    @Slot(str, str)
    def _on_fallo_lanzamiento(self, clave: str, mensaje: str) -> None:
        self.fallo_lanzamiento.emit(clave, mensaje)

    @Slot(str)
    def _on_lanzador_finalizado(self, clave: str) -> None:
        self._lanzadores.pop(clave, None)

    @Slot(str, object)
    def _on_progreso(self, task_id: str, prog: ProgresoExport) -> None:
        try:
            self.registro.actualizar_estado(task_id, prog.estado.value, prog.mensaje_error,
                                            list(prog.uris_destino))
        except OSError as exc:
            self._avisos[task_id] = f"No se pudo guardar en el registro: {exc}"
            self.cambio.emit(task_id)
            return
        self._avisos.pop(task_id, None)
        self.cambio.emit(task_id)

    @Slot(str, str)
    def _on_fallo_poller(self, task_id: str, mensaje: str) -> None:
        # El task puede seguir vivo server-side: no se marca fallido en el registro.
        self._avisos[task_id] = mensaje
        self.cambio.emit(task_id)

    @Slot(str)
    def _on_sin_sesion(self, task_id: str) -> None:
        # No se marca fallido: el task sigue vivo server-side; se retoma al autenticarse.
        self._sin_sesion.add(task_id)
        self._avisos[task_id] = AVISO_SIN_SESION
        self.cambio.emit(task_id)

    @Slot(str)
    def _on_poller_finalizado(self, task_id: str) -> None:
        p = self._pollers.get(task_id)
        if p is not None and p.ha_terminado():
            del self._pollers[task_id]
        self.cambio.emit(task_id)
