"""Inputs numéricos dinámicos para los parámetros ajustables del índice (EVI: g, C1, C2, L)."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QFormLayout, QDoubleSpinBox
from PySide6.QtCore import Signal


class PanelParametros(QWidget):
    """Reconstruye un form de spinboxes cada vez que cambia el índice."""
    cambiado = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._spins: dict[str, QDoubleSpinBox] = {}

    def cargar(self, parametros_ajustables) -> None:
        """`parametros_ajustables`: iterable con .nombre / .default / .descripcion (modelo de F1)."""
        self._limpiar()
        for p in parametros_ajustables:
            nombre, default, desc = self._desempacar(p)
            spin = QDoubleSpinBox()
            spin.setDecimals(4)
            spin.setRange(-1_000_000.0, 1_000_000.0)
            spin.setValue(float(default))
            if desc:
                spin.setToolTip(desc)
            spin.valueChanged.connect(self.cambiado)
            self._form.addRow(nombre, spin)
            self._spins[nombre] = spin
        self.cambiado.emit()

    def valores(self) -> dict[str, float]:
        return {n: s.value() for n, s in self._spins.items()}

    def _limpiar(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._spins.clear()

    @staticmethod
    def _desempacar(p):
        # Adaptar al modelo real de F1: objeto con atributos, dict, o tupla.
        if hasattr(p, "nombre"):
            return p.nombre, getattr(p, "default", 0.0), getattr(p, "descripcion", "")
        if isinstance(p, dict):
            return p["nombre"], p.get("default", 0.0), p.get("descripcion", "")
        return p[0], p[1], (p[2] if len(p) > 2 else "")
