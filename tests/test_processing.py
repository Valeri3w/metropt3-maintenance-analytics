from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from metropt.processing import (
    counter_increments,
    failure_duration_hours,
    gap_overlap_seconds,
    normalize_telemetry_timestamps,
    pareto_by_failure_type,
)


def test_normalize_timestamps_marks_naive_input_as_utc_and_sorts() -> None:
    source = pd.DataFrame(
        {
            "timestamp": [
                "2020-02-01 00:00:20",
                "2020-02-01 00:00:00",
                "2020-02-01 00:00:10",
            ],
            "value": [3, 1, 2],
        }
    )

    result = normalize_telemetry_timestamps(source)

    assert result.frame["observed_at_utc"].dt.tz is not None
    assert result.frame["value"].tolist() == [1, 2, 3]
    assert result.out_of_order_count == 1
    assert result.duplicate_count == 0


def test_normalize_timestamps_keeps_last_duplicate_record() -> None:
    source = pd.DataFrame(
        {
            "timestamp": [
                "2020-02-01 00:00:00",
                "2020-02-01 00:00:10",
                "2020-02-01 00:00:00",
            ],
            "value": [10, 20, 99],
        }
    )

    result = normalize_telemetry_timestamps(source)

    assert result.duplicate_count == 1
    assert result.frame["value"].tolist() == [99, 20]


def test_normalize_timestamps_rejects_unparseable_values() -> None:
    source = pd.DataFrame({"timestamp": ["not-a-time"]})

    with pytest.raises(ValueError, match="timestamp"):
        normalize_telemetry_timestamps(source)


def test_counter_increments_exclude_negative_reset_steps() -> None:
    values = pd.Series([100, 110, 125, 5, 15])

    increments = counter_increments(values)

    assert increments.iloc[1] == 10
    assert increments.iloc[2] == 15
    assert pd.isna(increments.iloc[3])
    assert increments.iloc[4] == 10


def test_failure_duration_uses_end_minus_start() -> None:
    start = datetime(2020, 4, 18, tzinfo=timezone.utc)
    end = start + timedelta(hours=23, minutes=59)

    assert failure_duration_hours(start, end) == pytest.approx(23.9833333333)


def test_failure_duration_rejects_non_positive_interval() -> None:
    start = datetime(2020, 4, 18, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="later"):
        failure_duration_hours(start, start)


def test_pareto_orders_failure_types_by_cumulative_duration() -> None:
    records = [
        {"failure_type": "Air Leak", "duration_seconds": 3600},
        {"failure_type": "Air Leak", "duration_seconds": 7200},
        {"failure_type": "Sensor", "duration_seconds": 1800},
    ]

    pareto = pareto_by_failure_type(records)

    assert pareto["failure_type"].tolist() == ["Air Leak", "Sensor"]
    assert pareto["cumulative_hours"].tolist() == pytest.approx([3.0, 0.5])
    assert pareto["cumulative_share_pct"].iloc[-1] == pytest.approx(100.0)


def test_gap_overlap_uses_only_intersection() -> None:
    event_start = datetime(2020, 6, 5, 10, tzinfo=timezone.utc)
    event_end = event_start + timedelta(hours=4)
    gap_start = event_start + timedelta(hours=1)
    gap_end = event_start + timedelta(hours=2, minutes=30)

    assert gap_overlap_seconds(event_start, event_end, gap_start, gap_end) == 5400


def test_gap_overlap_returns_zero_for_disjoint_intervals() -> None:
    event_start = datetime(2020, 6, 5, 10, tzinfo=timezone.utc)
    event_end = event_start + timedelta(hours=1)
    gap_start = event_end + timedelta(hours=1)
    gap_end = gap_start + timedelta(hours=1)

    assert gap_overlap_seconds(event_start, event_end, gap_start, gap_end) == 0
