from engine.datasources.sentinel2_cdse import NDVISample


class FakeNdviSource:
    """In-memory NDVI zdroj pro testy — žádná síť, žádné CDSE credentials."""

    def __init__(self, samples: list[NDVISample]):
        self._samples = samples

    async def get_ndvi_series(self, geometry, date_start, date_end) -> list[NDVISample]:
        return [s for s in self._samples if date_start <= s.date <= date_end]
