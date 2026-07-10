import ee, eemont
ee.Initialize()

aoi = ee.Geometry({'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]})
col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2023-01-01', '2023-12-31'))
col = col.maskClouds().scaleAndOffset()
col = col.spectralIndices(['EVI'], L=1.0, g=2.5)
img = col.median().clip(aoi)
task = ee.batch.Export.image.toDrive(image=img.select('EVI'), region=aoi, scale=10, description='EVI')
task.start()