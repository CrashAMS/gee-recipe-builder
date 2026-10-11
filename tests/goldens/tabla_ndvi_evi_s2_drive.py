import ee, eemont
ee.Initialize()

aoi = ee.Geometry({'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]})
col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2023-01-01', '2023-12-31'))
col = col.maskClouds().scaleAndOffset()
col = col.spectralIndices(['NDVI', 'EVI'])
img = col.median().clip(aoi)
poligonos = ee.FeatureCollection({'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.49, -34.6], [-58.49, -34.59], [-58.5, -34.59], [-58.5, -34.6]]]}, 'properties': {'lote': 'L1', 'ha': 10.5}}, {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[-58.49, -34.6], [-58.480000000000004, -34.6], [-58.480000000000004, -34.59], [-58.49, -34.59], [-58.49, -34.6]]]}, 'properties': {'lote': 'L2', 'ha': 11.5}}]})
tabla = poligonos
tabla = img.select('NDVI').reduceRegions(
    collection=tabla,
    reducer=(ee.Reducer.mean()
             .combine(ee.Reducer.min(), sharedInputs=True)
             .combine(ee.Reducer.max(), sharedInputs=True)
             .combine(ee.Reducer.stdDev(), sharedInputs=True)
             .combine(ee.Reducer.count(), sharedInputs=True)
             .setOutputs(['NDVI_mean', 'NDVI_min', 'NDVI_max', 'NDVI_std', 'NDVI_n'])),
    scale=10)
tabla = img.select('EVI').reduceRegions(
    collection=tabla,
    reducer=(ee.Reducer.mean()
             .combine(ee.Reducer.min(), sharedInputs=True)
             .combine(ee.Reducer.max(), sharedInputs=True)
             .combine(ee.Reducer.stdDev(), sharedInputs=True)
             .combine(ee.Reducer.count(), sharedInputs=True)
             .setOutputs(['EVI_mean', 'EVI_min', 'EVI_max', 'EVI_std', 'EVI_n'])),
    scale=10)
tabla = tabla.select(['lote', 'ha', 'NDVI_mean', 'NDVI_min', 'NDVI_max', 'NDVI_std', 'NDVI_n', 'EVI_mean', 'EVI_min', 'EVI_max', 'EVI_std', 'EVI_n'], None, False)
task = ee.batch.Export.table.toDrive(collection=tabla, description='tabla_NDVI-EVI', fileFormat='CSV', selectors=['lote', 'ha', 'NDVI_mean', 'NDVI_min', 'NDVI_max', 'NDVI_std', 'NDVI_n', 'EVI_mean', 'EVI_min', 'EVI_max', 'EVI_std', 'EVI_n'])
task.start()