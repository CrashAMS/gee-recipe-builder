var spectral = require('users/dmlmont/spectral:spectral');
function maskLandsatC1SR_L8(img){var qa=img.select('pixel_qa');var m=qa.bitwiseAnd(1<<5).eq(0).and(qa.bitwiseAnd(1<<3).eq(0));return img.updateMask(m);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('LANDSAT/LC08/C01/T1_SR')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(maskLandsatC1SR_L8);
col = col.map(function(img){
  return spectral.computeIndex(img, ['NDVI'], {'N': img.select('B5'), 'R': img.select('B4')});
});
var img = col.median().clip(aoi);
var url = img.select('NDVI').getDownloadURL({scale: 10, region: aoi, format: 'GEO_TIFF'});
print(url);