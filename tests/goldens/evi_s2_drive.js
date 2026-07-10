var spectral = require('users/dmlmont/spectral:spectral');
function maskS2clouds(img){var qa=img.select('QA60');var m=qa.bitwiseAnd(1<<10).eq(0).and(qa.bitwiseAnd(1<<11).eq(0));return img.updateMask(m);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = col.map(maskS2clouds);
col = col.map(function(img){
  return spectral.computeIndex(img, ['EVI'], {'B': img.select('B2'), 'N': img.select('B8'), 'R': img.select('B4'), 'L': 1.0, 'g': 2.5});
});
var img = col.median().clip(aoi);
Export.image.toDrive({image: img.select('EVI'), region: aoi, scale: 10, description: 'EVI'});