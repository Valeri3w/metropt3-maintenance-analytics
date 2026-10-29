"""Read-only PostgreSQL access for dashboard and report queries."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row


DEFAULT_DSN = "postgresql://metropt:metropt@127.0.0.1:5434/metropt"
FLOAT_FIELDS = {
    "duration_seconds",
    "duration_hours",
    "seconds_since_previous_annotation",
    "hours_since_previous_annotation",
    "gap_overlap_hours",
    "gap_overlap_seconds",
    "observed_coverage_pct",
    "average_duration_seconds",
    "average_duration_hours",
    "longest_duration_seconds",
    "longest_duration_hours",
    "cumulative_duration_seconds",
    "cumulative_duration_hours",
    "cumulative_hours",
    "cumulative_share_pct",
    "annotated_share_of_effective_time_pct",
    "bounded_period_seconds",
    "unobserved_seconds",
    "unobserved_hours",
    "effective_monitoring_seconds",
    "effective_monitoring_hours",
    "period_effective_hours",
    "calendar_coverage_pct",
}
INT_FIELDS = {
    "event_count",
    "gap_count",
    "source_event_id",
    "source_id_occurrence",
    "sample_count",
    "source_row_number",
    "first_source_row_number",
    "last_source_row_number",
    "source_index",
    "first_source_index",
    "last_source_index",
}


def _dsn(dsn: str | None = None) -> str:
    return dsn or os.getenv("DATABASE_URL", DEFAULT_DSN)


def _convert_row(row: Mapping[str, Any]) -> dict[str, Any]:
    converted = dict(row)
    for field in FLOAT_FIELDS.intersection(converted):
        if converted[field] is not None:
            converted[field] = float(converted[field])
    for field in INT_FIELDS.intersection(converted):
        if converted[field] is not None:
            converted[field] = int(converted[field])
    return converted


def query_all(
    query: str,
    params: Sequence[Any] | None = None,
    *,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    with psycopg.connect(
        _dsn(dsn),
        connect_timeout=5,
        row_factory=dict_row,
    ) as connection:
        rows = connection.execute(query, params).fetchall()
    return [_convert_row(row) for row in rows]


def query_one(
    query: str,
    params: Sequence[Any] | None = None,
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    rows = query_all(query, params, dsn=dsn)
    if not rows:
        raise LookupError(f"Query returned no rows: {query}")
    return rows[0]


def get_database_health(*, dsn: str | None = None) -> dict[str, Any]:
    return query_one(
        """
        SELECT
            (SELECT COUNT(*) FROM telemetry) AS telemetry_rows,
            (SELECT COUNT(*) FROM failure_events) AS failure_events,
            (SELECT MIN(observed_at) FROM telemetry) AS first_observed_at,
            (SELECT MAX(observed_at) FROM telemetry) AS last_observed_at
        """,
        dsn=dsn,
    )


def get_period_quality(
    started_at: datetime,
    ended_at: datetime,
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    return query_one(
        "SELECT * FROM report_period_quality(%s, %s)",
        (started_at, ended_at),
        dsn=dsn,
    )


def get_period_metrics(
    started_at: datetime,
    ended_at: datetime,
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    return query_one(
        "SELECT * FROM report_period_metrics(%s, %s)",
        (started_at, ended_at),
        dsn=dsn,
    )


def get_period_pareto(
    started_at: datetime,
    ended_at: datetime,
    *,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    return query_all(
        "SELECT * FROM report_failure_pareto(%s, %s)",
        (started_at, ended_at),
        dsn=dsn,
    )


def get_failure_events(
    started_at: datetime,
    ended_at: datetime,
    *,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    return query_all(
        "SELECT * FROM report_failure_events(%s, %s)",
        (started_at, ended_at),
        dsn=dsn,
    )


def get_event_trace(
    event_id: str,
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    return query_one(
        "SELECT * FROM failure_event_trace(%s)",
        (event_id,),
        dsn=dsn,
    )


def get_event_samples(
    event_id: str,
    *,
    sample_limit: int = 8,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    return query_all(
        "SELECT * FROM failure_event_samples(%s, %s)",
        (event_id, sample_limit),
        dsn=dsn,
    )


def get_event_gaps(
    event_id: str,
    *,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    return query_all(
        """
        SELECT
            event_id,
            gap_started_at,
            gap_ended_at,
            unobserved_hours,
            overlap_started_at,
            overlap_ended_at,
            overlap_seconds
        FROM failure_gap_overlap
        WHERE event_id = %s
        ORDER BY gap_started_at
        """,
        (event_id,),
        dsn=dsn,
    )


def get_period_gaps(
    started_at: datetime,
    ended_at: datetime,
    *,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    return query_all(
        """
        SELECT
            gap_started_at,
            gap_ended_at,
            unobserved_hours,
            GREATEST(%s, gap_started_at) AS overlap_started_at,
            LEAST(%s, gap_ended_at) AS overlap_ended_at,
            EXTRACT(
                EPOCH FROM (
                    LEAST(%s, gap_ended_at)
                    - GREATEST(%s, gap_started_at)
                )
            ) AS overlap_seconds
        FROM telemetry_gaps
        WHERE gap_started_at < %s
          AND gap_ended_at > %s
        ORDER BY gap_started_at
        """,
        (
            started_at,
            ended_at,
            ended_at,
            started_at,
            ended_at,
            started_at,
        ),
        dsn=dsn,
    )
