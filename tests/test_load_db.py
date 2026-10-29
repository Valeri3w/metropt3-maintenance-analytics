import inspect
import os
from pathlib import Path

import psycopg
import pytest

from scripts.load_db import (
    DEFAULT_DSN,
    database_has_complete_load,
    load_failure_events,
)


DSN = os.getenv("DATABASE_URL", DEFAULT_DSN)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_data_quality_summary_is_created_before_dependent_overall_metrics() -> None:
    metrics_sql = (PROJECT_ROOT / "sql" / "metrics.sql").read_text(
        encoding="utf-8"
    )

    quality_view_position = metrics_sql.index(
        "CREATE OR REPLACE VIEW data_quality_summary AS"
    )
    overall_metrics_position = metrics_sql.index(
        "CREATE OR REPLACE VIEW failure_overall_metrics AS"
    )

    assert quality_view_position < overall_metrics_position


def test_complete_load_detection_uses_expected_telemetry_and_event_counts() -> None:
    try:
        connection = psycopg.connect(DSN, connect_timeout=5)
    except Exception as exc:
        pytest.skip(f"PostgreSQL integration database unavailable: {exc}")

    try:
        assert database_has_complete_load(connection, 1_516_948)
        assert not database_has_complete_load(connection, 1_516_949)
    finally:
        connection.close()


def test_load_failure_events_exposes_expected_event_count() -> None:
    signature = inspect.signature(load_failure_events)

    assert signature.parameters["expected_events"].default == 4
