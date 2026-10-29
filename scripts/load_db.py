#!/usr/bin/env python3
"""Load audited MetroPT-3 evidence into PostgreSQL in reproducible batches."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg import Connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_CSV = (
    PROJECT_ROOT / "data" / "raw" / "metropt3" / "MetroPT3(AirCompressor).csv"
)
DEFAULT_FAILURE_CSV = PROJECT_ROOT / "artifacts" / "audit" / "failure_events.csv"
DEFAULT_AUDIT_REPORT = PROJECT_ROOT / "artifacts" / "audit" / "audit_report.json"
DEFAULT_SCHEMA_SQL = PROJECT_ROOT / "sql" / "schema.sql"
DEFAULT_METRICS_SQL = PROJECT_ROOT / "sql" / "metrics.sql"
DEFAULT_DSN = "postgresql://metropt:metropt@127.0.0.1:5434/metropt"

DATASET_NAME = "MetroPT-3"
DATASET_DOI = "10.24432/C5VW3R"
ASSET_ID = "metropt3-air-compressor-01"
ASSET_NAME = "MetroPT-3 air compressor"
ASSET_TYPE = "Air compressor"
SOURCE_DOCUMENT = "Data Description_Metro.pdf"

SOURCE_COLUMNS = [
    "Unnamed: 0",
    "timestamp",
    "TP2",
    "TP3",
    "H1",
    "DV_pressure",
    "Reservoirs",
    "Oil_temperature",
    "Motor_current",
    "COMP",
    "DV_eletric",
    "Towers",
    "MPG",
    "LPS",
    "Pressure_switch",
    "Oil_level",
    "Caudal_impulses",
]

ANALOG_COLUMNS = {
    "TP2": "tp2_bar",
    "TP3": "tp3_bar",
    "H1": "h1_bar",
    "DV_pressure": "dv_pressure_bar",
    "Reservoirs": "reservoirs_bar",
    "Oil_temperature": "oil_temperature_c",
    "Motor_current": "motor_current_a",
}

DIGITAL_COLUMNS = {
    "COMP": "comp",
    "DV_eletric": "dv_electric",
    "Towers": "towers",
    "MPG": "mpg",
    "LPS": "lps",
    "Pressure_switch": "pressure_switch",
    "Oil_level": "oil_level",
    "Caudal_impulses": "caudal_impulses",
}

TELEMETRY_COLUMNS = [
    "asset_id",
    "observed_at",
    "source_row_number",
    "source_index",
    *ANALOG_COLUMNS.values(),
    *DIGITAL_COLUMNS.values(),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-csv", type=Path, default=DEFAULT_RAW_CSV)
    parser.add_argument("--failure-csv", type=Path, default=DEFAULT_FAILURE_CSV)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--schema-sql", type=Path, default=DEFAULT_SCHEMA_SQL)
    parser.add_argument("--metrics-sql", type=Path, default=DEFAULT_METRICS_SQL)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", DEFAULT_DSN))
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("--apply-schema", action="store_true")
    parser.add_argument("--apply-metrics", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def wait_for_database(dsn: str, wait_seconds: int) -> Connection[Any]:
    deadline = time.monotonic() + wait_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connection = psycopg.connect(dsn, connect_timeout=5)
            connection.execute("SELECT 1")
            return connection
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(
        f"Could not connect to PostgreSQL within {wait_seconds} seconds: "
        f"{last_error}"
    )


def read_expected_rows(audit_report: Path) -> int | None:
    if not audit_report.exists():
        return None
    report = json.loads(audit_report.read_text(encoding="utf-8"))
    return int(report["dataset"]["rows"])


def load_schema(connection: Connection[Any], schema_sql: Path) -> None:
    connection.execute(schema_sql.read_text(encoding="utf-8"))


def load_metrics(connection: Connection[Any], metrics_sql: Path) -> None:
    connection.execute(metrics_sql.read_text(encoding="utf-8"))


def validate_metric_views(connection: Connection[Any]) -> int:
    expected_views = (
        "sensor_field_catalog",
        "telemetry_gaps",
        "failure_event_metrics",
        "failure_type_pareto",
        "failure_overall_metrics",
        "failure_gap_overlap",
        "failure_event_gap_summary",
        "data_quality_summary",
    )
    view_count = query_one(
        connection,
        """
        SELECT COUNT(*)
        FROM information_schema.views
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        """,
        (list(expected_views),),
    )[0]
    if view_count != len(expected_views):
        raise RuntimeError(
            f"Found {view_count} of {len(expected_views)} expected metric views."
        )
    return view_count


def upsert_asset(
    connection: Connection[Any], audit_report: Path
) -> None:
    archive_sha256 = None
    if audit_report.exists():
        report = json.loads(audit_report.read_text(encoding="utf-8"))
        archive_sha256 = (
            report.get("source", {}).get("archive", {}).get("sha256")
        )

    connection.execute(
        """
        INSERT INTO assets (
            asset_id,
            asset_name,
            asset_type,
            dataset_name,
            dataset_doi,
            source_archive_sha256,
            timestamp_interpretation,
            nominal_interval_seconds,
            gap_threshold_seconds,
            notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (asset_id) DO UPDATE SET
            asset_name = EXCLUDED.asset_name,
            asset_type = EXCLUDED.asset_type,
            dataset_name = EXCLUDED.dataset_name,
            dataset_doi = EXCLUDED.dataset_doi,
            source_archive_sha256 = EXCLUDED.source_archive_sha256,
            timestamp_interpretation = EXCLUDED.timestamp_interpretation,
            nominal_interval_seconds = EXCLUDED.nominal_interval_seconds,
            gap_threshold_seconds = EXCLUDED.gap_threshold_seconds,
            notes = EXCLUDED.notes
        """,
        (
            ASSET_ID,
            ASSET_NAME,
            ASSET_TYPE,
            DATASET_NAME,
            DATASET_DOI,
            archive_sha256,
            "Naive source timestamps are interpreted as UTC by convention.",
            10,
            30,
            "Single-asset dataset. No production or financial metrics are inferred.",
        ),
    )


def load_failure_events(connection: Connection[Any], failure_csv: Path) -> int:
    with failure_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 4:
        raise ValueError(f"Expected four failure events, found {len(rows)}.")

    source_id_seen: Counter[int] = Counter()
    connection.execute("TRUNCATE TABLE failure_events")
    for row in rows:
        remark = row["report_text"] or None
        source_event_id = int(row["source_id"])
        source_id_seen[source_event_id] += 1
        connection.execute(
            """
            INSERT INTO failure_events (
                event_id,
                asset_id,
                source_event_id,
                source_id_occurrence,
                source_failure_type,
                failure_type,
                severity,
                started_at,
                ended_at,
                maintenance_remark,
                source_text,
                source_document
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["internal_event_id"],
                ASSET_ID,
                source_event_id,
                source_id_seen[source_event_id],
                "Air leak",
                row["failure_type"],
                row["severity"],
                row["start_utc"],
                row["end_utc"],
                remark,
                remark,
                SOURCE_DOCUMENT,
            ),
        )
    return len(rows)


