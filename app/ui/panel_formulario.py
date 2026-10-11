"""Formulario index-first: índice → sensor → zona → fechas → máscara → composición → salida."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QDateEdit, QLabel, QGroupBox,
    QSpinBox, QLineEdit, QHBoxLayout, QListWidget, QListWidgetItem,
)
from pathlib import Path

from PySide6.QtCore import Signal, QDate, Qt

from app.dominio import catalogo
from app.dominio.aoi import FuenteAOI, bbox_de
from app.dominio.estimador import estimar_tamano_descarga, texto_estimacion
from app.dominio.errores import FuenteAOIError
from app.dominio.receta import PERIODOS, Producto, Receta, Salida
from app.ui.widget_parametros import PanelParametros
from app.ui.widget_aoi import SelectorAOI

COMPOSICIONES = [
    ("Mediana", "median"), ("Media", "mean"), ("Mínimo", "min"),
    ("Máximo", "max"), ("Mosaico (más reciente)", "mosaic"),
]
SALIDAS = [  # (etiqueta, valor, habilitada) — valores = Salida.*.value de F1 ("descarga", no "disco")
    ("Descarga a disco", "descarga", True),
    ("Drive / Cloud", "drive", True),
    ("Preview en mapa", "preview", True),
]
PRODUCTOS = [  # (etiqueta, Producto) — la tabla por polígono se suma en F9
    ("Imagen (GeoTIFF)", Producto.IMAGEN),
    ("Serie temporal", Producto.SERIE_TEMPORAL),
]
_ETIQUETAS_PERIODO = {"mensual": "Mensual", "16_dias": "16 días", "anual": "Anual"}


class PanelFormulario(QWidget):
    cambiado = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        raiz = QVBoxLayout(self)
        self._error_aoi: str | None = None
        self._escala_manual = False          # True solo si el usuario editó la escala
        self._aplicando_limites = False
        self._extras: list[str] = []         # índices tildados además del principal, en orden de tildado
        self._filtrados: list = []           # resultado vigente de catalogo.buscar (contenido de la lista)
        self._cache_sensores: dict[str, frozenset[str]] = {}

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
        # Buscador: texto libre + dominio. Filtran el contenido de combo_indice (selección única).
        self.edit_buscar = QLineEdit()
        self.edit_buscar.setPlaceholderText("Buscar por sigla, nombre o dominio…")
        self.edit_buscar.setClearButtonEnabled(True)
        self.combo_dominio = QComboBox()
        self.combo_dominio.addItem("Todos los dominios", None)
        for dom in catalogo.listar_dominios():
            self.combo_dominio.addItem(catalogo.etiqueta_dominio(dom), dom)
        # Multi-selección (F7): el principal (combo) va tildado y fijo; los extras se tildan acá.
        self.lista_indices = QListWidget()
        self.lista_indices.setFixedHeight(110)
        self.lista_indices.setToolTip("Tildá índices extra: se descargan juntos en un GeoTIFF multibanda")
        self.lbl_seleccion = QLabel()
        self.lbl_seleccion.setWordWrap(True)
        self._poblar_combo_indices(catalogo.buscar())
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.panel_params = PanelParametros()
        f_idx.addRow("Buscar", self.edit_buscar)
        f_idx.addRow("Dominio", self.combo_dominio)
        f_idx.addRow("Índice", self.combo_indice)
        f_idx.addRow("Sumar", self.lista_indices)
        f_idx.addRow("Elegidos", self.lbl_seleccion)
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
        self.chk_nubes = QCheckBox("Descartar escenas con nubes ≥")
        self.spin_nubes = QSpinBox()
        self.spin_nubes.setRange(0, 100)
        self.spin_nubes.setValue(20)
        self.spin_nubes.setSuffix(" %")
        fila_nubes = QWidget()
        h_nubes = QHBoxLayout(fila_nubes)
        h_nubes.setContentsMargins(0, 0, 0, 0)
        h_nubes.addWidget(self.chk_nubes)
        h_nubes.addWidget(self.spin_nubes)
        h_nubes.addStretch()
        self.lbl_conteo = QLabel()
        self.lbl_conteo.setWordWrap(True)
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
        self.combo_producto = QComboBox()
        for etiqueta, producto in PRODUCTOS:
            self.combo_producto.addItem(etiqueta, producto)
        self.combo_periodo = QComboBox()
        for p in PERIODOS:                     # única fuente de los valores de período
            self.combo_periodo.addItem(_ETIQUETAS_PERIODO.get(p, p), p)
        self.spin_escala = QSpinBox()
        self.spin_escala.setRange(10, 1000)
        self.spin_escala.setValue(10)
        self.spin_escala.setSuffix(" m")
        f_r.addRow("Desde", self.fecha_inicio)
        f_r.addRow("Hasta", self.fecha_fin)
        f_r.addRow(self.chk_mascara)
        f_r.addRow(fila_nubes)
        f_r.addRow(self.lbl_conteo)
        f_r.addRow("Composición", self.combo_comp)
        f_r.addRow("Escala", self.spin_escala)
        self.lbl_estimacion = QLabel()
        self.lbl_estimacion.setWordWrap(True)
        f_r.addRow(self.lbl_estimacion)
        f_r.addRow("Producto", self.combo_producto)
        f_r.addRow("Período", self.combo_periodo)
        f_r.addRow("Salida", self.combo_salida)
        self._form_resto = f_r
        raiz.addWidget(caja_resto)
        raiz.addStretch()

        # --- Wiring ---
        self.combo_indice.currentIndexChanged.connect(self._on_indice)
        self.edit_buscar.textChanged.connect(self._on_filtro_indices)
        self.combo_dominio.currentIndexChanged.connect(self._on_filtro_indices)
        self.combo_sensor.currentIndexChanged.connect(self._on_sensor)
        self.lista_indices.itemChanged.connect(self._on_item_lista)
        self.spin_escala.valueChanged.connect(self._on_escala_editada)
        self.fecha_inicio.dateChanged.connect(self._aplicar_limites_fechas)
        self.fecha_fin.dateChanged.connect(self._aplicar_limites_fechas)
        self.combo_producto.currentIndexChanged.connect(self._on_producto)
        for sig in (
            self.panel_params.cambiado, self.selector_aoi.cambiado,
            self.fecha_inicio.dateChanged, self.fecha_fin.dateChanged,
            self.chk_mascara.toggled, self.chk_nubes.toggled, self.spin_nubes.valueChanged,
            self.combo_comp.currentIndexChanged,
            self.spin_escala.valueChanged, self.combo_salida.currentIndexChanged,
            self.combo_producto.currentIndexChanged, self.combo_periodo.currentIndexChanged,
        ):
            sig.connect(self.cambiado)
        self._on_producto()

        self._on_indice()  # inicializa sensor + params del primer índice

    def _indice_actual(self):
        return self.combo_indice.currentData()

    def indices_seleccionados(self) -> list[str]:
        """[principal] + extras tildados, en orden. Vacío si el combo no tiene índice."""
        ind = self._indice_actual()
        return [] if ind is None else [ind.short_name, *self._extras]

    def _ids_sensores(self, short_name: str) -> frozenset[str]:
        if short_name not in self._cache_sensores:
            self._cache_sensores[short_name] = frozenset(catalogo.sensores_de_indice(short_name))
        return self._cache_sensores[short_name]

    def _hay_sensor_comun(self, indices: list[str]) -> bool:
        return bool(frozenset.intersection(*(self._ids_sensores(i) for i in indices)))

    def _poblar_lista(self) -> None:
        """Reconstruye los ítems de `lista_indices` desde `_filtrados` (sin señales)."""
        self.lista_indices.blockSignals(True)
        try:
            self.lista_indices.clear()
            for ind in self._filtrados:
                it = QListWidgetItem(f"{ind.short_name} — {ind.long_name}")
                it.setData(Qt.ItemDataRole.UserRole, ind.short_name)
                self.lista_indices.addItem(it)
        finally:
            self.lista_indices.blockSignals(False)
        self._estados_lista()

    def _estados_lista(self) -> None:
        """Actualiza tildes y habilitación en el lugar (seguro dentro de `itemChanged`)."""
        sel = self.indices_seleccionados()
        self.lista_indices.blockSignals(True)
        try:
            for i in range(self.lista_indices.count()):
                it = self.lista_indices.item(i)
                sn = it.data(Qt.ItemDataRole.UserRole)
                marcado = sn in sel
                it.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)
                flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
                if marcado or not sel or self._hay_sensor_comun([*sel, sn]):
                    it.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
                    it.setToolTip("Índice principal (se cambia en el combo)"
                                  if sel and sn == sel[0] else "")
                else:
                    it.setFlags(flags)
                    it.setToolTip("sin sensor en común con la selección")
        finally:
            self.lista_indices.blockSignals(False)
        self.lbl_seleccion.setText(", ".join(sel))

    def _on_item_lista(self, item: QListWidgetItem) -> None:
        sn = item.data(Qt.ItemDataRole.UserRole)
        sel = self.indices_seleccionados()
        if not sel:
            return
        if sn == sel[0]:                       # el principal no se destilda
            self._estados_lista()
            return
        if item.checkState() == Qt.CheckState.Checked:
            if sn not in self._extras and self._hay_sensor_comun([*sel, sn]):
                self._extras.append(sn)
        elif sn in self._extras:
            self._extras.remove(sn)
        self._reaplicar_seleccion()

    def _reaplicar_seleccion(self) -> None:
        """Cambió la selección (no el principal): tildes, sensores y params; un solo `cambiado`."""
        previos = self.panel_params.valores()
        self.blockSignals(True)
        try:
            self._estados_lista()
            self._cargar_params()
            self.panel_params.set_valores(previos)      # lo editado por el usuario no se pierde
            self._repoblar_sensores(conservar=True)
            self._on_sensor()
        finally:
            self.blockSignals(False)
        self.cambiado.emit()

    def _cargar_params(self) -> None:
        cat = catalogo.cargar_catalogo()
        self.panel_params.cargar_grupos(
            [(sn, cat[sn].parametros_ajustables) for sn in self.indices_seleccionados()])

    def _repoblar_sensores(self, conservar: bool) -> None:
        """`combo_sensor` = intersección de sensores de la selección (sin señales)."""
        actual = self._sensor_actual()
        self.combo_sensor.blockSignals(True)
        try:
            self.combo_sensor.clear()
            for sen in catalogo.sensores_para_indices(self.indices_seleccionados()):
                self.combo_sensor.addItem(sen.display_name, sen)
            if conservar and actual is not None:
                pos = self.combo_sensor.findText(actual.display_name)
                if pos >= 0:
                    self.combo_sensor.setCurrentIndex(pos)
        finally:
            self.combo_sensor.blockSignals(False)

    def _poblar_combo_indices(self, indices) -> bool:
        """Repuebla `combo_indice` con `indices` conservando la selección si sigue presente.
        Sin señales (ni `_on_indice` ni `cambiado`). Devuelve True si cambió el índice
        seleccionado (o quedó vacío), para que el caller decida si repoblar sensor/params."""
        antes = self._indice_actual()
        self.combo_indice.blockSignals(True)
        try:
            self.combo_indice.clear()
            for ind in indices:
                self.combo_indice.addItem(f"{ind.short_name} — {ind.long_name}", ind)
            if antes is not None:
                pos = self.combo_indice.findText(f"{antes.short_name} — {antes.long_name}")
                self.combo_indice.setCurrentIndex(max(pos, 0) if indices else -1)
        finally:
            self.combo_indice.blockSignals(False)
        self._filtrados = list(indices)
        self._poblar_lista()
        despues = self._indice_actual()
        return despues is None or antes is None or despues.short_name != antes.short_name

    def _on_filtro_indices(self) -> None:
        """Texto o dominio cambiaron: repuebla el combo; un solo `_on_indice` al final."""
        indices = catalogo.buscar(self.edit_buscar.text(), self.combo_dominio.currentData())
        cambio = self._poblar_combo_indices(indices)
        if self._indice_actual() is None:
            self.lbl_desc.setText("Sin coincidencias")
            self.panel_params.cargar(())
            self.combo_sensor.blockSignals(True)
            self.combo_sensor.clear()
            self.combo_sensor.blockSignals(False)
            self.cambiado.emit()          # receta_actual() ahora es None
        elif cambio:
            self._on_indice()

    def _limpiar_filtro_indices(self) -> None:
        """Quita texto y dominio y repuebla el catálogo completo, sin emitir nada."""
        for w in (self.edit_buscar, self.combo_dominio):
            w.blockSignals(True)
        try:
            self.edit_buscar.clear()
            self.combo_dominio.setCurrentIndex(0)
        finally:
            self.edit_buscar.blockSignals(False)
            self.combo_dominio.blockSignals(False)
        self._poblar_combo_indices(catalogo.buscar())

    def _sensor_actual(self):
        return self.combo_sensor.currentData()

    def _on_indice(self) -> None:
        ind = self._indice_actual()
        if ind is None:
            return
        # Cambió el principal: el nuevo principal ya no es "extra" y los extras sin sensor
        # en común con él se destildan (en orden, voraz).
        antes = list(self._extras)
        kept: list[str] = []
        for e in antes:
            if e != ind.short_name and self._hay_sensor_comun([ind.short_name, *kept, e]):
                kept.append(e)
        self._extras = kept
        quitados = [e for e in antes if e not in kept and e != ind.short_name]
        # `Indice` (F1) no expone `.descripcion` — mostramos long_name + fórmula ASI.
        texto = f"{ind.long_name}  ·  fórmula: {ind.formula}"
        if quitados:
            texto += f"  ·  se destildaron por no compartir sensor: {', '.join(quitados)}"
        self.lbl_desc.setText(texto)
        self._estados_lista()
        self._cargar_params()
        self._repoblar_sensores(conservar=False)
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
        hay_prop_nubes = catalogo.propiedad_nubes(sen.collection_id) is not None
        self.chk_nubes.setEnabled(hay_prop_nubes)
        self.spin_nubes.setEnabled(hay_prop_nubes)
        if not hay_prop_nubes:
            self.chk_nubes.setChecked(False)
            self.chk_nubes.setToolTip(
                f"El sensor {sen.display_name} no informa % de nubes por escena.")
        else:
            self.chk_nubes.setToolTip("")
        nativa = catalogo.escala_nativa(sen.collection_id)
        if nativa is not None and not self._escala_manual:
            self.spin_escala.blockSignals(True)   # set programático: ni cambiado extra ni flag manual
            try:
                self.spin_escala.setValue(nativa)
            finally:
                self.spin_escala.blockSignals(False)
        self._aplicar_limites_fechas()
        self.cambiado.emit()

    def producto_actual(self) -> Producto:
        return Producto(self.combo_producto.currentData())

    def _on_producto(self) -> None:
        """Período visible solo con serie; con serie la salida no aplica (se deshabilita).
        No emite `cambiado`: lo hace la conexión directa del combo."""
        serie = self.producto_actual() is Producto.SERIE_TEMPORAL
        self._form_resto.setRowVisible(self.combo_periodo, serie)
        self.combo_salida.setEnabled(not serie)

    def _on_escala_editada(self) -> None:
        self._escala_manual = True

    def _aplicar_limites_fechas(self) -> None:
        """Limita ambos calendarios al rango del sensor y fuerza inicio <= fin con
        límites cruzados (Qt clampea; no se hace setDate). No emite `cambiado`."""
        if self._aplicando_limites:
            return
        sen = self._sensor_actual()
        if sen is None:
            return
        ini_s, fin_s = catalogo.rango_fechas(sen.collection_id)
        qmin = QDate.fromString(ini_s, "yyyy-MM-dd") if ini_s else QDate(1970, 1, 1)
        qmax = QDate.fromString(fin_s, "yyyy-MM-dd") if fin_s else QDate.currentDate()
        self._aplicando_limites = True
        self.fecha_inicio.blockSignals(True)
        self.fecha_fin.blockSignals(True)
        try:
            for de in (self.fecha_inicio, self.fecha_fin):
                de.setDateRange(qmin, qmax)
            self.fecha_inicio.setMaximumDate(self.fecha_fin.date())
            self.fecha_fin.setMinimumDate(self.fecha_inicio.date())
        finally:
            self.fecha_inicio.blockSignals(False)
            self.fecha_fin.blockSignals(False)
            self._aplicando_limites = False

    def actualizar_estimacion(self, receta: Receta | None) -> None:
        """Texto de tamaño estimado bajo la escala; vacío si no hay receta/geometría válida."""
        if receta is None or receta.producto is not Producto.IMAGEN:
            self.lbl_estimacion.setText("")   # la estimación de descarga solo aplica a imagen
            return
        try:
            est = estimar_tamano_descarga(bbox_de(receta.geometria), receta.escala,
                                          n_bandas=len(receta.indices), dtype="float32")
        except Exception:  # noqa: BLE001 — geometría vacía/inválida: etiqueta vacía, nunca levanta
            self.lbl_estimacion.setText("")
            return
        self.lbl_estimacion.setText(
            texto_estimacion(est, descarga_directa=receta.salida == Salida.DESCARGA))

    def umbral_nubes(self) -> int:
        """Valor del spin de nubes (X de "< X %"), aunque el checkbox esté destildado."""
        return self.spin_nubes.value()

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
            indices=self.indices_seleccionados(),                 # strings, no objetos Indice; [0] = principal
            sensor=sen.collection_id,                             # string, no el objeto Sensor
            geometria=geometria,                                   # GeoJSON dict (F1) — campo `geometria`, no `aoi`
            fecha_inicio=self.fecha_inicio.date().toString("yyyy-MM-dd"),
            fecha_fin=self.fecha_fin.date().toString("yyyy-MM-dd"),
            mascara_nubes=self.chk_mascara.isChecked(),
            composicion=self.combo_comp.currentData(),            # string .value — __post_init__ coacciona a enum
            salida=self.combo_salida.currentData(),               # "descarga" — matchea Salida.DESCARGA
            escala=self.spin_escala.value(),
            parametros=self.panel_params.valores(),
            max_nubes_pct=(self.spin_nubes.value()
                           if self.chk_nubes.isChecked() and self.chk_nubes.isEnabled() else None),
            producto=self.producto_actual(),
            periodo=(self.combo_periodo.currentData()
                     if self.producto_actual() is Producto.SERIE_TEMPORAL else None),
        )

    def cargar_receta(self, cargada) -> list[str]:
        """Inverso de `receta_actual`: vuelca una `RecetaCargada` en los widgets y emite
        `cambiado` UNA vez al final. Devuelve avisos (AOI degradado, valores no aplicables).
        Levanta ValueError (form intacto) si algún índice no existe, o si el sensor no existe
        o no es común a todos los índices. Imagen y serie (con su período) se restauran; la tabla
        por polígono (F9) todavía no: avisa y queda como imagen."""
        r = cargada.receta
        cat = catalogo.cargar_catalogo()
        desconocidos = [i for i in r.indices if i not in cat]
        if desconocidos:
            raise ValueError(f"Índice(s) que no existen en el catálogo: {', '.join(desconocidos)}.")
        primero = r.indices[0]
        ids = [s.collection_id for s in catalogo.sensores_para_indices(list(r.indices))]
        if r.sensor not in ids:
            raise ValueError(
                f"El sensor '{r.sensor}' no existe o no es compatible con {', '.join(r.indices)}.")
        self._limpiar_filtro_indices()   # un filtro activo no debe ocultar el índice a cargar
        idx_ind = next((i for i in range(self.combo_indice.count())
                        if self.combo_indice.itemData(i).short_name == primero), -1)
        if idx_ind < 0:
            raise ValueError(f"El índice '{primero}' no existe en el catálogo.")
        avisos: list[str] = []
        idx_prod = self.combo_producto.findData(r.producto)
        if idx_prod < 0:     # tabla_poligonos hasta F9
            avisos.append(
                f"El producto '{r.producto.value}' todavía no está disponible: se cargó como imagen.")
            idx_prod = self.combo_producto.findData(Producto.IMAGEN)
        self.blockSignals(True)      # _on_indice/_on_sensor/params emiten adentro
        try:
            self.combo_indice.blockSignals(True)
            self.combo_indice.setCurrentIndex(idx_ind)
            self.combo_indice.blockSignals(False)
            self._extras = list(r.indices[1:])        # ya validados: todos comparten sensor con r.sensor
            self._on_indice()                         # repuebla lista, sensores y params
            self.combo_sensor.blockSignals(True)
            self.combo_sensor.setCurrentIndex(
                next(i for i in range(self.combo_sensor.count())
                     if self.combo_sensor.itemData(i).collection_id == r.sensor))
            self.combo_sensor.blockSignals(False)
            self._on_sensor()                         # máscara, escala nativa y límites de F1

            ini_s, fin_s = catalogo.rango_fechas(r.sensor)
            qmin = QDate.fromString(ini_s, "yyyy-MM-dd") if ini_s else QDate(1970, 1, 1)
            qmax = QDate.fromString(fin_s, "yyyy-MM-dd") if fin_s else QDate.currentDate()
            for de in (self.fecha_inicio, self.fecha_fin):
                de.setDateRange(qmin, qmax)
            self.fecha_fin.setDate(QDate.fromString(r.fecha_fin, "yyyy-MM-dd"))
            self.fecha_inicio.setDate(QDate.fromString(r.fecha_inicio, "yyyy-MM-dd"))
            if (self.fecha_inicio.date().toString("yyyy-MM-dd") != r.fecha_inicio
                    or self.fecha_fin.date().toString("yyyy-MM-dd") != r.fecha_fin):
                avisos.append("Fechas fuera de la disponibilidad del sensor: se ajustaron.")
            self._aplicar_limites_fechas()

            if self.chk_mascara.isEnabled():
                self.chk_mascara.setChecked(r.mascara_nubes)
            elif r.mascara_nubes:
                avisos.append("El sensor no tiene máscara de nubes: se dejó desactivada.")
            if r.max_nubes_pct is not None:
                self.spin_nubes.setValue(r.max_nubes_pct)
            if self.chk_nubes.isEnabled():
                self.chk_nubes.setChecked(r.max_nubes_pct is not None)
            elif r.max_nubes_pct is not None:
                avisos.append("El sensor no informa % de nubes: se quitó el filtro por escena.")
            self.combo_comp.setCurrentIndex(max(0, self.combo_comp.findData(r.composicion.value)))
            idx_sal = self.combo_salida.findData(r.salida.value)
            if idx_sal >= 0 and self.combo_salida.model().item(idx_sal).isEnabled():
                self.combo_salida.setCurrentIndex(idx_sal)
            else:
                avisos.append(f"La salida '{r.salida.value}' no está disponible: se dejó la actual.")
            self.combo_producto.setCurrentIndex(idx_prod)   # _on_producto: período y salida
            if r.periodo is not None:
                self.combo_periodo.setCurrentIndex(self.combo_periodo.findData(r.periodo))
            self.spin_escala.setValue(r.escala)
            if self.spin_escala.value() != r.escala:
                avisos.append(f"Escala {r.escala} m fuera de rango: se ajustó a {self.spin_escala.value()} m.")
            self._escala_manual = True    # lo cargado no lo pisa el default por sensor
            self.panel_params.set_valores(r.parametros)

            d = cargada.descriptor_aoi
            tipo = d.get("tipo") if d else None
            if tipo in {"bbox", "geojson-dict"} or (
                    tipo in {"shapefile", "geojson"} and d.get("ruta") and Path(d["ruta"]).exists()):
                self.selector_aoi.set_descriptor(d)
            else:
                motivo = (f"No se encontró {d['ruta']}" if d and d.get("ruta")
                          else "La receta no traía descriptor de zona")
                avisos.append(f"{motivo}: se cargó la geometría embebida como zona dibujada.")
                self.selector_aoi.set_descriptor({"tipo": "geojson-dict", "geojson": r.geometria})
        finally:
            self.combo_indice.blockSignals(False)
            self.combo_sensor.blockSignals(False)
            self.blockSignals(False)
        self.cambiado.emit()
        return avisos

    def ultimo_error_aoi(self) -> str | None:
        """Mensaje de `FuenteAOIError` de la última llamada a `receta_actual`, si la hubo."""
        return self._error_aoi
