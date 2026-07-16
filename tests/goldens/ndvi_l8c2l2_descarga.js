var spectral = require('users/dmlmont/spectral:spectral');
function maskLandsatC2(img){var qa=img.select('QA_PIXEL');var m=qa.bitwiseAnd(1<<2).eq(0).and(qa.bitwiseAnd(1<<3).eq(0)).and(qa.bitwiseAnd(1<<4).eq(0));return img.updateMask(m);}
function escalarLandsatC2_T10(img){var sr=['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7'];var s=img.select(sr).multiply(2.75e-05).add(-0.2);s=s.addBands(img.select(['ST_B10']).multiply(0.00341802).add(149));return img.addBands(s,null,true);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(maskLandsatC2);
col = col.map(escalarLandsatC2_T10);
col = col.map(function(img){
  return spectral.computeIndex(img, ['NDVI'], {'N': img.select('SR_B5'), 'R': img.select('SR_B4')});
});
var img = col.median().clip(aoi);
var url = img.select('NDVI').getDownloadURL({scale: 10, region: aoi, format: 'GEO_TIFF'});
print(url);