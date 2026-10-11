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


def test_buscar_por_sigla_y_por_nombre():
    from app.dominio.catalogo import buscar
    assert "NDVI" in {i.short_name for i in buscar("ndvi")}
    por_nombre = buscar("normalized difference vegetation")
    assert "NDVI" in {i.short_name for i in por_nombre}
    assert all("normalized difference vegetation" in i.long_name.lower() for i in por_nombre)


def test_buscar_filtra_por_dominio_y_combina_con_texto():
    from app.dominio.catalogo import buscar
    agua = buscar(dominio="water")
    assert agua and {i.application_domain for i in agua} == {"water"}
    combinado = buscar("ndwi", "water")
    assert combinado and all(i.application_domain == "water" for i in combinado)
    assert "NDVI" not in {i.short_name for i in buscar("ndvi", "water")}


def test_buscar_agua_acentos_y_mayusculas():
    from app.dominio.catalogo import buscar
    agua = buscar("agua")
    assert {i.short_name for i in buscar(dominio="water")} <= {i.short_name for i in agua}
    veg = {i.short_name for i in buscar("VEGETACION")}
    assert veg == {i.short_name for i in buscar("vegetación")}
    assert "NDVI" in veg


def test_buscar_sin_argumentos_devuelve_todo_y_sin_match_vacio():
    from app.dominio.catalogo import buscar, listar_indices
    assert len(buscar()) == len(listar_indices())
    assert buscar("zzzzqqqq") == []


def test_listar_dominios_sin_radar():
    from app.dominio.catalogo import listar_dominios, etiqueta_dominio
    doms = listar_dominios()
    assert "radar" not in doms
    assert {"vegetation", "water", "burn"} <= set(doms)
    assert etiqueta_dominio("water") == "Agua"
