from app.dominio.estimador import estimar_tamano_descarga, LIMITE_BYTES


def test_aoi_chica_no_excede():
    e = estimar_tamano_descarga((-58.5, -34.6, -58.4, -34.5), escala_m=10, n_bandas=1)
    assert not e.excede


def test_aoi_grande_excede_bytes():
    e = estimar_tamano_descarga((-60.0, -35.0, -58.0, -33.0), escala_m=10, n_bandas=3)
    assert e.excede_bytes and e.excede


def test_excede_lado_px():
    e = estimar_tamano_descarga((-60.0, -35.0, -58.0, -33.0), escala_m=1, n_bandas=1)
    assert e.excede_lado


def test_math_dtype():
    e = estimar_tamano_descarga((0.0, 0.0, 0.001, 0.001), escala_m=10, n_bandas=2, dtype="float32")
    assert e.bytes_estimados == e.ancho_px * e.alto_px * 2 * 4


def test_motivo_ok_cuando_no_excede():
    e = estimar_tamano_descarga((-58.5, -34.6, -58.4, -34.5), escala_m=10, n_bandas=1)
    assert e.motivo == "ok"


def test_motivo_excede_bytes_y_lado():
    e = estimar_tamano_descarga((-60.0, -35.0, -58.0, -33.0), escala_m=1, n_bandas=3)
    assert e.motivo == "excede_bytes_y_lado"
