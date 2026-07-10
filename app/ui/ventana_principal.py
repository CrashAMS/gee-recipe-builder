"""Ventana principal: [ formulario | visor de script | mapa interactivo (F3b) ]."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QScrollArea, QSplitter,
    QPushButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThreadPool, QTimer

from app.dominio.compilador import dialecto_js, dialecto_python
from app.gee import auth, config, ejecutor
from app.mapa.widget_mapa import WidgetMapa, refrescar_preview
from app.ui.panel_formulario import PanelFormulario
from app.ui.visor_script import VisorScript
from app.ui.workers import WorkerDescarga, solicitud_desde_receta

# Debounce del auto-refresh de preview al cambiar la receta (decisión #6 F3b):
# regenerar mapid en cada cambio, pero sin saturar GEE en cada tecla/spin.
_DEBOUNCE_PREVIEW_MS = 800


class VentanaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GEE Recipe Builder")
        self.resize(1200, 800)
        self.pool = QThreadPool.globalInstance()

        # --- Zona formulario (con scroll) ---
        self.form = PanelFormulario()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)

        # --- Zona visor + botón ejecutar ---
        col_visor = QWidget()
        v = QVBoxLayout(col_visor)
        self.visor = VisorScript()
        v.addWidget(self.visor)
        self.btn_ejecutar = QPushButton("Ejecutalo por mí (descarga a disco)")
        self.btn_ejecutar.clicked.connect(self._ejecutar)
        v.addWidget(self.btn_ejecutar)

        # --- Mapa interactivo (F3b) — reemplaza el placeholder de F3a ---
        self._mapa = WidgetMapa()
        self.btn_preview = QPushButton("Refrescar preview")
        self.btn_preview.clicked.connect(lambda: self._lanzar_preview(interactivo=True))
        # Feedback del preview: sin esto, éxito/error del worker solo van a stdout y el
        # usuario no tiene forma de saber si el tile se cargó o falló.
        self.lbl_preview = QLabel("")
        self.lbl_preview.setWordWrap(True)
        lay_mapa = QVBoxLayout()
        lay_mapa.setContentsMargins(0, 0, 0, 0)
        lay_mapa.addWidget(self._mapa)
        lay_mapa.addWidget(self.btn_preview)
        lay_mapa.addWidget(self.lbl_preview)
        panel_mapa = QWidget()
        panel_mapa.setLayout(lay_mapa)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(col_visor)
        splitter.addWidget(panel_mapa)
        splitter.setSizes([460, 620, 180])  # el mapa arranca angosto en F3a
        # Sin stretch factors, QSplitter reparte el espacio extra en la misma
        # proporción que los tamaños iniciales — al maximizar, el slot de mapa
        # (sin uso en F3a) se infla igual que el form/visor. Con stretch 0 se
        # queda angosto y el espacio extra va a formulario/visor.
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        self.setCentralWidget(splitter)

        # --- Wiring de actualización en vivo ---
        self.form.cambiado.connect(self._actualizar_script)
        self.visor.dialecto_cambiado.connect(self._actualizar_script)
        self._actualizar_script()

        # --- Wiring AOI dibujada en el mapa → SelectorAOI (F3b) ---
        self._mapa.aoi_dibujada.connect(self.form.selector_aoi.set_geometria_dibujada)
        self._mapa.aoi_borrada.connect(lambda: self.form.selector_aoi.set_geometria_dibujada(None))

        # --- Wiring preview (F3b): auto-refresh debounced en cada cambio de receta
        # (decisión #6, evita regenerar el mapid en cada tecla) + botón manual ---
        self._preview_thread = None  # guardar ref viva, si no el GC mata el QThread
        self._preview_en_curso = False  # evita pisar self._preview_thread con un QThread
        # todavía corriendo (auto-refresh + botón manual solapados) — Qt aborta el
        # proceso si se destruye un QThread vivo ("QThread: Destroyed while thread
        # is still running", Qt6Core.dll fatal).
        self._debounce_preview = QTimer(self)
        self._debounce_preview.setSingleShot(True)
        self._debounce_preview.setInterval(_DEBOUNCE_PREVIEW_MS)
        self._debounce_preview.timeout.connect(lambda: self._lanzar_preview(interactivo=False))
        self.form.cambiado.connect(self._debounce_preview.start)

        print("VentanaPrincipal lista — form poblado, visor inicializado, mapa embebido")

    def _actualizar_script(self) -> None:
        receta = self.form.receta_actual()
        if receta is None:
            error_aoi = self.form.ultimo_error_aoi()
            if error_aoi:
                self.visor.mostrar(f"// AOI inválida: {error_aoi}")
            else:
                self.visor.mostrar("// Completá el formulario (índice, sensor y zona) para ver el script.")
            return
        try:
            if self.visor.dialecto() == "js":
                script = dialecto_js.compilar(receta)
            else:
                script = dialecto_python.compilar(receta)
        except Exception as e:  # noqa: BLE001 — un error de compilación se muestra, no crashea la UI
            script = f"// Error al compilar la receta: {e}"
        self.visor.mostrar(script)

    def _ejecutar(self) -> None:
        receta = self.form.receta_actual()
        if receta is None:
            QMessageBox.warning(self, "Receta incompleta",
                                "Completá índice, sensor y zona antes de ejecutar.")
            return
        # Onboarding del Cloud project (decisión #11, PRD user story 10):
        # sin project configurado, asegurar_sesion levantaría ErrorAuthGEE en el worker.
        if not config.hay_project_configurado():
            pid, ok = QInputDialog.getText(
                self, "Google Cloud project",
                "GEE requiere un Cloud project (gratis para uso no comercial).\n"
                "Registrate en code.earthengine.google.com/register y pegá acá el project ID:")
            if not ok or not pid.strip():
                return
            config.guardar_project(pid.strip())
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar GeoTIFF", "salida.tif",
                                                 "GeoTIFF (*.tif)")
        if not destino:
            return
        self.btn_ejecutar.setEnabled(False)
        self.btn_ejecutar.setText("Descargando…")
        worker = WorkerDescarga(receta, Path(destino))
        worker.senales.terminado.connect(self._on_ok)
        worker.senales.error.connect(self._on_error)
        worker.senales.finalizado.connect(self._on_fin)
        self.pool.start(worker)

    def _on_ok(self, ruta) -> None:
        QMessageBox.information(self, "Listo", f"Imagen descargada en:\n{ruta}")

    def _on_error(self, tipo: str, mensaje: str) -> None:
        QMessageBox.critical(self, f"Error ({tipo})", mensaje)

    def _on_fin(self) -> None:
        self.btn_ejecutar.setEnabled(True)
        self.btn_ejecutar.setText("Ejecutalo por mí (descarga a disco)")

    def _lanzar_preview(self, interactivo: bool) -> None:
        """Construye la ee.Image de la receta actual y refresca el tile de preview en el mapa.
        `interactivo=True` (botón manual) pide el Cloud project si falta; el auto-refresh
        debounced (`interactivo=False`) se salta en silencio si todavía no hay project
        configurado, para no interrumpir al usuario mientras completa el formulario.

        Si ya hay un refresh en vuelo, se ignora el pedido nuevo — lanzar uno superpuesto
        pisaría `self._preview_thread` con el QThread anterior todavía corriendo, y Qt
        aborta el proceso al destruirlo vivo. El próximo cambio de receta (debounce) o
        click manual dispara el refresh pendiente una vez que el actual termina.

        `auth.asegurar_sesion` + el adapter + `construir_imagen` + `getMapId` corren
        TODOS dentro del mismo QThread (via `construir_imagen_para_preview`, ejecutado
        por PreviewWorker) — partir la sesión GEE entre dos hilos distintos cuelga
        `getMapId` indefinidamente (visto en vivo: 0% CPU, sin excepción, sin volver)."""
        if self._preview_en_curso:
            return
        receta = self.form.receta_actual()
        if receta is None:
            if interactivo:
                QMessageBox.warning(self, "Receta incompleta",
                                    "Completá índice, sensor y zona antes de refrescar el preview.")
            return
        if not config.hay_project_configurado():
            if not interactivo:
                return
            pid, ok = QInputDialog.getText(
                self, "Google Cloud project",
                "GEE requiere un Cloud project (gratis para uso no comercial).\n"
                "Registrate en code.earthengine.google.com/register y pegá acá el project ID:")
            if not ok or not pid.strip():
                return
            config.guardar_project(pid.strip())

        def construir_imagen_para_preview():
            auth.asegurar_sesion()
            sol = solicitud_desde_receta(receta)
            return ejecutor.construir_imagen(sol)

        self._preview_en_curso = True
        self.btn_preview.setEnabled(False)
        self.btn_preview.setText("Generando preview…")
        self.lbl_preview.setText("Generando preview… (calculando en GEE, puede tardar unos segundos)")
        self._preview_thread = refrescar_preview(
            self._mapa, construir_imagen_para_preview,
            on_ok=self._on_preview_ok, on_error=self._on_preview_error,
        )
        self._preview_thread.finished.connect(self._on_preview_fin)

    def _on_preview_ok(self, url_format: str) -> None:
        self.lbl_preview.setText("Preview cargado ✓ — el índice se pintó sobre el mapa.")

    def _on_preview_error(self, mensaje: str) -> None:
        self.lbl_preview.setText("Error al generar el preview (ver detalle).")
        QMessageBox.critical(self, "Error al generar el preview", mensaje)

    def _on_preview_fin(self) -> None:
        self._preview_en_curso = False
        self.btn_preview.setEnabled(True)
        self.btn_preview.setText("Refrescar preview")

    def closeEvent(self, event) -> None:
        self._mapa.close()  # detiene el ServidorMapa (widget no top-level: close() igual dispara closeEvent)
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec())
