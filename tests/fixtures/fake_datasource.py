from engine.datasources.base import DataSource, SAR_Scene
from tests.fixtures.mock_scenes import make_scene


class FakeDataSource(DataSource):
    """In-memory DataSource pro testy — žádná síť, žádné CDSE credentials."""

    source_name = "fake"
    typical_resolution_m = 10.0

    def __init__(self, scenes: list[SAR_Scene]):
        self._scenes = scenes

    async def get_scenes(self, geometry, date_start, date_end, polarizations=None, **kwargs) -> list[SAR_Scene]:
        return [s for s in self._scenes if date_start <= s.acquisition_date <= date_end]

    async def get_scene_count(self, geometry, date_start, date_end) -> int:
        return len(await self.get_scenes(geometry, date_start, date_end))


def make_daily_scenes(start_date: str, count: int, mean_db_fn) -> list[SAR_Scene]:
    """Vygeneruje `count` scén od start_date po 2 dnech, mean_db podle mean_db_fn(index)."""
    from datetime import datetime, timedelta

    start = datetime.strptime(start_date, "%Y-%m-%d")
    scenes = []
    for i in range(count):
        date = (start + timedelta(days=2 * i)).strftime("%Y-%m-%d")
        scenes.append(make_scene(date, mean_db_fn(i)))
    return scenes
