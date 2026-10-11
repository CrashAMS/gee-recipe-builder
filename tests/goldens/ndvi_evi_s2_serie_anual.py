import ee, eemont
ee.Initialize()

aoi = ee.Geometry({'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]})
col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2021-06-01', '2023-03-01')
       .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))
col = col.maskClouds().scaleAndOffset()
col = col.spectralIndices(['NDVI', 'EVI'])
periodos = [
    ('2021-06-01', '2022-01-01'),
    ('2022-01-01', '2023-01-01'),
    ('2023-01-01', '2023-03-01'),
]


def fila(ini, fin):
    sub = col.filterDate(ini, fin)
    n = sub.size()
    medias = ee.Dictionary(ee.Algorithms.If(n.gt(0), sub.mean().select(['NDVI', 'EVI']).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=10, maxPixels=1e9), {}))
    props = {'periodo_inicio': ini, 'periodo_fin': fin}
    props['NDVI_mean'] = ee.Algorithms.If(medias.contains('NDVI'), medias.get('NDVI'), None)
    props['EVI_mean'] = ee.Algorithms.If(medias.contains('EVI'), medias.get('EVI'), None)
    props['n_imagenes'] = n
    return ee.Feature(None, props)


serie = ee.FeatureCollection([fila(ini, fin) for ini, fin in periodos])
print(serie.getInfo())