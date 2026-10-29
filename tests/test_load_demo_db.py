import json
import subprocess
import sys
from pathlib import Path

from scripts.load_demo_db import DEFAULT_DEMO_DIR


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_demo_manifest_identifies_one_complete_week_and_e03() -> None:
    manifest = json.loads(
        (DEFAULT_DEMO_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["demo_start_utc"] == "2020-06-01T00:00:00+00:00"
    assert manifest["demo_end_utc"] == "2020-06-08T00:00:00+00:00"
    assert manifest["event_ids"] == ["E03"]
    assert manifest["telemetry_rows"] > 0


def test_demo_loader_supports_direct_script_execution() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/load_demo_db.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--confirm-reset" in result.stdout
