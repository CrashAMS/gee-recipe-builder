var spectral = require('users/dmlmont/spectral:spectral');
function maskModisGA(img){var qa=img.select('state_1km');var m=qa.bitwiseAnd(1<<0).eq(0).and(qa.bitwiseAnd(1<<2).eq(0)).and(qa.bitwiseAnd(1<<8).eq(0));return img.updateMask(m);}
function escalarModisGA(img){var b=['sur_refl_b01','sur_refl_b02','sur_refl_b03','sur_refl_b04','sur_refl_b06','sur_refl_b07'];return img.addBands(img.select(b).multiply(0.0001),null,true);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('MODIS/061/MOD09GA')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(maskModisGA);
col = col.map(escalarModisGA);
col = col.map(function(img){
  return spectral.computeIndex(img, ['NDVI'], {'N': img.select('sur_refl_b02'), 'R': img.select('sur_refl_b01')});
});
var img = col.median().clip(aoi);
var url = img.select('NDVI').getDownloadURL({scale: 10, region: aoi, format: 'GEO_TIFF'});
print(url);