"""Selector de AOI: shapefile/zip, GeoJSON, bbox o dibujado en el mapa (F3b). Produce un
descriptor para FuenteAOI (F1)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QStackedWidget,
    QLineEdit, QPushButton, QDoubleSpinBox, QFileDialog, QLabel,
)
from PySide6.QtCore import Signal


class SelectorAOI(QWidget):
    """Arma un descriptor {'tipo': ..., ...}. NO resuelve a ee.Geometry (eso es del ejecutor)."""
    cambiado = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._geom_dibujada: dict | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tipo = QComboBox()
        self.tipo.addItems([
            "Shapefile (.shp/.zip)", "GeoJSON (.geojson)", "Bounding box",
            "Dibujado en el mapa",
        ])
        layout.addWidget(self.tipo)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(self._pagina_archivo("Shapefile o .zip", "Shapefiles (*.shp *.zip)"))
        self.stack.addWidget(self._pagina_archivo("Archivo GeoJSON", "GeoJSON (*.geojson *.json)"))
        self.stack.addWidget(self._pagina_bbox())
        self.stack.addWidget(self._pagina_dibujado())
        self.tipo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.tipo.currentIndexChanged.connect(self.cambiado)

    def _pagina_archivo(self, titulo: str, filtro: str) -> QWidget:
        w = QWidget()
        fila = QHBoxLayout(w)
        fila.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        edit.setPlaceholderText(titulo)
        edit.setReadOnly(True)
        edit.textChanged.connect(self.cambiado)
        boton = QPushButton("Elegir…")

        def elegir():
            ruta, _ = QFileDialog.getOpenFileName(self, titulo, "", filtro)
            if ruta:
                edit.setText(ruta)

        boton.clicked.connect(elegir)
        fila.addWidget(edit)
        fila.addWidget(boton)
        w._edit = edit  # type: ignore[attr-defined]
        return w

    def _pagina_bbox(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        self._bbox: dict[str, QDoubleSpinBox] = {}
        for clave, etiqueta, rango in [
            ("oeste", "Oeste (lon min)", (-180, 180)),
            ("sur", "Sur (lat min)", (-90, 90)),
            ("este", "Este (lon max)", (-180, 180)),
            ("norte", "Norte (lat max)", (-90, 90)),
        ]:
            spin = QDoubleSpinBox()
            spin.setDecimals(6)
            spin.setRange(*rango)
            spin.valueChanged.connect(self.cambiado)
            form.addRow(etiqueta, spin)
            self._bbox[clave] = spin
        return w

    def _pagina_dibujado(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self._lbl_dibujado = QLabel("Ningún polígono dibujado todavía — usá el mapa.")
        self._lbl_dibujado.setWordWrap(True)
        v.addWidget(self._lbl_dibujado)
        return w

    def descriptor(self) -> dict | None:
        """Descriptor para FuenteAOI, o None si está incompleto."""
        idx = self.tipo.currentIndex()
        if idx == 0:
            ruta = self.stack.widget(0)._edit.text()  # type: ignore[attr-defined]
            return {"tipo": "shapefile", "ruta": ruta} if ruta else None
        if idx == 1:
            ruta = self.stack.widget(1)._edit.text()  # type: ignore[attr-defined]
            return {"tipo": "geojson", "ruta": ruta} if ruta else None
        if idx == 2:
            b = {k: s.value() for k, s in self._bbox.items()}
            if b["oeste"] == b["este"] or b["sur"] == b["norte"]:
                return None  # bbox degenerado
            return {"tipo": "bbox", **b}
        # idx == 3: dibujado en el mapa — reusa el contrato 'geojson-dict' de FuenteAOI
        # (el bridge ya entrega .geometry, no una Feature/FeatureCollection completa).
        if self._geom_dibujada is None:
            return None
        return {"tipo": "geojson-dict", "geojson": self._geom_dibujada}

    def set_geometria_dibujada(self, geometria: dict | None) -> None:
        """Llamado por VentanaPrincipal cuando WidgetMapa.aoi_dibujada/aoi_borrada emite.
        Cambia el combo a 'Dibujado en el mapa' automáticamente al recibir una geometría."""
        self._geom_dibujada = geometria
        if geometria is not None:
            tipo = geometria.get("type", "?")
            self._lbl_dibujado.setText(f"AOI dibujada en el mapa (tipo: {tipo}).")
            self.tipo.setCurrentIndex(3)  # dispara stack.setCurrentIndex + cambiado
        else:
            self._lbl_dibujado.setText("Ningún polígono dibujado todavía — usá el mapa.")
            if self.tipo.currentIndex() == 3:
                self.cambiado.emit()
