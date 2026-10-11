"""Tests de GestorExports + PollerTask/WorkerLanzarExport (F5). Exportador fake, pool
sincrónico (o inerte) e intervalo 0: nada toca GEE ni hilos reales."""
from types import SimpleNamespace

import pytest

from app.gee import auth, config
from app.gee.exportador import ConfigExport, DestinoExport, EstadoExport, interpretar_estado
from app.gee.registro_exports import RegistroExports, nueva_entrada
from app.ui.gestor_exports import GestorExports
from app.ui.workers import PollerTask, WorkerLanzarExport

_CFG = ConfigExport(descripcion="ndvi_x", prefijo_archivo="ndvi_x", destino=DestinoExport.DRIVE,
                    region=None, carpeta_drive="GEE", scale=10.0)


class PoolSync:
    """Corre el worker en el acto, en el hilo actual (señales → conexión directa)."""
    def start(self, w):
        w.run()


class PoolInerte:
    def __init__(self):
        self.workers = []

    def start(self, w):
        self.workers.append(w)


class FakeExportador:
    def __init__(self, estados=("RUNNING", "COMPLETED"), lanzar_exc=None, registro=None):
        self._estados = list(estados)
        self._lanzar_exc = lanzar_exc
        self._registro = registro
        self.consultas = []
        self.cancelados = []
        self.registrado_al_primer_poll = None

    def lanzar(self, image, cfg):
        if self._lanzar_exc:
            raise self._lanzar_exc
        return SimpleNamespace(id="T1")

    def estado_por_id(self, task_id):
        if self._registro is not None and self.registrado_al_primer_poll is None:
            self.registrado_al_primer_poll = self._registro.obtener(task_id) is not None
        self.consultas.append(task_id)
        crudo = self._estados.pop(0) if len(self._estados) > 1 else self._estados[0]
        st = {"state": crudo, "id": task_id}
        if crudo == "COMPLETED":
            st["destination_uris"] = ["https://drive/x"]
        return interpretar_estado(st)

    def cancelar_por_id(self, task_id):
        self.cancelados.append(task_id)
        self._estados = ["CANCELLED"]


@pytest.fixture
def sesiones(monkeypatch):
    llamadas = []
    monkeypatch.setattr(auth, "asegurar_sesion", lambda p=None: llamadas.append(p) or "proj")
    return llamadas


@pytest.fixture
def init_ok(monkeypatch):
    """Sesión ya inicializable sin OAuth (camino de recuperar())."""
    intentos = []
    monkeypatch.setattr(config, "leer_project", lambda: "proj")
    monkeypatch.setattr(auth, "intentar_inicializar", lambda p: intentos.append(p) or True)
    return intentos


def _gestor(tmp_path, exp, pool=None):
    reg = RegistroExports(tmp_path / "exports.json")
    if isinstance(exp, FakeExportador) and exp._registro is None:
        exp._registro = reg
    return GestorExports(registro=reg, exportador=exp, pool=pool or PoolSync(), intervalo_ms=0)


def test_workers_no_autodelete():
    assert WorkerLanzarExport(None, _CFG).autoDelete() is False
    assert PollerTask("T1").autoDelete() is False


def test_lanzar_registra_el_id_antes_del_primer_poll(qtbot, tmp_path, sesiones):
    exp = FakeExportador()
    g = _gestor(tmp_path, exp)
    lanzados = []
    g.lanzado.connect(lambda clave, tid: lanzados.append((clave, tid)))
    clave = g.lanzar(None, _CFG, clave="k1")
    assert clave == "k1" and lanzados == [("k1", "T1")]
    assert exp.registrado_al_primer_poll is True
    e = g.registro.obtener("T1")
    assert e["nombre"] == "ndvi_x" and e["destino"] == "drive" and e["carpeta"] == "GEE"


def test_completado_actualiza_estado_y_uris(qtbot, tmp_path, sesiones):
    exp = FakeExportador(estados=("READY", "RUNNING", "COMPLETED"))
    g = _gestor(tmp_path, exp)
    g.lanzar(None, _CFG)
    e = g.registro.obtener("T1")
    assert e["estado"] == EstadoExport.COMPLETADO.value and e["uris"] == ["https://drive/x"]
    assert exp.consultas == ["T1"] * 3
    assert not g.siguiendo("T1")


def test_cuota_al_lanzar_no_registra_nada(qtbot, tmp_path, sesiones):
    exp = FakeExportador(lanzar_exc=RuntimeError("Too many tasks already in the queue"))
    g = _gestor(tmp_path, exp)
    fallos = []
    g.fallo_lanzamiento.connect(lambda clave, msg: fallos.append((clave, msg)))
    g.lanzar(None, _CFG, clave="k1")
    assert g.registro.listar() == []
    assert fallos and fallos[0][0] == "k1" and "Cuota" in fallos[0][1]
    assert exp.consultas == []


