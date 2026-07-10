"""Visor del script generado con toggle JS/Python, monoespaciado y solo-lectura."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QRadioButton, QPushButton,
)
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtCore import Signal


class VisorScript(QWidget):
    dialecto_cambiado = Signal()  # emitida al togglear JS/Python

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        fila = QHBoxLayout()
        self.rb_js = QRadioButton("JavaScript")
        self.rb_py = QRadioButton("Python")
        self.rb_js.setChecked(True)
        self.rb_js.toggled.connect(lambda _=False: self.dialecto_cambiado.emit())
        fila.addWidget(self.rb_js)
        fila.addWidget(self.rb_py)
        fila.addStretch()
        self.btn_copiar = QPushButton("Copiar")
        self.btn_copiar.clicked.connect(self._copiar)
        fila.addWidget(self.btn_copiar)
        layout.addLayout(fila)
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setFont(QFont("Consolas", 10))
        self.texto.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.texto)

    def dialecto(self) -> str:
        return "js" if self.rb_js.isChecked() else "python"

    def mostrar(self, script: str) -> None:
        self.texto.setPlainText(script)

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto.toPlainText())
