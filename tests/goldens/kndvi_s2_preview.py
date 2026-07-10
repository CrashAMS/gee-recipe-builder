import ee, eemont
ee.Initialize()

aoi = ee.Geometry({'type': 'Polygon', 'coordinates': [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]})
col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2023-01-01', '2023-12-31'))
col = col.scaleAndOffset()
col = col.spectralIndices(['kNDVI'])
img = col.median().clip(aoi)
# preview: img.select('kNDVI').getMapId(vis_params) -> tile URL (lo consume F3b)