"""F8 — generador puro de períodos de la serie temporal."""
import pytest

from app.dominio.errores import DemasiadosPeriodos
from app.dominio.periodos import TOPE_PERIODOS, periodos


def test_mensual_bordes_de_mes():
    assert periodos("2023-01-15", "2023-04-01", "mensual") == [
        ("2023-01-15", "2023-02-01"), ("2023-02-01", "2023-03-01"), ("2023-03-01", "2023-04-01")]


def test_mensual_ultimo_recortado_y_cruce_de_anio():
    assert periodos("2023-11-01", "2024-01-10", "mensual") == [
        ("2023-11-01", "2023-12-01"), ("2023-12-01", "2024-01-01"), ("2024-01-01", "2024-01-10")]


def test_febrero_bisiesto():
    assert periodos("2024-02-01", "2024-03-01", "mensual") == [("2024-02-01", "2024-03-01")]
    # 16 días desde el 20/02/2024 cruza el 29/02.
    assert periodos("2024-02-20", "2024-03-20", "16_dias") == [
        ("2024-02-20", "2024-03-07"), ("2024-03-07", "2024-03-20")]


def test_16_dias_anclado_en_inicio_y_ultimo_recortado():
    assert periodos("2023-01-05", "2023-02-15", "16_dias") == [
        ("2023-01-05", "2023-01-21"), ("2023-01-21", "2023-02-06"), ("2023-02-06", "2023-02-15")]


def test_anual_recortado():
    assert periodos("2021-06-01", "2023-03-01", "anual") == [
        ("2021-06-01", "2022-01-01"), ("2022-01-01", "2023-01-01"), ("2023-01-01", "2023-03-01")]


def test_intervalos_contiguos_y_cubren_el_rango():
    ps = periodos("2020-01-03", "2022-07-19", "16_dias")
    assert ps[0][0] == "2020-01-03" and ps[-1][1] == "2022-07-19"
    assert all(a[1] == b[0] for a, b in zip(ps, ps[1:]))


def test_exactamente_60_ok_y_61_levanta_con_n():
    assert TOPE_PERIODOS == 60
    assert len(periodos("2020-01-01", "2025-01-01", "mensual")) == 60
    with pytest.raises(DemasiadosPeriodos, match="61") as exc:
        periodos("2020-01-01", "2025-01-02", "mensual")
    assert exc.value.n == 61 and "período más largo" in str(exc.value)


@pytest.mark.parametrize("ini,fin", [("2023-01-01", "2023-01-01"), ("2023-02-01", "2023-01-01")])
def test_rango_vacio_o_invertido(ini, fin):
    with pytest.raises(ValueError):
        periodos(ini, fin, "mensual")


def test_periodo_o_fecha_invalidos():
    with pytest.raises(ValueError):
        periodos("2023-01-01", "2023-03-01", "semanal")
    with pytest.raises(ValueError):
        periodos("2023/01/01", "2023-03-01", "mensual")
