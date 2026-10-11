"""Registro persistente de los exports lanzados por la app (F5) — `exports.json`.

Sin `ee` ni Qt. Solo guarda tasks que la app lanzó (nunca lista la cuenta). Lo escribe
únicamente el hilo Qt (slots de `GestorExports`): los workers emiten señales y nunca
tocan el archivo, por eso no hay lock. Escritura atómica vía `config.escribir_json_atomico`.

Entrada: {task_id, nombre, destino, carpeta, fecha_lanzado (ISO), estado, mensaje_error, uris}.
`estado` es el `.value` de `EstadoExport`. El archivo guarda la más reciente primero.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app.gee import config

TOPE = 50
# Valores de EstadoExport terminales (espejo de exportador._TERMINALES; un test los ata).
ESTADOS_TERMINALES = frozenset({"completado", "fallido", "cancelado", "desconocido"})


def ruta_default() -> Path:
    return config._dir_config() / "exports.json"


def es_terminal(entrada: dict) -> bool:
    return entrada.get("estado") in ESTADOS_TERMINALES


def nueva_entrada(task_id: str, nombre: str, destino: str, carpeta: str | None,
                  fecha_lanzado: str | None = None, estado: str = "pendiente") -> dict:
    return {
        "task_id": task_id,
        "nombre": nombre,
        "destino": destino,
        "carpeta": carpeta,
        "fecha_lanzado": fecha_lanzado or datetime.now().isoformat(timespec="seconds"),
        "estado": estado,
        "mensaje_error": None,
        "uris": [],
    }


class RegistroExports:
    def __init__(self, ruta: Path | str | None = None) -> None:
        self.ruta = Path(ruta) if ruta is not None else ruta_default()

    # ---- lectura ----
    def _leer(self, estricto: bool = False) -> list[dict]:
        """`estricto` (caminos de escritura): un OSError transitorio re-levanta en vez de
        devolver [] — si no, la escritura siguiente pisaría todas las entradas."""
        if not self.ruta.exists():
            return []
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except OSError:
            if estricto:
                raise
            return []
        except ValueError:          # JSON inválido / encoding roto: no se pisa en silencio
            self._apartar_corrupto()
            return []
        if not isinstance(datos, list):
            self._apartar_corrupto()
            return []
        return [e for e in datos if isinstance(e, dict) and isinstance(e.get("task_id"), str)]

    def _apartar_corrupto(self) -> None:
        try:
            os.replace(self.ruta, self.ruta.with_name(self.ruta.name + ".bak"))
        except OSError:
            pass

    def listar(self) -> list[dict]:
        """Más reciente primero."""
        return self._leer()

    def obtener(self, task_id: str) -> dict | None:
        return next((e for e in self._leer() if e["task_id"] == task_id), None)

    def pendientes(self) -> list[dict]:
        return [e for e in self._leer() if not es_terminal(e)]

    # ---- escritura (solo hilo Qt) ----
    def agregar(self, entrada: dict) -> None:
        """Agrega al frente (reemplaza si el id ya estaba). Con más de `TOPE`, descarta
        las terminales más viejas; las no terminales nunca se descartan."""
        entradas = [entrada] + [e for e in self._leer(estricto=True) if e["task_id"] != entrada["task_id"]]
        exceso = len(entradas) - TOPE
        if exceso > 0:
            for i in range(len(entradas) - 1, 0, -1):   # de la más vieja a la más nueva
                if exceso == 0:
                    break
                if es_terminal(entradas[i]):
                    del entradas[i]
                    exceso -= 1
        config.escribir_json_atomico(self.ruta, entradas)

    def actualizar_estado(self, task_id: str, estado: str, mensaje_error: str | None = None,
                          uris: list[str] | tuple[str, ...] | None = None) -> bool:
        """Actualiza estado (y error/uris). False si el id no está (no escribe nada)."""
        entradas = self._leer(estricto=True)
        for e in entradas:
            if e["task_id"] == task_id:
                cambios = {"estado": estado, "mensaje_error": mensaje_error}
                if uris is not None:
                    cambios["uris"] = list(uris)
                if all(e.get(k) == v for k, v in cambios.items()):
                    return True     # nada cambió: no reescribir el archivo en cada poll
                e.update(cambios)
                config.escribir_json_atomico(self.ruta, entradas)
                return True
        return False
