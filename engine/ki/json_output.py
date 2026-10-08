"""JSON výstup pro strojové zpracování (zadání kap. 2)."""

import json
from dataclasses import asdict
from pathlib import Path

from engine.ki.models import ObjectReport


def write_json(reports: list[ObjectReport], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "objekty": [
            {
                "id": r.obj.id,
                "name": r.obj.name,
                "lon": r.obj.lon,
                "lat": r.obj.lat,
                "source_note": r.obj.source_note,
                "generated_at": r.generated_at,
                "zjisteni": [asdict(f) for f in r.findings],
            }
            for r in reports
        ]
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
