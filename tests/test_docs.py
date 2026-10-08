"""The hours-saved sheet must add up, and it must say it is an estimate."""

import csv

from workflow_pack.config import REPO_ROOT

SHEET = REPO_ROOT / "docs" / "hours_saved.csv"


def test_hours_saved_arithmetic():
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8")))
    items, total = rows[:-1], rows[-1]
    for r in items:
        volume = float(r["weekly_volume_ASSUMED"])
        assert round(volume * float(r["manual_minutes_per_item_ASSUMED"]) / 60, 2) == float(r["manual_hours_per_week"])
        assert round(volume * float(r["after_minutes_per_item_ASSUMED"]) / 60, 2) == float(r["after_hours_per_week"])
        assert round(float(r["manual_hours_per_week"]) - float(r["after_hours_per_week"]), 2) == float(r["hours_saved_per_week"])
    for column in ("manual_hours_per_week", "after_hours_per_week", "hours_saved_per_week"):
        assert round(sum(float(r[column]) for r in items), 2) == float(total[column])
    assert "ESTIMATE" in total["workflow"] and "not measured" in total["assumption_notes"]
