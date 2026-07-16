var spectral = require('users/dmlmont/spectral:spectral');
function maskLandsatC1SR_L457(img){var qa=img.select('pixel_qa');var cloud=qa.bitwiseAnd(1<<5).and(qa.bitwiseAnd(1<<7)).or(qa.bitwiseAnd(1<<3));var mask2=img.mask().reduce(ee.Reducer.min());return img.updateMask(cloud.not()).updateMask(mask2);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('LANDSAT/LE07/C01/T1_SR')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(maskLandsatC1SR_L457);
col = col.map(function(img){
  return spectral.computeIndex(img, ['NDVI'], {'N': img.select('B4'), 'R': img.select('B3')});
});
var img = col.median().clip(aoi);
var url = img.select('NDVI').getDownloadURL({scale: 10, region: aoi, format: 'GEO_TIFF'});
print(url);