from engine.datasources.base import SAR_Scene, ROIStats

MOCK_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [15.590, 49.395],
        [15.598, 49.395],
        [15.598, 49.402],
        [15.590, 49.402],
        [15.590, 49.395],
    ]],
}


def make_scene(date: str, mean_db: float, valid_pixel_ratio: float = 1.0) -> SAR_Scene:
    return SAR_Scene(
        acquisition_date=date,
        polarization="VV",
        orbit_direction="ASCENDING",
        instrument_mode="IW",
        roi_stats=ROIStats(
            mean_db=mean_db,
            p10_db=mean_db - 2.0,
            p90_db=mean_db + 2.0,
            stddev_db=1.5,
            valid_pixel_ratio=valid_pixel_ratio,
        ),
        spatial_resolution_m=10.0,
        crs="EPSG:4326",
        bbox=(15.590, 49.395, 15.598, 49.402),
        source_id=f"cdse/sentinel-1-grd/{date}",
        metadata={},
    )


def make_dry_scene(date: str = "2026-07-15") -> SAR_Scene:
    """Extrémně suchá půda, Ïƒâ° â‰ˆ -20 dB."""
    return make_scene(date, -20.0)


def make_wet_scene(date: str = "2026-04-10") -> SAR_Scene:
    """Půda po vydatném dešti, Ïƒâ° â‰ˆ -10 dB."""
    return make_scene(date, -10.0)


def make_low_coverage_scene(date: str = "2026-05-01") -> SAR_Scene:
    """Scéna s nedostatečným pokrytím AOI — musí být RadiometricAnalyzer zahozena."""
    return make_scene(date, -15.0, valid_pixel_ratio=0.1)
