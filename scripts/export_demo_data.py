#!/usr/bin/env python3
"""Extract the deterministic public-demo week from audited source data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_CSV = (
    PROJECT_ROOT / "data" / "raw" / "metropt3" / "MetroPT3(AirCompressor).csv"
)
DEFAULT_FAILURE_CSV = PROJECT_ROOT / "artifacts" / "audit" / "failure_events.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "demo"

DEMO_START = datetime(2020, 6, 1, tzinfo=timezone.utc)
DEMO_END = datetime(2020, 6, 8, tzinfo=timezone.utc)
DEMO_EVENT_ID = "E03"


def filter_demo_telemetry(frame: pd.DataFrame) -> pd.DataFrame:
    timestamps = pd.to_datetime(frame["timestamp"], errors="raise", utc=True)
    mask = (timestamps >= DEMO_START) & (timestamps < DEMO_END)
    return frame.loc[mask].copy()


def filter_demo_events(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.loc[frame["internal_event_id"] == DEMO_EVENT_ID].copy()
    if result.empty:
        raise ValueError(f"Demo event {DEMO_EVENT_ID} was not found.")
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-csv", type=Path, default=DEFAULT_RAW_CSV)
    parser.add_argument("--failure-csv", type=Path, default=DEFAULT_FAILURE_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[pd.DataFrame] = []
    for frame in pd.read_csv(args.raw_csv, chunksize=args.chunk_size):
        filtered = filter_demo_telemetry(frame)
        if not filtered.empty:
            chunks.append(filtered)
    if not chunks:
        raise ValueError("No telemetry rows fell inside the demo week.")
    telemetry = pd.concat(chunks, ignore_index=True)
    telemetry_path = args.output_dir / "MetroPT3(AirCompressor)_20200601.csv"
    telemetry.to_csv(telemetry_path, index=False)

    events = filter_demo_events(pd.read_csv(args.failure_csv))
    events_path = args.output_dir / "failure_events_demo.csv"
    events.to_csv(events_path, index=False)

    manifest = {
        "demo_start_utc": DEMO_START.isoformat(),
        "demo_end_utc": DEMO_END.isoformat(),
        "event_ids": events["internal_event_id"].tolist(),
        "telemetry_rows": int(len(telemetry)),
        "telemetry_first_timestamp": str(telemetry["timestamp"].iloc[0]),
        "telemetry_last_timestamp": str(telemetry["timestamp"].iloc[-1]),
        "telemetry_sha256": sha256_file(telemetry_path),
        "failure_events_sha256": sha256_file(events_path),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
