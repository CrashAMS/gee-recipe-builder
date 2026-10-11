import ee, eemont
ee.Initialize()

aoi = ee.Geometry({'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]})
col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2023-01-01', '2023-12-31'))
col = col.maskClouds().scaleAndOffset()
col = col.spectralIndices(['NDVI', 'EVI', 'NDWI'], g=2.6)
img = col.median().clip(aoi)
url = img.select(['NDVI', 'EVI', 'NDWI']).getDownloadURL({'scale': 10, 'region': aoi, 'format': 'GEO_TIFF'})
print(url)