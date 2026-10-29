import json

from scripts.load_demo_db import DEFAULT_DEMO_DIR


def test_demo_manifest_identifies_one_complete_week_and_e03() -> None:
    manifest = json.loads(
        (DEFAULT_DEMO_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["demo_start_utc"] == "2020-06-01T00:00:00+00:00"
    assert manifest["demo_end_utc"] == "2020-06-08T00:00:00+00:00"
    assert manifest["event_ids"] == ["E03"]
    assert manifest["telemetry_rows"] > 0
