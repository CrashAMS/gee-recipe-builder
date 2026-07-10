from app.dominio.catalogo.indices import cargar_catalogo, sensores_de_indice, simbolos_banda


def test_catalogo_carga_y_cuenta():
    cat = cargar_catalogo()
    assert len(cat) > 200                      # conteo derivado, NO citado ([HALLAZGO-1.4])


def test_bands_json_17_simbolos():
    assert len(simbolos_banda()) == 17


def test_evi_separa_bandas_de_parametros():
    evi = cargar_catalogo()["EVI"]             # [HALLAZGO-1.1]: 3 bandas + 4 params
    assert evi.bandas_requeridas == frozenset({"N", "R", "B"})
    assert {p.nombre for p in evi.parametros_ajustables} == {"g", "C1", "C2", "L"}


def test_ndvi_trivial():
    assert cargar_catalogo()["NDVI"].bandas_requeridas == frozenset({"N", "R"})


def test_kernel_kndvi_incluido_y_resuelto():
    kndvi = cargar_catalogo()["kNDVI"]          # DEC-F1-kernel: incluido
    assert kndvi.es_kernel
    assert kndvi.bandas_requeridas == frozenset({"N", "R"})
    assert "sigma" in {p.nombre for p in kndvi.parametros_ajustables}


def test_kernel_kevi_incluye_L_como_parametro_no_banda():
    kevi = cargar_catalogo()["kEVI"]
    assert kevi.bandas_requeridas == frozenset({"N", "R", "B"})
    assert "L" not in kevi.bandas_requeridas
    assert {p.nombre for p in kevi.parametros_ajustables} == {"g", "C1", "C2", "L", "sigma"}


def test_radar_excluido_del_catalogo():
    assert "DPDD" not in cargar_catalogo()      # application_domain == 'radar', SAR excluido


def test_todo_el_catalogo_clasifica_sin_simbolos_desconocidos():
    cargar_catalogo()                           # no debe levantar SimboloDesconocido


def test_ndvi_soporta_s2_y_landsat():
    s = sensores_de_indice("NDVI")
    assert "COPERNICUS/S2_SR_HARMONIZED" in s
    assert "LANDSAT/LC08/C02/T1_L2" in s
