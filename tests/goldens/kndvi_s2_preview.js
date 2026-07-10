var spectral = require('users/dmlmont/spectral:spectral');
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(function(img){
  return spectral.computeIndex(img, ['kNDVI'], {'N': img.select('B8'), 'R': img.select('B4')});
});
var img = col.median().clip(aoi);
Map.addLayer(img.select('kNDVI'), {}, 'kNDVI');
Map.centerObject(aoi);