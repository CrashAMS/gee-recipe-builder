"""DialogoExportDrive — punto de entrada del camino Drive (DEC-2 de F0).
Se abre con la ee.Image ya construida (proactivo desde el combo "Salida" o
reactivo desde el aviso de límite de 32MB de F2): recoge destino/carpeta,
lanza el export en QThreadPool y muestra el progreso del polling.
"""
from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from app.gee.exportador import ConfigExport, DestinoExport, ProgresoExport
from app.ui.workers import ExportPollingWorker


class DialogoExportDrive(QDialog):
    def __init__(self, image, region, sugerencia_nombre: str = "export_gee",
                 scale: float = 30.0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Exportar a Google Drive / Cloud Storage")
        self._image = image
        self._region = region
        self._scale = scale
        self._worker: ExportPollingWorker | None = None
        self._terminado = False   # True desde el primer estado terminal (completado/fallo)

        # --- Form ---
        self._combo_destino = QComboBox()
        self._combo_destino.addItem("Google Drive", DestinoExport.DRIVE)
        self._combo_destino.addItem("Cloud Storage (requiere bucket + billing)",
                                    DestinoExport.CLOUD_STORAGE)
        self._input_nombre = QLineEdit(sugerencia_nombre)
        self._input_carpeta = QLineEdit("GEE_exports")  # folder plano en raíz Drive
        self._input_carpeta.setToolTip(
            "Carpeta en la raíz de TU Drive (la misma cuenta con la que te "
            "autenticaste en GEE). Si no existe, GEE la crea. Sin subcarpetas.\n"
            "Para Cloud Storage: nombre del bucket (requiere billing habilitado).")

        form = QFormLayout()
        form.addRow("Destino:", self._combo_destino)
        form.addRow("Nombre del archivo:", self._input_nombre)
        form.addRow("Carpeta / bucket:", self._input_carpeta)

        # --- Progreso ---
        self._label_estado = QLabel("Listo para exportar.")
        self._label_estado.setWordWrap(True)
        self._barra = QProgressBar()
        self._barra.setRange(0, 0)   # indeterminada
        self._barra.setVisible(False)

        # --- Botones ---
        self._btn_exportar = QPushButton("Exportar")
        self._btn_cancelar = QPushButton("Cancelar")
        self._btn_cerrar = QPushButton("Cerrar")
        self._btn_cancelar.setEnabled(False)
        self._btn_exportar.clicked.connect(self._on_exportar)
        self._btn_cancelar.clicked.connect(self._on_cancelar)
        self._btn_cerrar.clicked.connect(self.reject)
        fila_btns = QHBoxLayout()
        fila_btns.addWidget(self._btn_exportar)
        fila_btns.addWidget(self._btn_cancelar)
        fila_btns.addStretch()
        fila_btns.addWidget(self._btn_cerrar)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._label_estado)
        layout.addWidget(self._barra)
        layout.addLayout(fila_btns)

    # ---- lanzamiento ----
    def _on_exportar(self) -> None:
        destino: DestinoExport = self._combo_destino.currentData()
        nombre = self._input_nombre.text().strip() or "export_gee"
        carpeta = self._input_carpeta.text().strip() or None  # "" -> None: raíz de Drive / sin bucket
        cfg = ConfigExport(
            descripcion=nombre,
            prefijo_archivo=nombre,
            destino=destino,
            region=self._region,
            scale=self._scale,
            carpeta_drive=carpeta if destino is DestinoExport.DRIVE else None,
            bucket=carpeta if destino is DestinoExport.CLOUD_STORAGE else None,
        )

        self._terminado = False
        self._worker = ExportPollingWorker(self._image, cfg)
        self._worker.senales.iniciado.connect(self._on_iniciado)
        self._worker.senales.progreso.connect(self._on_progreso)
        self._worker.senales.completado.connect(self._on_completado)
        self._worker.senales.fallo.connect(self._on_fallo)
        self._worker.senales.finalizado.connect(self._on_finalizado)

        self._btn_exportar.setEnabled(False)
        self._btn_cancelar.setEnabled(True)
        self._barra.setVisible(True)
        self._label_estado.setText("Lanzando export…")
        QThreadPool.globalInstance().start(self._worker)

    def _on_cancelar(self) -> None:
        if self._worker is not None:
            self._label_estado.setText("Cancelando…")
            self._worker.solicitar_cancelacion()  # el worker llama task.cancel() (DEC-9)

    # ---- señales del worker ----
    def _on_iniciado(self, task_id: str) -> None:
        self._label_estado.setText(f"Export en curso (task {task_id})…")

    def _on_progreso(self, prog: ProgresoExport) -> None:
        self._label_estado.setText(f"Estado: {prog.estado.value} ({prog.crudo})")

    def _on_completado(self, prog: ProgresoExport) -> None:
        link = prog.uris_destino[0] if prog.uris_destino else "tu Drive"
        self._label_estado.setText(f"✅ Export completado. Archivo en: {link}")
        self._marcar_terminado()

    def _on_fallo(self, mensaje: str) -> None:
        self._label_estado.setText(f"❌ {mensaje}")
        self._marcar_terminado()

    def _marcar_terminado(self) -> None:
        """Deshabilita Cancelar apenas llega el primer estado terminal (B3 del
        audit de cierre), no recién en `_on_finalizado`: entre que el hilo del
        pool termina `run()` (QRunnable con `setAutoDelete(False)`, así que el
        objeto sigue vivo) y que `finalizado` se procesa, un clic en Cancelar
        alcanzaba a llamar `solicitar_cancelacion()` sobre un export que ya
        no está poleando — inofensivo hoy, pero es la misma ventana de carrera
        que motivó el fix; cerrarla acá es más barato que confiar en el orden
        de señales Qt."""
        self._terminado = True
        self._btn_cancelar.setEnabled(False)

    def _on_finalizado(self) -> None:
        """Se emite SIEMPRE (éxito, error o cancelación) — rehabilita la UI sin
        importar el desenlace (mismo contrato que SenalesWorker.finalizado)."""
        self._barra.setVisible(False)
        self._btn_cancelar.setEnabled(False)
        self._btn_exportar.setEnabled(True)

    # ---- cierre del diálogo (B4 del audit de cierre) ----
    def _cancelar_si_en_curso(self) -> None:
        """Cerrar/Escape/"Cerrar" con un export en curso dejaba el polling
        huérfano: el worker seguía emitiendo señales hacia un QDialog cerrado
        (mismo riesgo de `RuntimeError` de B3) y sin forma de cancelar después.
        Sin diálogo de confirmación — app personal, cancelar es seguro
        (`task.cancel()` corre server-side, DEC-9 de F0)."""
        if self._worker is not None and not self._terminado:
            self._worker.solicitar_cancelacion()

    def closeEvent(self, event) -> None:
        self._cancelar_si_en_curso()
        super().closeEvent(event)

    def reject(self) -> None:
        # Escape llama reject() directo, sin pasar por closeEvent — mismo fix acá.
        self._cancelar_si_en_curso()
        super().reject()
