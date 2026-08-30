"""
UTM reprojekce pro GeoJSON polygony. Nutné pro CDSE Statistical API, kde
resx/resy jsou v jednotkách deklarovaného bounds CRS — pro metrové rozlišení
(10m Sentinel-1) potřebujeme metrický CRS, ne EPSG:4326 (stupně). Zjištěno
živým testem proti API 2026-08-30: se stupňovým CRS a resx=10 se celé AOI
sesbírá do jediného pixelu (sampleCount=1).
"""

from pyproj import Transformer


def utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone  # severní polokoule
    return 32700 + zone  # jižní polokoule


def reproject_geometry_to_utm(geometry: dict) -> tuple[dict, int]:
    """Vrátí (geometrie v UTM metrech, EPSG kód UTM zóny) pro Polygon geometrii v EPSG:4326."""
    coords = geometry["coordinates"][0]
    centroid_lon = sum(c[0] for c in coords) / len(coords)
    centroid_lat = sum(c[1] for c in coords) / len(coords)
    epsg = utm_epsg_for_lonlat(centroid_lon, centroid_lat)

    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    utm_coords = [[list(transformer.transform(lon, lat)) for lon, lat in coords]]

    utm_geometry = {"type": "Polygon", "coordinates": utm_coords}
    return utm_geometry, epsg