def validate_source_header(frame: pd.DataFrame) -> None:
    columns = list(frame.columns)
    if columns != SOURCE_COLUMNS:
        raise ValueError(
            "Raw CSV header does not match the audited schema.\n"
            f"Expected: {SOURCE_COLUMNS}\n"
            f"Found:    {columns}"
        )


def prepare_copy_chunk(
    frame: pd.DataFrame, first_source_row_number: int
) -> io.StringIO:
    observed_at = pd.to_datetime(
        frame["timestamp"],
        format="%Y-%m-%d %H:%M:%S",
        errors="raise",
        utc=True,
    )
    if observed_at.isna().any():
        raise ValueError("Timestamp parsing produced null values.")

    output = pd.DataFrame(
        {
            "asset_id": ASSET_ID,
            "observed_at": observed_at,
            "source_row_number": range(
                first_source_row_number,
                first_source_row_number + len(frame),
            ),
            "source_index": frame["Unnamed: 0"].astype("int64"),
        }
    )
    for source_column, db_column in ANALOG_COLUMNS.items():
        output[db_column] = pd.to_numeric(
            frame[source_column], errors="raise"
        )
    for source_column, db_column in DIGITAL_COLUMNS.items():
        values = pd.to_numeric(frame[source_column], errors="raise")
        if not values.isin([0, 1]).all():
            raise ValueError(f"{source_column} contains values outside 0/1.")
        output[db_column] = values.astype("int8").astype("bool")

    buffer = io.StringIO()
    output.to_csv(
        buffer,
        index=False,
        header=False,
        date_format="%Y-%m-%d %H:%M:%S%z",
        na_rep="",
    )
    buffer.seek(0)
    return buffer


