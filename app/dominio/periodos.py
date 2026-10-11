"""Generador puro de períodos de la serie temporal (F8).

`periodos(inicio, fin, periodo)` parte el rango `[inicio, fin)` en intervalos
semiabiertos `[ini, fin)`, con la misma semántica que `filterDate` de GEE (la
fecha final queda excluida). Mensual y anual son meses / años calendario
recortados al rango; `16_dias` son ventanas consecutivas ancladas en `inicio`.
El último intervalo se recorta a `fin`. Lo consumen la ventana (validación en el
hilo GUI), el worker y el plan de compilación: los scripts llevan la lista literal.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.dominio.errores import DemasiadosPeriodos
from app.dominio.receta import PERIODOS

TOPE_PERIODOS = 60
_DIAS_VENTANA = 16


def _fecha(s: str, nombre: str) -> date:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} debe ser una fecha 'YYYY-MM-DD'; recibí {s!r}.") from None


def _siguiente_mes(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def _siguiente_anio(d: date) -> date:
    return date(d.year + 1, 1, 1)


def _siguiente_16_dias(d: date) -> date:
    return d + timedelta(days=_DIAS_VENTANA)


_SIGUIENTE = {"mensual": _siguiente_mes, "16_dias": _siguiente_16_dias, "anual": _siguiente_anio}
assert set(_SIGUIENTE) == set(PERIODOS), "periodos.py desalineado con receta.PERIODOS"


def periodos(fecha_inicio: str, fecha_fin: str, periodo: str) -> list[tuple[str, str]]:
    """Lista de `(ini, fin)` ISO. Rango vacío/invertido o período desconocido ->
    ValueError; más de `TOPE_PERIODOS` -> DemasiadosPeriodos (con N en el mensaje)."""
    if periodo not in _SIGUIENTE:
        raise ValueError(f"Período desconocido {periodo!r}; opciones: {', '.join(PERIODOS)}.")
    ini, fin = _fecha(fecha_inicio, "fecha_inicio"), _fecha(fecha_fin, "fecha_fin")
    if fin <= ini:
        raise ValueError(
            f"Rango de fechas vacío o invertido: {fecha_inicio} → {fecha_fin} "
            "(la fecha final se excluye, como en filterDate).")
    siguiente = _SIGUIENTE[periodo]
    salida: list[tuple[str, str]] = []
    actual = ini
    while actual < fin:
        corte = min(siguiente(actual), fin)
        salida.append((actual.isoformat(), corte.isoformat()))
        actual = corte
    if len(salida) > TOPE_PERIODOS:
        raise DemasiadosPeriodos(len(salida), TOPE_PERIODOS)
    return salida
