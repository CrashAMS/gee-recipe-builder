import ee, eemont
ee.Initialize()

aoi = ee.Geometry({'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]})
col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
       .filterBounds(aoi)
       .filterDate('2023-01-01', '2023-12-31')
       .filter(ee.Filter.lt('CLOUD_COVER', 30)))
col = col.maskClouds().scaleAndOffset()
col = col.spectralIndices(['NDVI'])
img = col.median().clip(aoi)
url = img.select('NDVI').getDownloadURL({'scale': 10, 'region': aoi, 'format': 'GEO_TIFF'})
print(url)