def test_recuperar_solo_pollea_no_terminales_sin_oauth(qtbot, tmp_path, sesiones, init_ok):
    exp = FakeExportador(estados=("COMPLETED",))
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("viejo", "a", "drive", None, estado="completado"))
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None, estado="corriendo"))
    assert g.recuperar() == 1
    assert exp.consultas == ["vivo"]
    assert sesiones == [] and init_ok == ["proj"]   # intentar_inicializar, nunca asegurar_sesion
    assert g.registro.obtener("vivo")["estado"] == "completado"


def test_id_expirado_queda_desconocido(qtbot, tmp_path, sesiones, init_ok):
    exp = FakeExportador(estados=("UNKNOWN",))
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("viejo", "a", "drive", None))
    g.recuperar()
    assert g.registro.obtener("viejo")["estado"] == EstadoExport.DESCONOCIDO.value
    assert g.registro.pendientes() == []


def test_recuperar_sin_sesion_no_abre_oauth_ni_marca_fallido(qtbot, tmp_path, sesiones, monkeypatch):
    monkeypatch.setattr(config, "leer_project", lambda: "proj")
    monkeypatch.setattr(auth, "intentar_inicializar", lambda p: False)
    exp = FakeExportador()
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    cambios = []
    g.cambio.connect(cambios.append)
    g.recuperar()
    assert sesiones == []                       # asegurar_sesion (OAuth) jamás llamado
    assert exp.consultas == []
    assert g.registro.obtener("vivo")["estado"] == "pendiente"   # puede seguir vivo server-side
    assert "Sin sesión GEE" in g.aviso("vivo") and "vivo" in cambios


def test_recuperar_sin_project_tampoco_abre_oauth(qtbot, tmp_path, sesiones, monkeypatch):
    monkeypatch.setattr(config, "leer_project", lambda: None)
    g = _gestor(tmp_path, FakeExportador())
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.recuperar()
    assert sesiones == [] and "Sin sesión GEE" in g.aviso("vivo")


def test_reintentar_recuperacion_retoma_al_haber_sesion(qtbot, tmp_path, sesiones, monkeypatch):
    estado = {"ok": False}
    monkeypatch.setattr(config, "leer_project", lambda: "proj")
    monkeypatch.setattr(auth, "intentar_inicializar", lambda p: estado["ok"])
    exp = FakeExportador(estados=("COMPLETED",))
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.recuperar()
    assert exp.consultas == []
    estado["ok"] = True
    assert g.reintentar_recuperacion() == 1
    assert exp.consultas == ["vivo"] and g.aviso("vivo") is None
    assert g.registro.obtener("vivo")["estado"] == "completado"
    assert g.reintentar_recuperacion() == 0


def test_lanzar_exitoso_dispara_reintento_de_recuperacion(qtbot, tmp_path, sesiones, monkeypatch):
    estado = {"ok": False}
    monkeypatch.setattr(config, "leer_project", lambda: "proj")
    monkeypatch.setattr(auth, "intentar_inicializar", lambda p: estado["ok"])
    exp = FakeExportador(estados=("COMPLETED",))
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("viejo", "a", "drive", None))
    g.recuperar()
    estado["ok"] = True
    g.lanzar(None, _CFG, clave="k1")
    assert "viejo" in exp.consultas and g.registro.obtener("viejo")["estado"] == "completado"


def test_poller_interactivo_usa_asegurar_sesion(qtbot, tmp_path, sesiones, monkeypatch):
    def prohibido(p):
        raise AssertionError("intentar_inicializar no debe usarse en el camino interactivo")
    monkeypatch.setattr(auth, "intentar_inicializar", prohibido)
    exp = FakeExportador(estados=("COMPLETED",))
    g = _gestor(tmp_path, exp)
    g.lanzar(None, _CFG, clave="k1")            # export lanzado por el usuario
    assert sesiones and exp.consultas == ["T1"]   # asegurar_sesion sí se usa


def test_cancelar_llama_cancelar_por_id(qtbot, tmp_path, sesiones):
    exp = FakeExportador(estados=("RUNNING",))
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.cancelar("vivo")
    assert exp.cancelados == ["vivo"]
    assert g.registro.obtener("vivo")["estado"] == EstadoExport.CANCELADO.value


def test_cancelar_sobre_poller_vivo_reusa_el_poller(qtbot, tmp_path, sesiones, init_ok):
    pool = PoolInerte()
    exp = FakeExportador(estados=("RUNNING",))
    g = _gestor(tmp_path, exp, pool=pool)
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.recuperar()
    assert g.siguiendo("vivo")
    g.cancelar("vivo")
    assert len(pool.workers) == 1   # no arranca un segundo poller
    pool.workers[0].run()
    assert exp.cancelados == ["vivo"]


def test_detener_todo_no_cancela(qtbot, tmp_path, sesiones):
    pool = PoolInerte()
    exp = FakeExportador(estados=("RUNNING",))
    g = _gestor(tmp_path, exp, pool=pool)
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.recuperar()
    cambios = []
    g.cambio.connect(cambios.append)
    g.detener_todo()
    pool.workers[0].run()   # el poller "sigue" en el pool tras detener: sale sin cancelar
    assert exp.cancelados == []
    assert exp.consultas == []
    assert cambios == []     # desconectado: no le habla más al gestor
    assert g.registro.obtener("vivo")["estado"] == "pendiente"


