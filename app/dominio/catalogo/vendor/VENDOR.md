# Vendor — awesome-spectral-indices (ASI)

Snapshot de 3 archivos JSON descargados del release **tag `0.11.0`** del repo
[awesome-spectral-indices/awesome-spectral-indices](https://github.com/awesome-spectral-indices/awesome-spectral-indices).

**Nunca apuntar a `main`** — el repo original muta sin versionar; el catálogo de F1
debe ser reproducible ([HALLAZGO-1.3] de la exploración F1-depth).

## Archivos y procedencia

| Archivo | URL raw | Fecha de descarga |
|---|---|---|
| `spectral-indices-dict.json` | https://raw.githubusercontent.com/awesome-spectral-indices/awesome-spectral-indices/0.11.0/output/spectral-indices-dict.json | 2026-07-09 |
| `bands.json` | https://raw.githubusercontent.com/awesome-spectral-indices/awesome-spectral-indices/0.11.0/output/bands.json | 2026-07-09 |
| `constants.json` | https://raw.githubusercontent.com/awesome-spectral-indices/awesome-spectral-indices/0.11.0/output/constants.json | 2026-07-09 |

Verificado al vendorizar:
- `spectral-indices-dict.json`: raíz `{"SpectralIndices": {...}}`, 279 índices.
- `bands.json`: 17 símbolos (A, B, G, G1, N, N2, R, RE1, RE2, RE3, S1, S2, T, T1, T2, WV, Y).
- `constants.json`: 26 constantes, cada una con `default` y `description`.

## Cómo actualizar el snapshot (tarea manual explícita)

1. Elegir el nuevo tag del repo ASI (nunca `main`).
2. Re-descargar los 3 archivos de ese tag con las mismas URLs (cambiando `0.11.0` por el tag nuevo).
3. Actualizar esta tabla (tag, fecha, conteos).
4. Re-correr `pytest tests/` — si algo rompe (símbolo nuevo no clasificado, golden desactualizado),
   resolverlo antes de commitear: ver `catalogo/kernel.py` para símbolos kernel nuevos y
   `UPDATE_GOLDENS=1 pytest tests/test_compilador.py` si el compilador cambia de salida.
