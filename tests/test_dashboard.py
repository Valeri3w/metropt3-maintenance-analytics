from datetime import date, datetime, timezone

import pytest

from metropt.dashboard import (
    build_pareto_figure,
    build_timeline_figure,
    event_display_frame,
    format_hours,
    period_bounds,
)


def test_period_bounds_cover_the_selected_calendar_dates_in_utc() -> None:
    started_at, ended_at = period_bounds(date(2020, 6, 1), date(2020, 6, 7))

    assert started_at == datetime(2020, 6, 1, tzinfo=timezone.utc)
    assert ended_at == datetime(2020, 6, 8, tzinfo=timezone.utc)


def test_period_bounds_reject_reversed_dates() -> None:
    with pytest.raises(ValueError, match="end date"):
        period_bounds(date(2020, 6, 8), date(2020, 6, 1))


def test_format_hours_handles_missing_values() -> None:
    assert format_hours(52.5) == "52.50 h"
    assert format_hours(None) == "不适用"


def test_timeline_uses_annotated_intervals_without_claiming_downtime() -> None:
    figure = build_timeline_figure(
        [
            {
                "event_id": "E03",
                "failure_type": "Air Leak",
                "severity": "High Stress",
                "started_at": datetime(2020, 6, 5, 10, tzinfo=timezone.utc),
                "ended_at": datetime(2020, 6, 7, 14, 30, tzinfo=timezone.utc),
                "duration_hours": 52.5,
            }
        ]
    )

    assert len(figure.data) == 1
    assert figure.data[0].type == "bar"
    assert figure.data[0].orientation == "h"
    assert "标注异常区间" in figure.layout.title.text
    assert "E03" in figure.data[0].hovertext[0]


def test_timeline_has_an_explicit_empty_state() -> None:
    figure = build_timeline_figure([])

    assert len(figure.data) == 0
    assert "无标注故障事件" in figure.layout.title.text


def test_pareto_uses_duration_bars_and_cumulative_share_line() -> None:
    figure = build_pareto_figure(
        [
            {
                "failure_type": "Air Leak",
                "event_count": 3,
                "cumulative_hours": 83.0,
                "cumulative_share_pct": 94.86,
            },
            {
                "failure_type": "Sensor",
                "event_count": 1,
                "cumulative_hours": 4.5,
                "cumulative_share_pct": 100.0,
            },
        ]
    )

    assert len(figure.data) == 2
    assert figure.data[0].type == "bar"
    assert figure.data[1].type == "scatter"
    assert list(figure.data[1].y) == pytest.approx([94.86, 100.0])


def test_event_display_frame_replaces_missing_previous_event_values() -> None:
    frame = event_display_frame(
        [
            {
                "event_id": "E01",
                "failure_type": "Air Leak",
                "severity": "High Stress",
                "started_at": datetime(2020, 4, 18, tzinfo=timezone.utc),
                "ended_at": datetime(2020, 4, 18, 23, 59, tzinfo=timezone.utc),
                "duration_hours": 23.9833333333,
                "previous_event_id": None,
                "hours_since_previous_annotation": None,
                "gap_count": 1,
                "gap_overlap_hours": 0.095,
            }
        ]
    )

    assert frame.loc[0, "上一事件"] == "无"
    assert frame.loc[0, "距上一标注结束（h）"] == "不适用"
