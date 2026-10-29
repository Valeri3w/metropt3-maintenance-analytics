from datetime import datetime, timezone

import pandas as pd
import pytest

from scripts.export_demo_data import (
    DEMO_END,
    DEMO_START,
    filter_demo_events,
    filter_demo_telemetry,
)


def test_filter_demo_telemetry_uses_half_open_utc_week() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                "2020-05-31 23:59:50",
                "2020-06-01 00:00:00",
                "2020-06-07 23:59:50",
                "2020-06-08 00:00:00",
            ],
            "value": [1, 2, 3, 4],
        }
    )

    result = filter_demo_telemetry(frame)

    assert result["value"].tolist() == [2, 3]
    assert DEMO_START == datetime(2020, 6, 1, tzinfo=timezone.utc)
    assert DEMO_END == datetime(2020, 6, 8, tzinfo=timezone.utc)


def test_filter_demo_events_keeps_only_e03() -> None:
    frame = pd.DataFrame(
        {"internal_event_id": ["E01", "E03", "E04"]}
    )

    result = filter_demo_events(frame)

    assert result["internal_event_id"].tolist() == ["E03"]


def test_filter_demo_events_rejects_missing_e03() -> None:
    frame = pd.DataFrame({"internal_event_id": ["E01", "E02"]})

    with pytest.raises(ValueError, match="E03"):
        filter_demo_events(frame)
