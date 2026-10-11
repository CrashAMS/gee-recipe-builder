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


def test_todos_los_perfiles_tienen_escala_e_inicio():
    for cid, p in PERFILES.items():
        assert p.escala_nativa_m, cid
        assert p.fecha_inicio, cid


def test_s2_10m_y_propiedad_nubes():
    for cid in ("COPERNICUS/S2", "COPERNICUS/S2_SR_HARMONIZED"):
        assert PERFILES[cid].escala_nativa_m == 10
        assert PERFILES[cid].prop_nubes == "CLOUDY_PIXEL_PERCENTAGE"
    assert PERFILES["COPERNICUS/S2_SR"].fecha_inicio == "2017-03-28"


def test_landsat_c2_30m_cloud_cover():
    p = PERFILES["LANDSAT/LC08/C02/T1_L2"]
    assert p.escala_nativa_m == 30 and p.prop_nubes == "CLOUD_COVER"


def test_modis_escalas_sin_propiedad_nubes():
    assert PERFILES["MODIS/061/MOD09GQ"].escala_nativa_m == 250
    assert PERFILES["MODIS/061/MOD09GA"].escala_nativa_m == 500
    assert PERFILES["MODIS/061/MCD43A4"].escala_nativa_m == 500
    for cid, p in PERFILES.items():
        if cid.startswith("MODIS/"):
            assert p.prop_nubes is None, cid


def test_fecha_fin_none_o_posterior_al_inicio():
    for cid, p in PERFILES.items():
        assert p.fecha_fin is None or p.fecha_fin >= p.fecha_inicio, cid


def test_funciones_publicas_coinciden_con_perfiles():
    from app.dominio import catalogo
    for cid, p in PERFILES.items():
        assert catalogo.escala_nativa(cid) == p.escala_nativa_m
        assert catalogo.rango_fechas(cid) == (p.fecha_inicio, p.fecha_fin)
        assert catalogo.propiedad_nubes(cid) == p.prop_nubes
