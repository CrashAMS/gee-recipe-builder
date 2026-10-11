"""PanelExports (F5) — dock no modal que lista los exports del registro.

UI delgada sobre `GestorExports`: relee el registro en cada `cambio`. Cancelar
server-side es SOLO el botón de acá (con confirmación), habilitado en no terminales.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDockWidget, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.gee.registro_exports import es_terminal

_COLUMNAS = ("Nombre", "Destino", "Fecha", "Estado", "Link")
_DESTINOS = {"drive": "Drive", "cloud_storage": "Cloud Storage",
             "drive-tabla": "Drive (tabla CSV)"}


class PanelExports(QDockWidget):
    def __init__(self, gestor, parent: QWidget | None = None) -> None:
        super().__init__("Exports", parent)
        self.setObjectName("panel_exports")
        self._gestor = gestor
        self._ids: list[str] = []
        self._entradas: dict[str, dict] = {}

        self.tabla = QTableWidget(0, len(_COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(_COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.itemSelectionChanged.connect(self._actualizar_boton)

        self.btn_cancelar = QPushButton("Cancelar export")
        self.btn_cancelar.setToolTip("Cancela el task en GEE (server-side). Cerrar la app no cancela.")
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.clicked.connect(self._on_cancelar)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(self.btn_cancelar)

        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.addWidget(self.tabla)
        lay.addLayout(fila)
        self.setWidget(cont)

        gestor.cambio.connect(self.refrescar)
        self.refrescar()

    def seleccionado(self) -> str | None:
        filas = self.tabla.selectionModel().selectedRows()
        return self._ids[filas[0].row()] if filas else None

    def refrescar(self, *_args) -> None:
        previo = self.seleccionado()
        entradas = self._gestor.registro.listar()
        self._ids = [e["task_id"] for e in entradas]
        self._entradas = {e["task_id"]: e for e in entradas}
        self.tabla.blockSignals(True)
        self.tabla.clearContents()
        self.tabla.setRowCount(len(entradas))
        for fila, e in enumerate(entradas):
            estado = e.get("estado") or "?"
            if not es_terminal(e) and not self._gestor.siguiendo(e["task_id"]):
                estado += " (sin seguimiento)"
            aviso = self._gestor.aviso(e["task_id"])
            if aviso:
                estado += f" — {aviso}"
            destino = _DESTINOS.get(e.get("destino"), e.get("destino") or "")
            if e.get("carpeta"):
                destino += f": {e['carpeta']}"
            celdas = (e.get("nombre") or "", destino,
                      (e.get("fecha_lanzado") or "").replace("T", " ")[:16], estado)
            for col, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                item.setToolTip(e.get("mensaje_error") or e["task_id"])
                self.tabla.setItem(fila, col, item)
            uris = e.get("uris") or []
            if uris:
                link = QLabel(f'<a href="{html.escape(uris[0], quote=True)}">abrir</a>')
                link.setOpenExternalLinks(True)
                link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                self.tabla.setCellWidget(fila, 4, link)
            else:
                self.tabla.setItem(fila, 4, QTableWidgetItem(""))
        if previo in self._ids:
            self.tabla.selectRow(self._ids.index(previo))
        self.tabla.blockSignals(False)
        self._actualizar_boton()

    def _actualizar_boton(self) -> None:
        tid = self.seleccionado()
        e = self._entradas.get(tid) if tid else None
        self.btn_cancelar.setEnabled(e is not None and not es_terminal(e))

    def _on_cancelar(self) -> None:
        tid = self.seleccionado()
        e = self._entradas.get(tid) if tid else None
        if e is None or es_terminal(e):
            return
        r = QMessageBox.question(
            self, "Cancelar export",
            f"¿Cancelar el export '{e.get('nombre')}' en GEE?\nEl task se detiene server-side.")
        if r == QMessageBox.StandardButton.Yes:
            self._gestor.cancelar(tid)
