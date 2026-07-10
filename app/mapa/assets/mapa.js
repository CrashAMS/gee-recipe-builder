let map, bridge = null, capaAOI = null, capaPreview = null;

function initMapa() {
  map = L.map('map').setView([-34.6, -58.4], 5);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);

  // Solo polígono y rectángulo para AOI (decisión #11)
  map.pm.addControls({
    position: 'topleft',
    drawPolygon: true, drawRectangle: true,
    drawMarker: false, drawPolyline: false, drawCircle: false,
    drawCircleMarker: false, drawText: false,
    editMode: true, dragMode: false, cutPolygon: false, removalMode: true,
  });

  map.on('pm:create', (e) => {
    if (capaAOI) map.removeLayer(capaAOI);   // una sola AOI viva (decisión #11)
    capaAOI = e.layer;
    emitirAOI(capaAOI);
    capaAOI.on('pm:edit', () => emitirAOI(capaAOI));  // re-emitir al editar vértices
  });
  map.on('pm:remove', () => { capaAOI = null; if (bridge) bridge.aoi_borrada(); });

  // Establecer canal (post-load; el bridge queda listo para los eventos)
  new QWebChannel(qt.webChannelTransport, (channel) => { bridge = channel.objects.bridge; });
}

function emitirAOI(layer) {
  const geometria = layer.toGeoJSON().geometry;   // extraer .geometry (DEC 5)
  if (bridge) bridge.polygon_drawn(JSON.stringify(geometria));
}

// ── Python→JS (via runJavaScript) ──
function cargarPreview(urlFormat) {
  if (capaPreview) map.removeLayer(capaPreview);
  capaPreview = L.tileLayer(urlFormat, { maxZoom: 20, opacity: 0.75 }).addTo(map);
}
function limpiarPreview() {
  if (capaPreview) { map.removeLayer(capaPreview); capaPreview = null; }
}

document.addEventListener('DOMContentLoaded', initMapa);
