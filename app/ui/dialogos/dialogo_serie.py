"""DialogoSerie — vista de la serie temporal (F8), no modal y propiedad de la ventana.

Muestra el progreso por período, permite cancelar entre períodos y grafica la media
de cada índice (una `QLineSeries` por índice; X = período, etiquetado con
`periodo_inicio`; los puntos sin dato se omiten). Sin QtCharts (p. ej. un `.exe`
empaquetado sin el módulo) cae a una `QTableWidget` con las mismas columnas del CSV.
"Exportar CSV" se habilita al terminar, cancelar o fallar, con las filas recibidas.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.dominio.serie_csv import FilaSerie, encabezado_serie, escribir_csv, filas_a_csv

try:  # QtCharts viene en PySide6-Addons; un build sin el módulo usa la tabla
    from PySide6.QtCharts import (
        QBarCategoryAxis, QChart, QChartView, QLineSeries, QValueAxis)
    _HAY_QTCHARTS = True
except ImportError:  # pragma: no cover — depende del entorno
    _HAY_QTCHARTS = False


class DialogoSerie(QDialog):
    cancelacion_pedida = Signal()   # la ventana la conecta a WorkerSerieTemporal.solicitar_cancelacion

    def __init__(self, indices: list[str], total: int, sugerencia_csv: str = "serie.csv",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Serie temporal")
        self.resize(760, 520)
        self.indices = list(indices)
        self.total = total
        self.filas: list[FilaSerie] = []
        self._sugerencia_csv = sugerencia_csv
        self._en_curso = True

        self.lbl_estado = QLabel(f"Calculando {total} períodos…")
        self.lbl_estado.setWordWrap(True)
        self.barra = QProgressBar()
        self.barra.setRange(0, max(total, 1))
        self.barra.setValue(0)

        self.usa_grafico = _HAY_QTCHARTS
        self.series: dict[str, object] = {}
        if self.usa_grafico:
            self._armar_grafico()
            vista = self.vista_grafico
        else:
            self.tabla = QTableWidget(0, len(encabezado_serie(self.indices)))
            self.tabla.setHorizontalHeaderLabels(encabezado_serie(self.indices))
            self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            vista = self.tabla
            self.lbl_estado.setText(self.lbl_estado.text()
                                    + " (gráfico no disponible: falta QtCharts, se muestra la tabla)")

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_exportar = QPushButton("Exportar CSV…")
        self.btn_exportar.setEnabled(False)
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cancelar.clicked.connect(self._on_cancelar)
        self.btn_exportar.clicked.connect(lambda: self.exportar_csv())
        self.btn_cerrar.clicked.connect(self.close)
        botones = QHBoxLayout()
        botones.addWidget(self.btn_cancelar)
        botones.addStretch()
        botones.addWidget(self.btn_exportar)
        botones.addWidget(self.btn_cerrar)

        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl_estado)
        lay.addWidget(self.barra)
        lay.addWidget(vista, 1)
        lay.addLayout(botones)

    # ---- vista ----
    def _armar_grafico(self) -> None:
        self.chart = QChart()
        self.chart.setTitle("Media sobre el AOI por período")
        self.eje_x = QBarCategoryAxis()       # categorías = periodo_inicio (robusto en offscreen)
        self.eje_x.setTitleText("Inicio del período")
        self.eje_y = QValueAxis()
        self.eje_y.setTitleText("Media")
        self.chart.addAxis(self.eje_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.eje_y, Qt.AlignmentFlag.AlignLeft)
        for ind in self.indices:
            s = QLineSeries()
            s.setName(ind)
            s.setPointsVisible(True)
            self.chart.addSeries(s)
            s.attachAxis(self.eje_x)
            s.attachAxis(self.eje_y)
            self.series[ind] = s
        self.vista_grafico = QChartView(self.chart)
        self._y_min: float | None = None
        self._y_max: float | None = None

    def _agregar_a_grafico(self, i: int, fila: FilaSerie) -> None:
        self.eje_x.append([fila.periodo_inicio])
        for ind, serie in self.series.items():
            v = fila.medias.get(ind)
            if v is None:
                continue                      # sin dato: el punto se omite
            serie.append(float(i), float(v))
            self._y_min = v if self._y_min is None else min(self._y_min, v)
            self._y_max = v if self._y_max is None else max(self._y_max, v)
        if self._y_min is not None:
            margen = max((self._y_max - self._y_min) * 0.1, 0.01)
            self.eje_y.setRange(self._y_min - margen, self._y_max + margen)

    def _agregar_a_tabla(self, fila: FilaSerie) -> None:
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        valores = [fila.periodo_inicio, fila.periodo_fin,
                   *(fila.medias.get(i) for i in self.indices), fila.n_imagenes]
        for c, v in enumerate(valores):
            self.tabla.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))

    # ---- slots del worker ----
    def on_progreso(self, i: int, total: int, fila: FilaSerie) -> None:
        self.filas.append(fila)
        self.barra.setValue(i)
        self.lbl_estado.setText(f"Período {i} de {total}: {fila.periodo_inicio} → {fila.periodo_fin} "
                                f"({fila.n_imagenes} imágenes)")
        if self.usa_grafico:
            self._agregar_a_grafico(i - 1, fila)
        else:
            self._agregar_a_tabla(fila)

    def on_terminado(self, filas) -> None:
        self.lbl_estado.setText(f"Serie completa: {len(filas)} períodos.")

    def on_cancelado(self, filas) -> None:
        self.lbl_estado.setText(f"Cancelada: {len(filas)} de {self.total} períodos calculados.")

    def on_error(self, tipo: str, mensaje: str) -> None:
        self.lbl_estado.setText(f"Error ({tipo}) tras {len(self.filas)} períodos: {mensaje}")

    def on_finalizado(self) -> None:
        self._en_curso = False
        self.btn_cancelar.setEnabled(False)
        self.btn_exportar.setEnabled(bool(self.filas))

    def en_curso(self) -> bool:
        return self._en_curso

    # ---- acciones ----
    def _on_cancelar(self) -> None:
        if self._en_curso:
            self.btn_cancelar.setEnabled(False)
            self.lbl_estado.setText("Cancelando al terminar el período en curso…")
            self.cancelacion_pedida.emit()

    def exportar_csv(self, ruta: str | None = None) -> str | None:
        """Escribe las filas recibidas con `escribir_csv`. Sin `ruta` pregunta dónde."""
        if ruta is None:
            ruta, _ = QFileDialog.getSaveFileName(self, "Exportar serie a CSV", self._sugerencia_csv,
                                                  "CSV (*.csv)")
            if not ruta:
                return None
        try:
            escribir_csv(ruta, filas_a_csv(self.filas, self.indices))
        except OSError as e:
            QMessageBox.critical(self, "No se pudo escribir el CSV", str(e))
            return None
        self.lbl_estado.setText(f"CSV exportado: {ruta}")
        return ruta

    def closeEvent(self, event) -> None:
        # Cerrar con la serie en curso la cancela (no hay dónde mostrar lo que siga llegando).
        if self._en_curso:
            self.cancelacion_pedida.emit()
        super().closeEvent(event)