def test_cancelar_fallido_sigue_poleando(qtbot, tmp_path, sesiones):
    exp = FakeExportador(estados=("RUNNING", "COMPLETED"))

    def boom(_tid):
        raise RuntimeError("sin permiso")
    exp.cancelar_por_id = boom
    g = _gestor(tmp_path, exp)
    g.registro.agregar(nueva_entrada("vivo", "b", "drive", None))
    g.cancelar("vivo")
    assert exp.consultas == ["vivo", "vivo"]   # no abandona el task vivo
    assert g.registro.obtener("vivo")["estado"] == "completado"


def test_registro_no_escribible_no_mata_el_seguimiento(qtbot, tmp_path, sesiones, monkeypatch):
    exp = FakeExportador(estados=("COMPLETED",))
    g = _gestor(tmp_path, exp)

    def lleno(_e):
        raise OSError("disco lleno")
    monkeypatch.setattr(g.registro, "agregar", lleno)
    lanzados = []
    g.lanzado.connect(lambda c, t: lanzados.append(t))
    g.lanzar(None, _CFG)
    assert lanzados == ["T1"] and exp.consultas == ["T1"]


# --- F9: lanzar_tabla ---
def test_lanzar_tabla_registra_destino_drive_tabla_con_carpeta(qtbot, tmp_path, sesiones):
    from app.gee.exportador import ConfigExportTabla

    class ExpTabla(FakeExportador):
        def lanzar_tabla(self, fc, cfg):
            self.recibido = (fc, cfg)
            return SimpleNamespace(id="TT1")

    exp = ExpTabla(estados=("RUNNING",))
    g = _gestor(tmp_path, exp, pool=PoolInerte())
    w = None
    cfg = ConfigExportTabla("tabla_NDVI", "tabla_NDVI", "GEE_exports", ("lote", "NDVI_mean"))
    clave = g.lanzar_tabla("FC", cfg, clave="kt")
    w = g._lanzadores[clave]
    w.run()
    assert exp.recibido == ("FC", cfg)
    e = g.registro.obtener("TT1")
    assert e["destino"] == "drive-tabla" and e["carpeta"] == "GEE_exports" and e["nombre"] == "tabla_NDVI"


def test_panel_muestra_drive_tabla_csv(qtbot, tmp_path):
    from app.ui.panel_exports import PanelExports
    reg = RegistroExports(tmp_path / "exports.json")
    reg.agregar(nueva_entrada("TT1", "tabla_NDVI", "drive-tabla", "GEE_exports", estado="corriendo"))
    panel = PanelExports(GestorExports(registro=reg, exportador=FakeExportador(), pool=PoolInerte(),
                                       intervalo_ms=0))
    qtbot.addWidget(panel)
    assert panel.tabla.item(0, 1).text() == "Drive (tabla CSV): GEE_exports"


# --- PERF-1: pollers en pool propio acotado ---
def test_pollers_usan_pool_propio_acotado_no_el_global(qtbot, tmp_path):
    from PySide6.QtCore import QThreadPool
    from app.ui.gestor_exports import MAX_HILOS_POLLERS
    g = GestorExports(registro=RegistroExports(tmp_path / "exports.json"),
                      exportador=FakeExportador(), intervalo_ms=0)
    assert g._pool_pollers is not QThreadPool.globalInstance()
    assert g._pool_pollers.maxThreadCount() == MAX_HILOS_POLLERS


# --- B3: un error transitorio de red no corta el seguimiento ---
def _exp_con_fallas(n_fallas):
    exp = FakeExportador(estados=("COMPLETED",))
    orig = exp.estado_por_id
    cuenta = {"n": 0}

    def flaky(task_id):
        cuenta["n"] += 1
        if cuenta["n"] <= n_fallas:
            raise ConnectionError("red caída")
        return orig(task_id)
    exp.estado_por_id = flaky
    return exp


def test_poller_reintenta_errores_transitorios_antes_de_fallar(monkeypatch, sesiones):
    from app.ui import workers
    monkeypatch.setattr(workers, "_ESPERA_REINTENTO_MS", 0)
    exp = _exp_con_fallas(workers._REINTENTOS_POLL)        # 3 fallas y después responde
    p = PollerTask("T1", exportador=exp, intervalo_ms=0)
    fallos, progresos = [], []
    p.senales.fallo.connect(lambda t, m: fallos.append(m))
    p.senales.progreso.connect(lambda t, prog: progresos.append(prog))
    p.run()
    assert fallos == [] and progresos and progresos[-1].terminal
    exp = _exp_con_fallas(workers._REINTENTOS_POLL + 1)    # se agotan los reintentos → fallo
    p = PollerTask("T1", exportador=exp, intervalo_ms=0)
    p.senales.fallo.connect(lambda t, m: fallos.append(m))
    p.run()
    assert len(fallos) == 1 and "red caída" in fallos[0]
