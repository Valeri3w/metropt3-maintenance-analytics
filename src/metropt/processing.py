"""Small, testable data-processing functions shared by scripts and the app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping

import pandas as pd


@dataclass(frozen=True)
class NormalizedTelemetry:
    frame: pd.DataFrame
    duplicate_count: int
    out_of_order_count: int


def normalize_telemetry_timestamps(
    frame: pd.DataFrame,
    timestamp_column: str = "timestamp",
) -> NormalizedTelemetry:
    """Parse source timestamps as UTC, stable-sort them, and keep last duplicates."""
    if timestamp_column not in frame.columns:
        raise ValueError(f"Missing timestamp column: {timestamp_column}")
    if frame.empty:
        result = frame.copy()
        result["observed_at_utc"] = pd.Series(dtype="datetime64[ns, UTC]")
        return NormalizedTelemetry(result, 0, 0)

    parsed = pd.to_datetime(
        frame[timestamp_column],
        errors="coerce",
        utc=True,
    )
    invalid_count = int(parsed.isna().sum())
    if invalid_count:
        raise ValueError(
            f"{timestamp_column} contains {invalid_count} unparseable value(s)."
        )

    out_of_order_count = int((parsed.diff().dt.total_seconds() < 0).sum())
    normalized = frame.copy()
    normalized["observed_at_utc"] = parsed
    normalized["_source_order"] = range(len(normalized))
    normalized = normalized.sort_values(
        ["observed_at_utc", "_source_order"],
        kind="mergesort",
    )
    duplicate_mask = normalized.duplicated("observed_at_utc", keep="last")
    duplicate_count = int(duplicate_mask.sum())
    normalized = normalized.loc[~duplicate_mask].drop(columns="_source_order")
    return NormalizedTelemetry(
        normalized.reset_index(drop=True),
        duplicate_count,
        out_of_order_count,
    )


def counter_increments(values: pd.Series) -> pd.Series:
    """Return non-negative counter steps; resets and invalid steps become null."""
    numeric = pd.to_numeric(values, errors="raise")
    differences = numeric.diff()
    return differences.where(differences >= 0)


def failure_duration_hours(started_at: datetime, ended_at: datetime) -> float:
    """Calculate an annotated interval as end minus start in hours."""
    if started_at.tzinfo is None or ended_at.tzinfo is None:
        raise ValueError("Failure timestamps must include a timezone.")
    if ended_at <= started_at:
        raise ValueError("Failure end must be later than failure start.")
    return (ended_at - started_at).total_seconds() / 3600.0


def pareto_by_failure_type(
    records: Iterable[Mapping[str, Any]],
) -> pd.DataFrame:
    """Aggregate annotated duration by type and sort descending."""
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "failure_type",
                "event_count",
                "cumulative_seconds",
                "cumulative_hours",
                "contribution_share_pct",
                "cumulative_share_pct",
            ]
        )
    required = {"failure_type", "duration_seconds"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing Pareto fields: {sorted(missing)}")
    frame["duration_seconds"] = pd.to_numeric(
        frame["duration_seconds"],
        errors="raise",
    )
    grouped = (
        frame.groupby("failure_type", as_index=False)
        .agg(
            event_count=("failure_type", "size"),
            cumulative_seconds=("duration_seconds", "sum"),
        )
        .sort_values(
            ["cumulative_seconds", "failure_type"],
            ascending=[False, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    total_seconds = float(grouped["cumulative_seconds"].sum())
    grouped["cumulative_hours"] = grouped["cumulative_seconds"] / 3600.0
    grouped["contribution_share_pct"] = (
        100.0 * grouped["cumulative_seconds"] / total_seconds
        if total_seconds
        else 0.0
    )
    grouped["cumulative_share_pct"] = grouped[
        "contribution_share_pct"
    ].cumsum()
    return grouped


def gap_overlap_seconds(
    event_started_at: datetime,
    event_ended_at: datetime,
    gap_started_at: datetime,
    gap_ended_at: datetime,
) -> int:
    """Return the overlap between an annotated event and an observation gap."""
    for value in (
        event_started_at,
        event_ended_at,
        gap_started_at,
        gap_ended_at,
    ):
        if value.tzinfo is None:
            raise ValueError("Interval timestamps must include a timezone.")
    if event_ended_at <= event_started_at:
        raise ValueError("Event end must be later than event start.")
    if gap_ended_at <= gap_started_at:
        raise ValueError("Gap end must be later than gap start.")
    overlap_start = max(event_started_at, gap_started_at)
    overlap_end = min(event_ended_at, gap_ended_at)
    return max(0, int((overlap_end - overlap_start).total_seconds()))


def week_bounds(anchor_date: date) -> tuple[datetime, datetime]:
    """Return the Monday-to-next-Monday UTC bounds containing an anchor date."""
    monday = anchor_date - timedelta(days=anchor_date.weekday())
    started_at = datetime.combine(monday, time.min, tzinfo=timezone.utc)
    return started_at, started_at + timedelta(days=7)
