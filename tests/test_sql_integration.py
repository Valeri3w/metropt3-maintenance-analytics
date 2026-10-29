import os
from datetime import datetime, timezone

import pytest

from metropt.data_access import (
    DEFAULT_DSN,
    get_period_metrics,
    get_period_pareto,
    get_period_quality,
)


DSN = os.getenv("DATABASE_URL", DEFAULT_DSN)


def test_sql_metrics_reproduce_audited_four_event_baseline() -> None:
    try:
        metrics = get_period_metrics(
            datetime(2020, 2, 1, tzinfo=timezone.utc),
            datetime(2020, 9, 2, tzinfo=timezone.utc),
            dsn=DSN,
        )
    except Exception as exc:
        pytest.skip(f"PostgreSQL integration database unavailable: {exc}")

    assert metrics["event_count"] == 4
    assert metrics["average_duration_hours"] == pytest.approx(21.8708333333)
    assert metrics["longest_duration_hours"] == pytest.approx(52.5)
    assert metrics["longest_event_id"] == "E03"
    assert metrics["cumulative_duration_hours"] == pytest.approx(87.4833333333)
    assert metrics["annotated_share_of_effective_time_pct"] == pytest.approx(
        2.0793, abs=0.0002
    )


def test_sql_pareto_and_period_quality_are_derived_from_database() -> None:
    try:
        pareto = get_period_pareto(
            datetime(2020, 6, 1, tzinfo=timezone.utc),
            datetime(2020, 6, 8, tzinfo=timezone.utc),
            dsn=DSN,
        )
        quality = get_period_quality(
            datetime(2020, 6, 1, tzinfo=timezone.utc),
            datetime(2020, 6, 8, tzinfo=timezone.utc),
            dsn=DSN,
        )
    except Exception as exc:
        pytest.skip(f"PostgreSQL integration database unavailable: {exc}")

    assert pareto == [
        {
            "failure_type": "Air Leak",
            "event_count": 1,
            "cumulative_hours": pytest.approx(52.5),
            "cumulative_share_pct": pytest.approx(100.0),
        }
    ]
    assert quality["gap_count"] == 10
    assert quality["unobserved_hours"] == pytest.approx(26.7622222222)
    assert quality["calendar_coverage_pct"] == pytest.approx(84.0701058201)
