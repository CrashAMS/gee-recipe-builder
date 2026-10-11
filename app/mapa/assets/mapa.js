let map, bridge = null, capaAOI = null, capaPreview = null, controlLeyenda = null;

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
function cargarPreview(urlFormat, vis) {
  if (!map) return;
  if (capaPreview) map.removeLayer(capaPreview);
  capaPreview = L.tileLayer(urlFormat, { maxZoom: 20, opacity: 0.75 }).addTo(map);
  if (vis) mostrarLeyenda(vis); else limpiarLeyenda();
}
function limpiarPreview() {
  if (!map) return;
  if (capaPreview) { map.removeLayer(capaPreview); capaPreview = null; }
  limpiarLeyenda();
}
// vis = {min, max, palette: [colores CSS ya normalizados en Python], nota?: string}
function mostrarLeyenda(vis) {
  if (!map) return;
  limpiarLeyenda();   // idempotente: una sola leyenda viva
  controlLeyenda = L.control({ position: 'bottomright' });
  controlLeyenda.onAdd = function () {
    const div = L.DomUtil.create('div', 'leyenda-preview');
    const colores = (vis.palette && vis.palette.length > 1) ? vis.palette : ['#ffffff', '#008000'];
    const barra = L.DomUtil.create('div', 'leyenda-barra', div);
    barra.style.background = 'linear-gradient(to right, ' + colores.join(', ') + ')';
    const etiquetas = L.DomUtil.create('div', 'leyenda-etiquetas', div);
    const fmt = (v) => String(Number(Number(v).toFixed(3)));
    etiquetas.innerHTML = '<span>' + fmt(vis.min) + '</span><span>' + fmt(vis.max) + '</span>';
    if (vis.nota) {
      const nota = L.DomUtil.create('div', 'leyenda-nota', div);
      nota.textContent = '(' + vis.nota + ')';
    }
    return div;
  };
  controlLeyenda.addTo(map);
}
function limpiarLeyenda() {
  if (controlLeyenda) { controlLeyenda.remove(); controlLeyenda = null; }
}

document.addEventListener('DOMContentLoaded', initMapa);
