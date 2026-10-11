"""F8 — CSV de la serie temporal y escritor único de CSV."""
from app.dominio.serie_csv import FilaSerie, escribir_csv, filas_a_csv, filas_a_texto

_FILAS = [FilaSerie("2023-01-01", "2023-02-01", 4, {"NDVI": 0.5, "EVI": 0.25}),
          FilaSerie("2023-02-01", "2023-03-01", 0, {"NDVI": None, "EVI": None})]


def test_header_exacto_un_indice():
    texto = filas_a_csv(_FILAS[:1], ["NDVI"])
    assert texto.splitlines()[0] == "periodo_inicio,periodo_fin,NDVI_mean,n_imagenes"
    assert texto.splitlines()[1] == "2023-01-01,2023-02-01,0.5,4"


def test_header_dos_indices_en_orden_de_indices():
    lineas = filas_a_csv(_FILAS, ["EVI", "NDVI"]).splitlines()
    assert lineas[0] == "periodo_inicio,periodo_fin,EVI_mean,NDVI_mean,n_imagenes"
    assert lineas[1] == "2023-01-01,2023-02-01,0.25,0.5,4"


def test_none_es_celda_vacia():
    assert filas_a_csv(_FILAS, ["NDVI", "EVI"]).splitlines()[2] == "2023-02-01,2023-03-01,,,0"


def test_indice_ausente_en_medias_es_vacio():
    assert filas_a_csv([FilaSerie("a", "b", 1, {})], ["NDVI"]).splitlines()[1] == "a,b,,1"


def test_filas_a_texto_generico_y_comillas():
    assert filas_a_texto(["x", "y"], [["a,b", 1.5]]) == 'x,y\r\n"a,b",1.5\r\n'


def test_escribir_csv_con_bom(tmp_path):
    ruta = tmp_path / "serie.csv"
    escribir_csv(ruta, filas_a_csv(_FILAS, ["NDVI"]))
    crudo = ruta.read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in crudo and b"\r\r\n" not in crudo
