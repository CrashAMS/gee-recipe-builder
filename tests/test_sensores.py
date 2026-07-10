from app.dominio.catalogo.sensores import PERFILES, sensores_compatibles, sensores_con_mascara


def test_termico_t2_compatible_c1_incompatible_c2():
    # [HALLAZGO-2.5]: L8 C1 tiene T2; C2 no. Un índice con T2 discrimina.
    comp = sensores_compatibles(frozenset({"N", "T2"}))
    assert "LANDSAT/LC08/C02/T1_L2" not in comp    # C2 no tiene T2
    assert "LANDSAT/LC08/C01/T1_SR" in comp        # C1 sí tiene T2


def test_s2_toa_sin_mascara():
    # [HALLAZGO-2.4]: S2 TOA soporta índices pero NO maskClouds.
    assert "COPERNICUS/S2" in PERFILES
    assert "COPERNICUS/S2" not in sensores_con_mascara()
    assert "COPERNICUS/S2_SR" in sensores_con_mascara()


def test_modis_gq_sin_mascara_ga_con_mascara():
    # MOD09GQ no está en el lookup de maskClouds; MOD09GA sí.
    assert "MODIS/061/MOD09GQ" not in sensores_con_mascara()
    assert "MODIS/061/MOD09GA" in sensores_con_mascara()


def test_cuarenta_collection_ids_opticos():
    assert len(PERFILES) == 40


def test_ningun_sensor_sar():
    assert "COPERNICUS/S1_GRD" not in PERFILES
    assert "JAXA/ALOS/PALSAR-2/Level2_2/ScanSAR" not in PERFILES
