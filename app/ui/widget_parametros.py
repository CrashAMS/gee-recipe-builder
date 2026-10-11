"""Inputs numéricos dinámicos para los parámetros ajustables del índice (EVI: g, C1, C2, L)."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QFormLayout, QDoubleSpinBox, QLabel
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
        """`parametros_ajustables`: iterable con .nombre / .default / .descripcion (modelo de F1).
        Caso de un solo bloque, sin título."""
        self.cargar_grupos([("", parametros_ajustables)])

    def cargar_grupos(self, grupos) -> None:
        """`grupos`: [(short_name, parametros_ajustables), ...]. Un bloque con título por índice
        (si hay más de uno). Un nombre compartido tiene UN solo spinbox, en el bloque del primer
        índice que lo usa y con el default de ese índice; en los siguientes va una nota sin spinbox.
        `valores()` sigue siendo un dict plano. Una sola emisión de `cambiado` por carga."""
        self._limpiar()
        grupos = list(grupos)
        con_titulo = len(grupos) > 1
        dueno: dict[str, str] = {}   # nombre de parámetro -> short_name del índice donde vive el spinbox
        for short_name, params in grupos:
            filas = [self._desempacar(p) for p in params]
            if con_titulo:
                titulo = QLabel(f"<b>{short_name}</b>")
                self._form.addRow(titulo)
            for nombre, default, desc in filas:
                if nombre in dueno:
                    self._form.addRow(QLabel(f"{nombre} (compartido con {dueno[nombre]})"))
                    continue
                spin = QDoubleSpinBox()
                spin.setDecimals(4)
                spin.setRange(-1_000_000.0, 1_000_000.0)
                spin.setValue(float(default))
                if desc:
                    spin.setToolTip(desc)
                spin.valueChanged.connect(self.cambiado)
                self._form.addRow(nombre, spin)
                self._spins[nombre] = spin
                dueno[nombre] = short_name
        self.cambiado.emit()

    def valores(self) -> dict[str, float]:
        return {n: s.value() for n, s in self._spins.items()}

    def set_valores(self, valores: dict) -> None:
        """Setea solo los nombres presentes en el panel; ignora el resto."""
        for nombre, valor in valores.items():
            spin = self._spins.get(nombre)
            if spin is not None:
                spin.setValue(float(valor))

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
