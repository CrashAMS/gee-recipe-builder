"""DialogoExportDrive — punto de entrada del camino Drive (DEC-2 de F0).
Se abre (no modal) con la ee.Image ya construida: recoge destino/carpeta y delega
el lanzamiento en `GestorExports` (F5). El seguimiento vive en el panel de exports,
así que el diálogo se puede cerrar al instante: cerrarlo NO afecta al export.
"""
from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from app.gee.exportador import ConfigExport, DestinoExport


class DialogoExportDrive(QDialog):
    def __init__(self, image, region, gestor, sugerencia_nombre: str = "export_gee",
                 scale: float = 30.0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Exportar a Google Drive / Cloud Storage")
        self._image = image
        self._region = region
        self._scale = scale
        self._gestor = gestor
        self._clave: str | None = None   # clave del lanzamiento propio en el gestor

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

        self._label_estado = QLabel("Listo para exportar.")
        self._label_estado.setWordWrap(True)

        # --- Botones (sin "Cancelar": cancelar server-side es solo del panel) ---
        self._btn_exportar = QPushButton("Exportar")
        self._btn_cerrar = QPushButton("Cerrar")
        self._btn_exportar.clicked.connect(self._on_exportar)
        self._btn_cerrar.clicked.connect(self.close)
        fila_btns = QHBoxLayout()
        fila_btns.addWidget(self._btn_exportar)
        fila_btns.addStretch()
        fila_btns.addWidget(self._btn_cerrar)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._label_estado)
        layout.addLayout(fila_btns)

        gestor.lanzado.connect(self._on_lanzado)
        gestor.fallo_lanzamiento.connect(self._on_fallo)

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
        self._btn_exportar.setEnabled(False)
        self._label_estado.setText("Lanzando export… (podés cerrar este diálogo)")
        self._clave = uuid.uuid4().hex   # fijada antes: el gestor puede emitir enseguida
        self._gestor.lanzar(self._image, cfg, clave=self._clave)

    def _on_lanzado(self, clave: str, task_id: str) -> None:
        if clave != self._clave:
            return
        self._label_estado.setText(
            f"Lanzado (task {task_id}). Seguilo en el panel de exports; ya podés cerrar.")

    def _on_fallo(self, clave: str, mensaje: str) -> None:
        if clave != self._clave:
            return
        self._label_estado.setText(f"❌ {mensaje}")
        self._btn_exportar.setEnabled(True)
