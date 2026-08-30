"""GeoJSON helpers."""

import math


def polygon_area_ha(geometry: dict) -> float:
    """
    Přibližná plocha GeoJSON Polygonu v hektarech.
    Ekvirektangulární aproximace (dost přesná pro pole v řádu do tisíců ha
    v mírných zeměpisných šířkách) — ne přesná geodetická plocha. Pokud
    potřebujeme přesnost pro fakturaci/kvóty, nahradit shapely + pyproj
    (Albers Equal Area nebo lokální UTM), ne tuhle aproximaci.
    """
    coords = geometry["coordinates"][0]
    if len(coords) < 3:
        return 0.0

    lat0 = sum(c[1] for c in coords) / len(coords)
    lat0_rad = math.radians(lat0)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(lat0_rad)

    projected = [(c[0] * m_per_deg_lon, c[1] * m_per_deg_lat) for c in coords]

    area_m2 = 0.0
    n = len(projected)
    for i in range(n):
        x1, y1 = projected[i]
        x2, y2 = projected[(i + 1) % n]
        area_m2 += x1 * y2 - x2 * y1
    area_m2 = abs(area_m2) / 2.0

    return area_m2 / 10_000.0
