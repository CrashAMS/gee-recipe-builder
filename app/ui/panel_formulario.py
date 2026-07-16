"""Formulario index-first: índice → sensor → zona → fechas → máscara → composición → salida."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QDateEdit, QLabel, QGroupBox,
    QSpinBox,
)
from PySide6.QtCore import Signal, QDate

from app.dominio import catalogo
from app.dominio.aoi import FuenteAOI
from app.dominio.errores import FuenteAOIError
from app.dominio.receta import Receta
from app.ui.widget_parametros import PanelParametros
from app.ui.widget_aoi import SelectorAOI

COMPOSICIONES = [
    ("Mediana", "median"), ("Media", "mean"), ("Mínimo", "min"),
    ("Máximo", "max"), ("Mosaico (más reciente)", "mosaic"),
]
SALIDAS = [  # (etiqueta, valor, habilitada) — valores = Salida.*.value de F1 ("descarga", no "disco")
    ("Descarga a disco", "descarga", True),
    ("Drive / Cloud (F4)", "drive", True),
    ("Preview en mapa (F3b)", "preview", True),
]


class PanelFormulario(QWidget):
    cambiado = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        raiz = QVBoxLayout(self)
        self._error_aoi: str | None = None

        # --- Índice (primera decisión, index-first) ---
        caja_indice = QGroupBox("1 · Índice")
        f_idx = QFormLayout(caja_indice)
        self.combo_indice = QComboBox()
        # Sin esto, QComboBox mide TODOS los ítems para dimensionarse (algunos nombres
        # del catálogo ASI superan los 90 caracteres) y fuerza scroll horizontal en
        # el panel entero. Se acota el ancho; el texto elegido se elide con "…" y el
        # nombre completo queda visible en lbl_desc debajo del combo.
        self.combo_indice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_indice.setMinimumContentsLength(28)
        self._indices = catalogo.listar_indices()
        for ind in self._indices:
            self.combo_indice.addItem(f"{ind.short_name} — {ind.long_name}", ind)
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.panel_params = PanelParametros()
        f_idx.addRow("Índice", self.combo_indice)
        f_idx.addRow(self.lbl_desc)
        f_idx.addRow("Parámetros", self.panel_params)
        raiz.addWidget(caja_indice)

        # --- Sensor (filtrado por el índice) ---
        caja_sensor = QGroupBox("2 · Sensor")
        f_sen = QFormLayout(caja_sensor)
        self.combo_sensor = QComboBox()
        f_sen.addRow("Sensor", self.combo_sensor)
        raiz.addWidget(caja_sensor)

        # --- Zona (AOI) ---
        caja_aoi = QGroupBox("3 · Zona (AOI)")
        v_aoi = QVBoxLayout(caja_aoi)
        self.selector_aoi = SelectorAOI()
        v_aoi.addWidget(self.selector_aoi)
        raiz.addWidget(caja_aoi)

        # --- Fechas + máscara + composición + salida ---
        caja_resto = QGroupBox("4 · Parámetros de la receta")
        f_r = QFormLayout(caja_resto)
        self.fecha_inicio = QDateEdit(QDate.currentDate().addYears(-1))
        self.fecha_fin = QDateEdit(QDate.currentDate())
        for de in (self.fecha_inicio, self.fecha_fin):
            de.setCalendarPopup(True)
            de.setDisplayFormat("yyyy-MM-dd")
        self.chk_mascara = QCheckBox("Aplicar máscara de nubes")
        self.chk_mascara.setChecked(True)
        self.combo_comp = QComboBox()
        for etiqueta, valor in COMPOSICIONES:
            self.combo_comp.addItem(etiqueta, valor)
        self.combo_salida = QComboBox()
        for etiqueta, valor, habilitada in SALIDAS:
            self.combo_salida.addItem(etiqueta, valor)
            if not habilitada:
                idx = self.combo_salida.count() - 1
                self.combo_salida.model().item(idx).setEnabled(False)
                self.combo_salida.setItemData(idx, "Disponible en una fase futura", 3)  # Qt.ToolTipRole
        self.spin_escala = QSpinBox()
        self.spin_escala.setRange(10, 1000)
        self.spin_escala.setValue(10)
        self.spin_escala.setSuffix(" m")
        f_r.addRow("Desde", self.fecha_inicio)
        f_r.addRow("Hasta", self.fecha_fin)
        f_r.addRow(self.chk_mascara)
        f_r.addRow("Composición", self.combo_comp)
        f_r.addRow("Escala", self.spin_escala)
        f_r.addRow("Salida", self.combo_salida)
        raiz.addWidget(caja_resto)
        raiz.addStretch()

        # --- Wiring ---
        self.combo_indice.currentIndexChanged.connect(self._on_indice)
        self.combo_sensor.currentIndexChanged.connect(self._on_sensor)
        for sig in (
            self.panel_params.cambiado, self.selector_aoi.cambiado,
            self.fecha_inicio.dateChanged, self.fecha_fin.dateChanged,
            self.chk_mascara.toggled, self.combo_comp.currentIndexChanged,
            self.spin_escala.valueChanged, self.combo_salida.currentIndexChanged,
        ):
            sig.connect(self.cambiado)

        self._on_indice()  # inicializa sensor + params del primer índice

    def _indice_actual(self):
        return self.combo_indice.currentData()

    def _sensor_actual(self):
        return self.combo_sensor.currentData()

    def _on_indice(self) -> None:
        ind = self._indice_actual()
        if ind is None:
            return
        # `Indice` (F1) no expone `.descripcion` — mostramos long_name + fórmula ASI.
        self.lbl_desc.setText(f"{ind.long_name}  ·  fórmula: {ind.formula}")
        self.panel_params.cargar(ind.parametros_ajustables)
        self.combo_sensor.blockSignals(True)
        self.combo_sensor.clear()
        for sen in catalogo.sensores_para(ind):
            self.combo_sensor.addItem(sen.display_name, sen)
        self.combo_sensor.blockSignals(False)
        self._on_sensor()
        self.cambiado.emit()

    def _on_sensor(self) -> None:
        sen = self._sensor_actual()
        if sen is None:
            return
        soporta = catalogo.soporta_mascara(sen.collection_id)  # [HALLAZGO-2.4] — recibe el ID string
        self.chk_mascara.setEnabled(soporta)
        if not soporta:
            self.chk_mascara.setChecked(False)
            self.chk_mascara.setToolTip(
                f"El sensor {sen.display_name} no tiene máscara de nubes automática."
            )
        else:
            self.chk_mascara.setToolTip("")
        self.cambiado.emit()

    def receta_actual(self) -> Receta | None:
        """Arma la Receta desde el estado del form, o None si falta algo obligatorio
        o si el AOI no se pudo resolver (ver `ultimo_error_aoi`)."""
        self._error_aoi = None
        ind = self._indice_actual()
        sen = self._sensor_actual()
        descriptor = self.selector_aoi.descriptor()
        if ind is None or sen is None or descriptor is None:
            return None
        try:
            geometria = FuenteAOI.desde_descriptor(descriptor)
        except FuenteAOIError as e:
            self._error_aoi = str(e)
            return None
        return Receta(
            indice=ind.short_name,                                # string, no el objeto Indice
            sensor=sen.collection_id,                             # string, no el objeto Sensor
            geometria=geometria,                                   # GeoJSON dict (F1) — campo `geometria`, no `aoi`
            fecha_inicio=self.fecha_inicio.date().toString("yyyy-MM-dd"),
            fecha_fin=self.fecha_fin.date().toString("yyyy-MM-dd"),
            mascara_nubes=self.chk_mascara.isChecked(),
            composicion=self.combo_comp.currentData(),            # string .value — __post_init__ coacciona a enum
            salida=self.combo_salida.currentData(),               # "descarga" — matchea Salida.DESCARGA
            escala=self.spin_escala.value(),
            parametros=self.panel_params.valores(),
        )

    def ultimo_error_aoi(self) -> str | None:
        """Mensaje de `FuenteAOIError` de la última llamada a `receta_actual`, si la hubo."""
        return self._error_aoi
