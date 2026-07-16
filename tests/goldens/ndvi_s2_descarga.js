var spectral = require('users/dmlmont/spectral:spectral');
function maskS2clouds(col){
  var s2Clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY');
  var fil = ee.Filter.equals({leftField: 'system:index', rightField: 'system:index'});
  col = ee.ImageCollection(ee.Join.saveFirst('cloud_mask').apply(col, s2Clouds, fil));
  return col.map(function(img){
    var clouds = ee.Image(img.get('cloud_mask')).select('probability');
    img = img.addBands(clouds.gte(60).rename('CLOUD_MASK'));
    var notWater = img.select('SCL').neq(6);
    var darkPixels = img.select('B8').lt(0.15 * 1e4).multiply(notWater);
    var shadowAzimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')));
    var cloudProjection = img.select('CLOUD_MASK')
      .directionalDistanceTransform(shadowAzimuth, 100)
      .reproject({crs: img.select(0).projection(), scale: 10})
      .select('distance').mask();
    img = img.addBands(cloudProjection.multiply(darkPixels).rename('SHADOW_MASK'));
    var isCloudShadow = img.select('CLOUD_MASK').add(img.select('SHADOW_MASK')).gt(0)
      .focalMin(20, 'circle', 'meters').focalMax(50, 'circle', 'meters')
      .rename('CLOUD_SHADOW_MASK');
    return img.addBands(isCloudShadow).updateMask(isCloudShadow.not());
  });
}
function escalarS2(img){var b=['B1','B2','B3','B4','B5','B6','B7','B8','B8A','B9','B11','B12'];return img.addBands(img.select(b).multiply(0.0001),null,true);}
var aoi = ee.Geometry({"type": "Polygon", "coordinates": [[[-58.5, -34.6], [-58.4, -34.6], [-58.4, -34.5], [-58.5, -34.5], [-58.5, -34.6]]]});
var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2023-01-01', '2023-12-31');
col = maskS2clouds(col);
col = col.map(escalarS2);
col = col.map(function(img){
  return spectral.computeIndex(img, ['NDVI'], {'N': img.select('B8'), 'R': img.select('B4')});
});
var img = col.median().clip(aoi);
var url = img.select('NDVI').getDownloadURL({scale: 10, region: aoi, format: 'GEO_TIFF'});
print(url);