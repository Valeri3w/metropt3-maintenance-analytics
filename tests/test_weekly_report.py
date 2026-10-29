from datetime import datetime, timezone

from metropt.weekly_report import (
    build_weekly_report,
    render_weekly_html,
    render_weekly_markdown,
)


def sample_report():
    start = datetime(2020, 6, 1, tzinfo=timezone.utc)
    end = datetime(2020, 6, 8, tzinfo=timezone.utc)
    events = [
        {
            "event_id": "E03",
            "failure_type": "Air Leak",
            "severity": "High Stress",
            "started_at": datetime(2020, 6, 5, 10, tzinfo=timezone.utc),
            "ended_at": datetime(2020, 6, 7, 14, 30, tzinfo=timezone.utc),
            "duration_hours": 52.5,
            "previous_event_id": "E02",
            "hours_since_previous_annotation": 148.0,
            "gap_count": 3,
            "gap_overlap_hours": 4.8205555556,
            "observed_coverage_pct": 90.8179,
            "maintenance_remark": "Maintenance on 8Jun at 16:00",
        }
    ]
    summary = {
        "event_count": 1,
        "average_duration_hours": 52.5,
        "longest_duration_hours": 52.5,
        "longest_event_id": "E03",
        "cumulative_duration_hours": 52.5,
        "annotated_share_of_effective_time_pct": 1.2478,
        "period_effective_hours": 166.1794,
    }
    quality = {
        "gap_count": 3,
        "unobserved_hours": 4.8205555556,
        "calendar_coverage_pct": 97.18,
        "global_gap_count": 331,
        "global_unobserved_hours": 908.5980555556,
    }
    return build_weekly_report(start, end, events, summary, quality)


def test_weekly_report_contains_core_decisions_and_traceability() -> None:
    markdown = render_weekly_markdown(sample_report())

    assert "# MetroPT-3 维护周报" in markdown
    assert "E03" in markdown
    assert "52.5000" in markdown
    assert "148.0000" in markdown
    assert "Air Leak" in markdown
    assert "4.8206" in markdown
    assert "有效监测时长" in markdown
    assert "UTC" in markdown
    assert "0.1 Hz" in markdown
    assert "Known Issues" in markdown


def test_weekly_report_html_is_self_contained_and_escaped() -> None:
    report = sample_report()
    report.events[0]["maintenance_remark"] = "<script>alert(1)</script>"

    html = render_weekly_html(report)

    assert html.startswith("<!doctype html>")
    assert "<style>" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "<code>Caudal_impulses</code>" in html
    assert "`Caudal_impulses`" not in html


def test_weekly_report_explicitly_handles_an_empty_week() -> None:
    start = datetime(2020, 8, 10, tzinfo=timezone.utc)
    end = datetime(2020, 8, 17, tzinfo=timezone.utc)
    report = build_weekly_report(
        start,
        end,
        [],
        {
            "event_count": 0,
            "average_duration_hours": None,
            "longest_duration_hours": None,
            "longest_event_id": None,
            "cumulative_duration_hours": 0,
            "annotated_share_of_effective_time_pct": 0,
            "period_effective_hours": 168,
        },
        {
            "gap_count": 0,
            "unobserved_hours": 0,
            "calendar_coverage_pct": 100,
        },
    )

    markdown = render_weekly_markdown(report)

    assert "本周无标注故障事件" in markdown
    assert "均值不适用" in markdown
