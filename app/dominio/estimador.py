"""Estimador puro de tamaño de descarga (pre-aviso 'excede -> ofrecé Drive'). Consumido por F2."""
from __future__ import annotations
import math
from dataclasses import dataclass

LIMITE_BYTES = 33554432        # 32 MiB - tope de getDownloadURL
LIMITE_LADO_PX = 10000         # tope de píxeles por lado
BYTES_POR_DTYPE = {"int8": 1, "uint8": 1, "int16": 2, "uint16": 2,
                    "int32": 4, "uint32": 4, "float32": 4, "float64": 8}


@dataclass(frozen=True)
class EstimacionDescarga:
    ancho_px: int
    alto_px: int
    n_bandas: int
    bytes_estimados: int
    excede_bytes: bool
    excede_lado: bool

    @property
    def excede(self) -> bool:
        return self.excede_bytes or self.excede_lado

    @property
    def motivo(self) -> str:
        """Causa accionable para el mensaje de aviso ('excede -> ofrecé Drive'),
        uniforme para que F2/F4 no tengan que re-derivar el porqué a mano."""
        if self.excede_bytes and self.excede_lado:
            return "excede_bytes_y_lado"
        if self.excede_bytes:
            return "excede_bytes"
        if self.excede_lado:
            return "excede_lado"
        return "ok"


def estimar_tamano_descarga(bbox_lonlat: tuple[float, float, float, float],
                             escala_m: float, n_bandas: int,
                             dtype: str = "float32") -> EstimacionDescarga:
    """bbox=(minx,miny,maxx,maxy) en lon/lat. Aproxima m/grado a la latitud media
    (conservador para el aviso; la grilla exacta de GEE depende del CRS)."""
    minx, miny, maxx, maxy = bbox_lonlat
    lat_media = (miny + maxy) / 2.0
    m_por_grado_lat = 111320.0
    m_por_grado_lon = 111320.0 * math.cos(math.radians(lat_media))
    ancho_m = abs(maxx - minx) * m_por_grado_lon
    alto_m = abs(maxy - miny) * m_por_grado_lat
    ancho_px = math.ceil(ancho_m / escala_m)
    alto_px = math.ceil(alto_m / escala_m)
    bytes_est = ancho_px * alto_px * n_bandas * BYTES_POR_DTYPE[dtype]
    return EstimacionDescarga(
        ancho_px, alto_px, n_bandas, bytes_est,
        excede_bytes=bytes_est > LIMITE_BYTES,
        excede_lado=max(ancho_px, alto_px) > LIMITE_LADO_PX)
