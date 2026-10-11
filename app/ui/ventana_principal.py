"""Ventana principal: [ formulario | visor de script | mapa interactivo (F3b) ]."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QScrollArea, QSplitter,
    QPushButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QComboBox, QDoubleSpinBox, QHBoxLayout,
)
from PySide6.QtCore import Qt, QThreadPool, QTimer

from app.dominio.compilador import dialecto_js, dialecto_python
from app import recientes
from app.dominio.errores import ColumnaTablaEnConflicto, DemasiadosPeriodos, RecetaJSONInvalida
from app.dominio.periodos import periodos
from app.dominio import catalogo, tabla_poligonos
from app.dominio.receta import Producto, Salida, nombre_bandas
from app.dominio.receta_json import a_json, desde_json
from app.gee import config
from app.gee.exportador import ConfigExportTabla
from app.mapa.preview import PALETAS, paleta_por_dominio, vis_para_leyenda
from app.mapa.widget_mapa import QtWebEngineNoDisponible, WidgetMapa
from app.ui.dialogos.dialogo_export import DialogoExportDrive
from app.ui.dialogos.dialogo_serie import DialogoSerie
from app.ui.gestor_exports import GestorExports
from app.ui.panel_exports import PanelExports
from app.ui.panel_formulario import PanelFormulario
from app.ui.visor_script import VisorScript
from app.ui.workers import (
    WorkerConstruirImagenExport, WorkerConteo, WorkerDescarga, WorkerPreview, WorkerSerieTemporal,
    WorkerTabla,
)

# Debounce del auto-refresh de preview al cambiar la receta (decisión #6 F3b):
# regenerar mapid en cada cambio, pero sin saturar GEE en cada tecla/spin.
_DEBOUNCE_PREVIEW_MS = 800
# PERF-3: con una FeatureCollection grande embebida (tabla por polígono) compilar y pintar
# el script en cada tecla bloquea el hilo GUI: se debouncea el visor.
_DEBOUNCE_SCRIPT_MS = 300
_FEATURES_DEBOUNCE_SCRIPT = 50
_SIN_ARMAR = object()  # centinela: _actualizar_script() sin argumento arma su propia receta


class VentanaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GEE Recipe Builder")
        self.resize(1200, 800)
        self.pool = QThreadPool.globalInstance()
        # Recetas en vuelo, para reusar sin recomputar si el camino Drive se
        # ofrece desde el aviso de límite (DEC-2 de F0) o se elige del combo.
        self._receta_en_curso: object | None = None
        self._receta_export_en_curso: object | None = None
        # Serie temporal (F8): un worker cancelable a la vez + su diálogo no modal.
        self._worker_serie: WorkerSerieTemporal | None = None
        self._dialogo_serie: DialogoSerie | None = None
        # Tabla por polígono (F9): receta y carpeta del export a Drive en vuelo.
        self._tabla_en_curso: tuple | None = None

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
        # Paleta y rango manual del preview: solo UI, no entran en la Receta ni en los scripts.
        self.combo_paleta = QComboBox()
        for nombre in PALETAS:
            self.combo_paleta.addItem(nombre.capitalize(), nombre)
        self.spin_min = QDoubleSpinBox()
        self.spin_max = QDoubleSpinBox()
        for sp, tip in ((self.spin_min, "Mínimo del preview"), (self.spin_max, "Máximo del preview")):
            sp.setDecimals(4)
            sp.setRange(-1_000_000.0, 1_000_000.0)
            sp.setToolTip(tip)
        self.spin_max.setValue(1.0)
        self.btn_auto = QPushButton("Auto")
        self.btn_auto.setToolTip("Volver al rango automático (percentiles 2-98)")
        # Banda a previsualizar (F7): el preview es de UNA banda; por default indices[0].
        self.combo_banda = QComboBox()
        self.combo_banda.setToolTip("Banda (índice) que se previsualiza en el mapa")
        fila_vis = QHBoxLayout()
        fila_vis.addWidget(self.combo_banda)
        fila_vis.addWidget(self.combo_paleta)
        fila_vis.addWidget(self.spin_min)
        fila_vis.addWidget(self.spin_max)
        fila_vis.addWidget(self.btn_auto)
        lay_mapa.addLayout(fila_vis)
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
        # Exports (F5): el gestor es dueño del ciclo de vida (sobrevive al diálogo);
        # el panel es un dock no modal oculto por defecto (Ver → Exports).
        self.gestor_exports = GestorExports(parent=self)
        self.gestor_exports.lanzado.connect(self._on_export_lanzado)
        self.gestor_exports.fallo_lanzamiento.connect(self._on_export_fallo_lanzamiento)
        self.panel_exports = PanelExports(self.gestor_exports, self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.panel_exports)
        self.panel_exports.hide()
        self._armar_menu()

        self._override_vis = False      # True: el preview usa min/max de los spinbox (sin stretch)
        self._dominio_paleta: str | None = None
        self._ultimo_resultado = None
        # --- Wiring de actualización en vivo ---
        self._receta_script_pendiente = None
        self._debounce_script = QTimer(self)
        self._debounce_script.setSingleShot(True)
        self._debounce_script.setInterval(_DEBOUNCE_SCRIPT_MS)
        self._debounce_script.timeout.connect(self._on_debounce_script)
        self.form.cambiado.connect(self._on_form_cambiado)
        self.visor.dialecto_cambiado.connect(self._actualizar_script)
        self._on_form_cambiado()

        # --- Wiring AOI dibujada en el mapa → SelectorAOI (F3b) ---
        self._mapa.aoi_dibujada.connect(self.form.selector_aoi.set_geometria_dibujada)
        self._mapa.aoi_borrada.connect(lambda: self.form.selector_aoi.set_geometria_dibujada(None))

        # --- Wiring preview (F3b): auto-refresh debounced en cada cambio de receta
        # (decisión #6, evita regenerar el mapid en cada tecla) + botón manual ---
        # `_preview_en_curso` evita lanzar previews solapados: WorkerPreview corre en el
        # pool y `finalizado` lo baja siempre (éxito o error), así el flag nunca se traba.
        self._preview_en_curso = False
        self._preview_pendiente = False  # B1: pedido descartado con otro en vuelo → se reencola
        self._preview_resuelto = False   # ok/error llegó; si no, fue un disparo sin sesión
        self._debounce_preview = QTimer(self)
        self._debounce_preview.setSingleShot(True)
        self._debounce_preview.setInterval(_DEBOUNCE_PREVIEW_MS)
        self._debounce_preview.timeout.connect(lambda: self._lanzar_preview(interactivo=False))
        self.form.cambiado.connect(self._debounce_preview.start)
        # Conteo de escenas (F4): debounce propio + token de generación (sin flag anti-solape):
        # cada lanzamiento incrementa `_gen_conteo` y se descarta toda respuesta con token viejo.
        self._gen_conteo = 0
        self._umbral_conteo = 0
        self._debounce_conteo = QTimer(self)
        self._debounce_conteo.setSingleShot(True)
        self._debounce_conteo.setInterval(_DEBOUNCE_PREVIEW_MS)
        self._debounce_conteo.timeout.connect(self._lanzar_conteo)
        self.form.cambiado.connect(self._debounce_conteo.start)
        self.combo_paleta.currentIndexChanged.connect(self._on_paleta_cambiada)
        self.combo_banda.currentIndexChanged.connect(self._on_banda_cambiada)
        self.spin_min.valueChanged.connect(self._on_rango_manual)
        self.spin_max.valueChanged.connect(self._on_rango_manual)
        self.btn_auto.clicked.connect(self._on_auto)
        self._sincronizar_paleta_dominio()
        # Recuperación de exports pendientes, diferida para no demorar la apertura.
        QTimer.singleShot(0, self, self._recuperar_exports)

        print("VentanaPrincipal lista — form poblado, visor inicializado, mapa embebido")

    def _armar_menu(self) -> None:
        menu = self.menuBar().addMenu("&Archivo")
        act_guardar = menu.addAction("Guardar receta…")
        act_guardar.setShortcut("Ctrl+S")
        act_guardar.triggered.connect(self._guardar_receta)
        act_abrir = menu.addAction("Abrir receta…")
        act_abrir.setShortcut("Ctrl+O")
        act_abrir.triggered.connect(self._abrir_receta)
        self._menu_recientes = menu.addMenu("Recientes")
        self._menu_recientes.aboutToShow.connect(self._rebuild_recientes)
        menu_ver = self.menuBar().addMenu("&Ver")
        menu_ver.addAction(self.panel_exports.toggleViewAction())

    def _rebuild_recientes(self) -> None:
        self._menu_recientes.clear()
        rutas = recientes.listar()
        if not rutas:
            self._menu_recientes.addAction("(vacío)").setEnabled(False)
        for ruta in rutas:
            act = self._menu_recientes.addAction(Path(ruta).name)
            act.setToolTip(ruta)
            act.triggered.connect(lambda _=False, r=ruta: self._cargar_desde_archivo(r))

    def _guardar_receta(self) -> None:
        receta = self.form.receta_actual()
        if receta is None:
            QMessageBox.warning(self, "Receta incompleta",
                                "Completá índice, sensor y zona antes de guardar.")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar receta", "", "Receta (*.json)")
        if not ruta:
            return
        if not ruta.lower().endswith(".json"):
            ruta += ".json"
        try:
            Path(ruta).write_text(a_json(receta, self.form.selector_aoi.descriptor()),
                                  encoding="utf-8")
            recientes.agregar(ruta)
        except OSError as e:
            QMessageBox.critical(self, "No se pudo guardar", str(e))
            return
        self.statusBar().showMessage(f"Receta guardada en {ruta}", 5000)

    def _abrir_receta(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir receta", "", "Receta (*.json)")
        if ruta:
            self._cargar_desde_archivo(ruta)

    def _cargar_desde_archivo(self, ruta: str) -> None:
        try:
            cargada = desde_json(Path(ruta).read_text(encoding="utf-8"))
            avisos = self.form.cargar_receta(cargada)
            recientes.agregar(ruta)
        except (RecetaJSONInvalida, ValueError, OSError) as e:
            QMessageBox.critical(self, "No se pudo abrir la receta", str(e))
            return
        self.statusBar().showMessage(" · ".join(avisos) or f"Receta abierta: {Path(ruta).name}", 8000)

    def _on_form_cambiado(self) -> None:
        """Slot central: arma la receta una sola vez y la reparte a script y estimación."""
        receta = self.form.receta_actual()
        feats = getattr(receta, "features", None) if receta is not None else None
        if feats is not None and len(feats.get("features", ())) > _FEATURES_DEBOUNCE_SCRIPT:
            self._receta_script_pendiente = receta
            self._debounce_script.start()
        else:
            self._debounce_script.stop()
            self._receta_script_pendiente = None
            self._actualizar_script(receta)
        self.form.actualizar_estimacion(receta)
        self._override_vis = False        # cambio de receta: el rango vuelve a automático
        self._ultimo_resultado = None
        self._repoblar_combo_banda()
        self._sincronizar_paleta_dominio()

    def _repoblar_combo_banda(self) -> None:
        """`combo_banda` = índices de la selección; conserva la banda elegida si sigue, si no
        queda en `indices[0]`. Sin señales (el cambio ya viaja por `form.cambiado`)."""
        indices = self.form.indices_seleccionados()
        actual = self.combo_banda.currentData()
        self.combo_banda.blockSignals(True)
        try:
            self.combo_banda.clear()
            for sn in indices:
                self.combo_banda.addItem(sn, sn)
            if actual in indices:
                self.combo_banda.setCurrentIndex(indices.index(actual))
        finally:
            self.combo_banda.blockSignals(False)

    def _banda_preview(self) -> str | None:
        return self.combo_banda.currentData()

    def _on_banda_cambiada(self) -> None:
        # Otra banda: el min/max anterior no vale; paleta al default de su dominio y re-preview.
        self._override_vis = False
        self._ultimo_resultado = None
        self._sincronizar_paleta_dominio()
        self._debounce_preview.start()

    def _sincronizar_paleta_dominio(self) -> None:
        """La paleta vuelve al default del dominio solo si el dominio de la banda previsualizada cambió."""
        banda = self._banda_preview()
        ind = catalogo.cargar_catalogo().get(banda) if banda else self.form._indice_actual()
        if ind is None or ind.application_domain == self._dominio_paleta:
            return
        self._dominio_paleta = ind.application_domain
        pos = self.combo_paleta.findData(paleta_por_dominio(ind.application_domain))
        self.combo_paleta.blockSignals(True)
        self.combo_paleta.setCurrentIndex(pos)
        self.combo_paleta.blockSignals(False)

    def _on_paleta_cambiada(self) -> None:
        # Con un preview ya calculado se conserva su min/max vigente (override); sin él, solo
        # cambia la paleta del próximo stretch automático.
        if self._ultimo_resultado is not None:
            self._override_vis = True
        self._debounce_preview.start()

    def _on_rango_manual(self) -> None:
        self._override_vis = True
        self._debounce_preview.start()

    def _on_auto(self) -> None:
        self._override_vis = False
        self._debounce_preview.start()

    def _on_debounce_script(self) -> None:
        receta, self._receta_script_pendiente = self._receta_script_pendiente, None
        self._actualizar_script(receta)

    def _actualizar_script(self, receta=_SIN_ARMAR) -> None:
        if receta is _SIN_ARMAR:
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

        # Ruteo por producto: ni la serie ni la tabla usan `salida`.
        if receta.producto is Producto.SERIE_TEMPORAL:
            self._lanzar_serie(receta)
            return
        if receta.producto is Producto.TABLA_POLIGONOS:
            self._lanzar_tabla(receta)
            return

        if receta.salida is Salida.DRIVE:
            # Camino directo (F4): el usuario eligió "Drive / Cloud" en el combo.
            self._lanzar_construccion_export(receta)
            return

        if receta.salida is Salida.PREVIEW:
            # FIX-5 (mini-roadmap post-audit de cierre): el combo "Salida" ya
            # ofrecía "Preview en mapa" pero el botón Ejecutar seguía yendo
            # por el flujo de descarga a disco. Reusa el mismo camino que el
            # botón "Refrescar preview" del panel de mapa (F3b) — misma receta,
            # mismo WorkerPreview, mismo feedback en `lbl_preview`.
            self._lanzar_preview(interactivo=True)
            return

        destino, _ = QFileDialog.getSaveFileName(self, "Guardar GeoTIFF", "salida.tif",
                                                 "GeoTIFF (*.tif)")
        if not destino:
            return
        self._receta_en_curso = receta   # DEC-2 F0: si excede el límite, F4 reusa esta receta
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
        if tipo == "DescargaExcedeLimite":
            # DEC-2 de F0: en vez de un error crudo, ofrecer el camino Drive de
            # F4 con la MISMA receta (F2 clasificó el límite de 32MB/10000px).
            respuesta = QMessageBox.question(
                self, "Descarga excede el límite",
                f"{mensaje}\n\n¿Exportar a Google Drive en su lugar?",
            )
            if respuesta == QMessageBox.StandardButton.Yes and self._receta_en_curso is not None:
                self._lanzar_construccion_export(self._receta_en_curso)
            return
        QMessageBox.critical(self, f"Error ({tipo})", mensaje)

    def _on_fin(self) -> None:
        self.btn_ejecutar.setEnabled(True)
        self.btn_ejecutar.setText("Ejecutalo por mí (descarga a disco)")

    # ---- serie temporal (F8) ----
    def _serie_en_curso(self) -> bool:
        return self._worker_serie is not None and not self._worker_serie.ha_terminado()

    def _lanzar_serie(self, receta) -> None:
        """Valida los períodos en el hilo GUI (sin tocar GEE), abre el diálogo y lanza el worker."""
        if self._serie_en_curso():
            QMessageBox.information(self, "Serie en curso",
                                    "Ya hay una serie calculándose: cancelala o esperá a que termine.")
            if self._dialogo_serie is not None:
                self._dialogo_serie.show()
                self._dialogo_serie.raise_()
            return
        try:
            lista = periodos(receta.fecha_inicio, receta.fecha_fin, receta.periodo)
        except DemasiadosPeriodos as e:
            QMessageBox.warning(self, "Demasiados períodos", str(e))
            return
        except ValueError as e:
            QMessageBox.warning(self, "Rango de fechas inválido", str(e))
            return
        if self._dialogo_serie is not None:
            self._dialogo_serie.close()
            self._dialogo_serie.deleteLater()
        nombre = (f"serie_{nombre_bandas(receta.indices)}_{receta.periodo}_"
                  f"{receta.fecha_inicio}_{receta.fecha_fin}.csv")
        dlg = DialogoSerie(receta.indices, len(lista), sugerencia_csv=nombre, parent=self)
        worker = WorkerSerieTemporal(receta)
        s = worker.senales
        s.progreso.connect(dlg.on_progreso)
        s.terminado.connect(dlg.on_terminado)
        s.cancelado.connect(dlg.on_cancelado)
        s.error.connect(dlg.on_error)
        s.finalizado.connect(dlg.on_finalizado)
        dlg.cancelacion_pedida.connect(worker.solicitar_cancelacion)
        self._dialogo_serie, self._worker_serie = dlg, worker
        dlg.show()
        self.pool.start(worker)

    # ---- tabla por polígono (F9) ----
    def _lanzar_tabla(self, receta) -> None:
        """Elige la rama en el hilo Qt (el nº de features se conoce local): ≤ umbral → CSV local;
        más → `Export.table.toDrive` vía el gestor de exports."""
        try:     # colisión de columnas: avisar antes de pedir archivo/carpeta
            tabla_poligonos.columnas_para(receta.features, receta.indices)
        except ColumnaTablaEnConflicto as e:
            QMessageBox.warning(self, "Columna en conflicto", str(e))
            return
        nombre = f"tabla_{nombre_bandas(receta.indices)}_{receta.fecha_inicio}_{receta.fecha_fin}"
        if tabla_poligonos.es_local(receta.features):
            destino, _ = QFileDialog.getSaveFileName(self, "Guardar tabla CSV", f"{nombre}.csv",
                                                     "CSV (*.csv)")
            if not destino:
                return
            worker = WorkerTabla(receta, "local", destino)
            self._tabla_en_curso = None
        else:
            n = len(receta.features["features"])
            carpeta, ok = QInputDialog.getText(
                self, "Exportar tabla a Drive",
                f"La tabla tiene {n} polígonos (más de {tabla_poligonos.UMBRAL_TABLA_LOCAL}): "
                "se exporta como CSV a Google Drive.\nCarpeta de Drive:", text="GEE_exports")
            if not ok or not carpeta.strip():
                return
            worker = WorkerTabla(receta, "drive")
            self._tabla_en_curso = (receta, nombre, carpeta.strip())
        self.btn_ejecutar.setEnabled(False)
        self.btn_ejecutar.setText("Calculando tabla…")
        worker.senales.terminado.connect(self._on_tabla_ok)
        worker.senales.error.connect(self._on_tabla_error)
        worker.senales.finalizado.connect(self._on_fin)
        self.pool.start(worker)

    def _on_tabla_ok(self, payload) -> None:
        if self._tabla_en_curso is None:     # rama local: payload = ruta del CSV
            QMessageBox.information(self, "Listo", f"Tabla guardada en:\n{payload}")
            return
        receta, nombre, carpeta = self._tabla_en_curso
        self._tabla_en_curso = None
        cfg = ConfigExportTabla(
            descripcion=nombre, prefijo_archivo=nombre, carpeta_drive=carpeta,
            selectors=tuple(tabla_poligonos.columnas_para(receta.features, receta.indices)))
        self.gestor_exports.lanzar_tabla(payload, cfg)

    def _on_tabla_error(self, tipo: str, mensaje: str) -> None:
        self._tabla_en_curso = None
        QMessageBox.critical(self, f"Error en la tabla ({tipo})", mensaje)

    # ---- camino Drive/Cloud (F4) ----
    def _lanzar_construccion_export(self, receta) -> None:
        """Construye la ee.Image de `receta` (sin descargarla) y abre el diálogo
        de export a Drive/Cloud Storage con esa imagen (DEC-2 de F0)."""
        self.btn_ejecutar.setEnabled(False)
        self.btn_ejecutar.setText("Preparando export…")
        self._receta_export_en_curso = receta
        worker = WorkerConstruirImagenExport(receta)
        worker.senales.terminado.connect(self._on_imagen_export_lista)
        worker.senales.error.connect(self._on_error_export)
        worker.senales.finalizado.connect(self._on_fin)
        self.pool.start(worker)

    def _on_imagen_export_lista(self, payload) -> None:
        imagen, region = payload
        receta = self._receta_export_en_curso
        nombre = f"{nombre_bandas(receta.indices)}_{receta.fecha_inicio}_{receta.fecha_fin}"
        dlg = DialogoExportDrive(imagen, region, self.gestor_exports, sugerencia_nombre=nombre,
                                 scale=receta.escala, parent=self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()   # no modal (F5): cerrarlo no afecta al export

    def _recuperar_exports(self) -> None:
        """Retoma el seguimiento de exports no terminales del registro (F5). Sin project
        no hay sesión posible: se saltea en silencio."""
        if not config.hay_project_configurado() or not self.gestor_exports.registro.pendientes():
            return
        n = self.gestor_exports.recuperar()
        self.panel_exports.show()
        self.statusBar().showMessage(f"Retomando el seguimiento de {n} export(s) pendiente(s)", 8000)

    def _on_export_lanzado(self, _clave: str, task_id: str) -> None:
        self.panel_exports.show()
        self.statusBar().showMessage(f"Export lanzado (task {task_id}) — ver panel Exports", 8000)

    def _on_export_fallo_lanzamiento(self, _clave: str, mensaje: str) -> None:
        self.statusBar().showMessage(f"No se pudo lanzar el export: {mensaje.splitlines()[0]}", 10000)

    def _on_error_export(self, tipo: str, mensaje: str) -> None:
        QMessageBox.critical(self, f"Error al preparar el export ({tipo})", mensaje)

    def _lanzar_preview(self, interactivo: bool) -> None:
        """Construye la ee.Image de la receta actual y refresca el tile de preview en el mapa.
        `interactivo=True` (botón manual) pide el Cloud project si falta; el auto-refresh
        debounced (`interactivo=False`) se salta en silencio si todavía no hay project
        configurado, para no interrumpir al usuario mientras completa el formulario.

        Si ya hay un refresh en vuelo, el pedido se marca pendiente y se reencola al terminar (B1). El pipeline corre en
        `WorkerPreview` (QThreadPool + señales, mismo patrón robusto que la descarga):
        `finalizado` se emite SIEMPRE (éxito o error), así el botón nunca queda colgado
        en "Generando…". Todo el pipeline GEE (auth + imagen + stretch + getMapId) va en
        ese único hilo — partirlo entre dos hilos cuelga getMapId (visto en vivo)."""
        if self._preview_en_curso:
            self._preview_pendiente = True   # B1: se reencola al terminar el que está en vuelo
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

        paleta = PALETAS[self.combo_paleta.currentData()]
        vis_params = None
        if self._override_vis:
            if self.spin_min.value() >= self.spin_max.value():
                self.lbl_preview.setText("Rango manual inválido: el mínimo debe ser menor que el máximo.")
                return
            vis_params = {"min": self.spin_min.value(), "max": self.spin_max.value(),
                          "palette": paleta}
        self._preview_en_curso = True
        self._preview_resuelto = False
        self.btn_preview.setEnabled(False)
        self.btn_preview.setText("Generando preview…")
        self.lbl_preview.setText("Generando preview… (calculando en GEE, puede tardar unos segundos)")
        worker = WorkerPreview(receta, vis_params=vis_params, paleta=paleta,
                               banda=self._banda_preview(), interactivo=interactivo)
        worker.senales.terminado.connect(self._on_preview_ok)
        worker.senales.error.connect(self._on_preview_error)
        worker.senales.finalizado.connect(self._on_preview_fin)
        self.pool.start(worker)

    def _lanzar_conteo(self) -> None:
        """Cuenta escenas (total y con < X % nubes) de la receta actual. Se salta en silencio
        sin receta o sin Cloud project (igual que el preview no interactivo). Los errores van
        a `lbl_conteo`, nunca a un diálogo."""
        receta = self.form.receta_actual()
        if receta is None or not config.hay_project_configurado():
            self._gen_conteo += 1       # invalida cualquier conteo en vuelo
            self.form.lbl_conteo.setText("")
            return
        self._gen_conteo += 1
        gen = self._gen_conteo
        self.form.lbl_conteo.setText("Contando escenas…")
        self._umbral_conteo = self.form.umbral_nubes()
        worker = WorkerConteo(receta, gen, self._umbral_conteo, interactivo=False)
        worker.senales.terminado.connect(self._on_conteo_ok)
        worker.senales.error_gen.connect(self._on_conteo_error)
        self.pool.start(worker)

    def _on_conteo_ok(self, payload) -> None:
        gen, total, pocas = payload
        if gen != self._gen_conteo:
            return                      # respuesta vieja: ya hay un conteo más reciente
        texto = f"{total} escenas"
        if pocas is not None:
            texto += f", {pocas} con < {self._umbral_conteo} % nubes"
        self.form.lbl_conteo.setText(texto)

    def _on_conteo_error(self, gen: int, tipo: str, mensaje: str) -> None:
        if gen != self._gen_conteo:
            return
        self.form.lbl_conteo.setText(f"conteo no disponible: {mensaje}")

    def _on_preview_ok(self, resultado) -> None:
        """`resultado`: PreviewResultado. Pinta tiles + leyenda y vuelca min/max a los
        spinbox sin disparar otro preview. Si hay un pedido más nuevo encolado (B1) el
        resultado es de la receta vieja: se descarta y lo pinta el refresco reencolado."""
        self._preview_resuelto = True
        if self._preview_pendiente:
            return
        self._ultimo_resultado = resultado
        nota = "" if resultado.estirado else ("rango manual" if self._override_vis
                                              else "rango no estimado")
        leyenda = {**vis_para_leyenda(resultado.vis), "nota": nota}
        self._mapa.cargar_preview(resultado.url, leyenda)
        for sp, clave in ((self.spin_min, "min"), (self.spin_max, "max")):
            sp.blockSignals(True)
            sp.setValue(float(resultado.vis[clave]))
            sp.blockSignals(False)
        self.lbl_preview.setText("Preview cargado ✓ — el índice se pintó sobre el mapa.")

    def _on_preview_error(self, tipo: str, mensaje: str) -> None:
        self._preview_resuelto = True
        self.lbl_preview.setText(f"Error al generar el preview ({tipo}) — ver detalle.")
        QMessageBox.critical(self, f"Error al generar el preview ({tipo})", mensaje)

    def _on_preview_fin(self) -> None:
        self._preview_en_curso = False
        self.btn_preview.setEnabled(True)
        self.btn_preview.setText("Refrescar preview")
        if not self._preview_resuelto:   # disparo automático sin sesión GEE (B2): sin OAuth
            self.lbl_preview.setText("Preview no generado: sin sesión GEE (usá «Refrescar preview»).")
        if self._preview_pendiente:
            self._preview_pendiente = False
            self._debounce_preview.start()

    def closeEvent(self, event) -> None:
        # Solo corta el polling local: los tasks siguen en GEE y se retoman al reabrir.
        self.gestor_exports.detener_todo()
        if self._serie_en_curso():
            self._worker_serie.solicitar_cancelacion()   # corta antes del próximo período
        self._mapa.close()  # detiene el ServidorMapa (widget no top-level: close() igual dispara closeEvent)
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    try:
        ventana = VentanaPrincipal()
    except QtWebEngineNoDisponible as e:
        # Sin QtWebEngine no hay mapa: mensaje accionable en vez de un traceback crudo.
        print(e, file=sys.stderr)
        QMessageBox.critical(None, "Falta QtWebEngine", str(e))
        sys.exit(1)
    ventana.show()
    sys.exit(app.exec())
