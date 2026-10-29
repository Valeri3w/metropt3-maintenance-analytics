#!/usr/bin/env python3
"""Load and validate only the committed public-demo week."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from psycopg import Connection

from scripts.load_db import (
    ASSET_ID,
    DEFAULT_AUDIT_REPORT,
    DEFAULT_METRICS_SQL,
    DEFAULT_SCHEMA_SQL,
    load_failure_events,
    load_metrics,
    load_schema,
    load_telemetry,
    query_one,
    upsert_asset,
    validate_metric_views,
    wait_for_database,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DIR = PROJECT_ROOT / "data" / "demo"


def validate_demo_load(
    connection: Connection[Any],
    expected_rows: int,
) -> dict[str, Any]:
    count, minimum, maximum = query_one(
        connection,
        """
        SELECT COUNT(*), MIN(observed_at), MAX(observed_at)
        FROM telemetry
        WHERE asset_id = %s
        """,
        (ASSET_ID,),
    )
    event_ids = [
        row[0]
        for row in connection.execute(
            "SELECT event_id FROM failure_events ORDER BY event_id"
        ).fetchall()
    ]
    if count != expected_rows:
        raise RuntimeError(f"Loaded {count} demo rows, expected {expected_rows}.")
    if event_ids != ["E03"]:
        raise RuntimeError(f"Expected only E03, found {event_ids}.")
    return {
        "telemetry_rows": count,
        "first_observed_at": minimum.isoformat(),
        "last_observed_at": maximum.isoformat(),
        "event_ids": event_ids,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    parser.add_argument("--schema-sql", type=Path, default=DEFAULT_SCHEMA_SQL)
    parser.add_argument("--metrics-sql", type=Path, default=DEFAULT_METRICS_SQL)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument(
        "--dsn",
        default=os.getenv("DATABASE_URL"),
        help="Use only a dedicated demo database.",
    )
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("--confirm-reset", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dsn:
        raise ValueError("Provide --dsn or set DATABASE_URL.")
    if not args.confirm_reset:
        raise ValueError(
            "Refusing to truncate tables without --confirm-reset. "
            "Use only a dedicated demo database."
        )

    manifest = json.loads(
        (args.demo_dir / "manifest.json").read_text(encoding="utf-8")
    )
    expected_rows = int(manifest["telemetry_rows"])
    raw_csv = args.demo_dir / "MetroPT3(AirCompressor)_20200601.csv"
    failure_csv = args.demo_dir / "failure_events_demo.csv"

    connection = wait_for_database(args.dsn, args.wait_seconds)
    try:
        with connection.transaction():
            load_schema(connection, args.schema_sql)
            upsert_asset(connection, args.audit_report)
            load_failure_events(connection, failure_csv, expected_events=1)
            load_telemetry(connection, raw_csv, args.chunk_size)
            load_metrics(connection, args.metrics_sql)
            result = validate_demo_load(connection, expected_rows)
            result["metric_views"] = validate_metric_views(connection)
        connection.commit()
    finally:
        connection.close()

    print(json.dumps({"status": "ok", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