def load_telemetry(
    connection: Connection[Any],
    raw_csv: Path,
    chunk_size: int,
) -> int:
    header = pd.read_csv(raw_csv, nrows=0)
    validate_source_header(header)
    connection.execute("TRUNCATE TABLE telemetry")

    copy_sql = (
        "COPY telemetry ("
        + ", ".join(TELEMETRY_COLUMNS)
        + ") FROM STDIN WITH (FORMAT CSV, NULL '')"
    )
    loaded_rows = 0
    with connection.cursor() as cursor:
        with cursor.copy(copy_sql) as copy:
            for frame in pd.read_csv(raw_csv, chunksize=chunk_size):
                validate_source_header(frame)
                buffer = prepare_copy_chunk(frame, loaded_rows + 1)
                copy.write(buffer.getvalue())
                loaded_rows += len(frame)
                print(
                    f"Loaded {loaded_rows:,} telemetry rows",
                    file=sys.stderr,
                )
    return loaded_rows


def query_one(
    connection: Connection[Any],
    query: str,
    params: tuple[Any, ...] | None = None,
) -> tuple[Any, ...]:
    result = connection.execute(query, params).fetchone()
    if result is None:
        raise RuntimeError(f"Validation query returned no rows: {query}")
    return result


def database_has_complete_load(
    connection: Connection[Any],
    expected_rows: int | None,
) -> bool:
    if expected_rows is None:
        return False
    telemetry_count, event_count = query_one(
        connection,
        """
        SELECT
            (SELECT COUNT(*) FROM telemetry),
            (SELECT COUNT(*) FROM failure_events)
        """,
    )
    return telemetry_count == expected_rows and event_count == 4


def validate_load(
    connection: Connection[Any],
    expected_rows: int | None,
) -> dict[str, Any]:
    count, minimum, maximum, distinct_indices = query_one(
        connection,
        """
        SELECT
            COUNT(*),
            MIN(observed_at),
            MAX(observed_at),
            COUNT(DISTINCT source_index)
        FROM telemetry
        WHERE asset_id = %s
        """,
        (ASSET_ID,),
    )
    event_count = query_one(
        connection,
        "SELECT COUNT(*) FROM failure_events",
    )[0]

    if expected_rows is not None and count != expected_rows:
        raise RuntimeError(
            f"Loaded {count:,} telemetry rows, expected {expected_rows:,}."
        )
    if distinct_indices != count:
        raise RuntimeError("source_index is not unique after loading.")
    if event_count != 4:
        raise RuntimeError(f"Loaded {event_count} failure events, expected 4.")

    return {
        "telemetry_rows": count,
        "distinct_source_indices": distinct_indices,
        "first_observed_at": minimum.isoformat(),
        "last_observed_at": maximum.isoformat(),
        "failure_events": event_count,
    }


def main() -> int:
    args = parse_args()
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be positive.")

    raw_csv = args.raw_csv.resolve()
    failure_csv = args.failure_csv.resolve()
    audit_report = args.audit_report.resolve()
    for path in (raw_csv, failure_csv):
        if not path.exists():
            raise FileNotFoundError(path)

    expected_rows = read_expected_rows(audit_report)
    connection = wait_for_database(args.dsn, args.wait_seconds)
    try:
        with connection.transaction():
            if args.apply_schema:
                load_schema(connection, args.schema_sql.resolve())
            upsert_asset(connection, audit_report)
            skipped_existing = (
                args.skip_existing
                and database_has_complete_load(connection, expected_rows)
            )
            if skipped_existing:
                event_rows = 0
                telemetry_rows = 0
            else:
                event_rows = load_failure_events(connection, failure_csv)
                telemetry_rows = load_telemetry(
                    connection, raw_csv, args.chunk_size
                )
            if args.apply_metrics:
                load_metrics(connection, args.metrics_sql.resolve())
            validation = validate_load(connection, expected_rows)
            validation["failure_event_rows_inserted"] = event_rows
            validation["telemetry_rows_inserted"] = telemetry_rows
            validation["skipped_existing"] = skipped_existing
            if args.apply_metrics:
                validation["metric_views"] = validate_metric_views(connection)
        connection.commit()
    finally:
        connection.close()

    # Reconnect after commit so the reported counts prove persisted state.
    connection = wait_for_database(args.dsn, args.wait_seconds)
    try:
        persisted = validate_load(connection, expected_rows)
        if args.apply_metrics:
            persisted["metric_views"] = validate_metric_views(connection)
    finally:
        connection.close()

    validation["persisted_validation"] = persisted
    print(json.dumps({"status": "ok", **validation}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Database load failed: {exc}", file=sys.stderr)
        raise
