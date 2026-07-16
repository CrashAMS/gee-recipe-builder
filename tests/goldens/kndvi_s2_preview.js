var spectral = require('users/dmlmont/spectral:spectral');
function escalarS2(img){var b=['B1','B2','B3','B4','B5','B6','B7','B8','B8A','B9','B11','B12'];return img.addBands(img.select(b).multiply(0.0001),null,true);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(escalarS2);
col = col.map(function(img){
  return spectral.computeIndex(img, ['kNDVI'], {'N': img.select('B8'), 'R': img.select('B4')});
});
var img = col.median().clip(aoi);
Map.addLayer(img.select('kNDVI'), {}, 'kNDVI');
Map.centerObject(aoi);