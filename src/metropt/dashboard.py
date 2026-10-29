"""Presentation helpers for the traceable maintenance dashboard."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


INK = "#17201c"
MUTED = "#5c6a62"
GREEN = "#237a57"
PALE_GREEN = "#dcebe3"
AMBER = "#a66a17"
GRID = "#dfe5e1"


def period_bounds(started_on: date, ended_on: date) -> tuple[datetime, datetime]:
    """Return an inclusive calendar-date selection as UTC half-open bounds."""
    if ended_on < started_on:
        raise ValueError("The end date must not be earlier than the start date.")
    started_at = datetime.combine(started_on, time.min, tzinfo=timezone.utc)
    ended_at = datetime.combine(
        ended_on + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return started_at, ended_at


def format_hours(value: Any) -> str:
    if value is None:
        return "不适用"
    return f"{float(value):.2f} h"


def event_display_frame(
    events: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Return event rows with explicit labels for missing annotations."""
    columns = {
        "event_id": "事件",
        "failure_type": "故障类型",
        "severity": "严重程度",
        "started_at": "开始（UTC）",
        "ended_at": "结束（UTC）",
        "duration_hours": "持续时长（h）",
        "previous_event_id": "上一事件",
        "hours_since_previous_annotation": "距上一标注结束（h）",
        "gap_count": "重叠缺口数",
        "gap_overlap_hours": "缺口重叠（h）",
    }
    if not events:
        return pd.DataFrame(columns=list(columns.values()))

    frame = pd.DataFrame(events)
    available = [key for key in columns if key in frame.columns]
    displayed = frame[available].rename(columns=columns)
    displayed["上一事件"] = displayed["上一事件"].fillna("无")
    displayed["距上一标注结束（h）"] = displayed[
        "距上一标注结束（h）"
    ].fillna("不适用")
    return displayed


def build_timeline_figure(
    events: Sequence[Mapping[str, Any]],
) -> go.Figure:
    """Build a horizontal timeline of annotated intervals, not downtime."""
    figure = go.Figure()
    if not events:
        figure.update_layout(
            title=Text("当前周期无标注故障事件"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=250,
        )
        return figure

    labels = [
        f"{event['event_id']} · {event['failure_type']}" for event in events
    ]
    starts = [event["started_at"] for event in events]
    durations_ms = [
        (event["ended_at"] - event["started_at"]).total_seconds() * 1000
        for event in events
    ]
    hover_text = [
        (
            f"<b>{event['event_id']}</b> · {event['failure_type']}<br>"
            f"开始：{event['started_at']:%Y-%m-%d %H:%M UTC}<br>"
            f"结束：{event['ended_at']:%Y-%m-%d %H:%M UTC}<br>"
            f"持续：{float(event['duration_hours']):.2f} 小时<br>"
            "口径：源报告标注异常区间，不代表停机或维修时间"
        )
        for event in events
    ]
    figure.add_trace(
        go.Bar(
            x=durations_ms,
            base=starts,
            y=labels,
            orientation="h",
            marker={
                "color": GREEN,
                "line": {"color": "#185c43", "width": 1},
            },
            hovertext=hover_text,
            hoverinfo="text",
            name="标注异常区间",
        )
    )
    figure.update_layout(
        title={
            "text": "标注异常区间（UTC）",
            "subtitle": {
                "text": "区间来自源故障报告，不代表设备停机或维修时间",
                "font": {"size": 12, "color": MUTED},
            },
            "font": {"size": 17, "color": INK},
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(260, 92 + 54 * len(events)),
        margin={"l": 24, "r": 24, "t": 82, "b": 42},
        showlegend=False,
        xaxis={
            "type": "date",
            "title": "UTC 时间",
            "gridcolor": GRID,
            "zeroline": False,
        },
        yaxis={
            "autorange": "reversed",
            "title": "",
            "gridcolor": "rgba(0,0,0,0)",
        },
        hoverlabel={"bgcolor": "#ffffff", "font_color": INK},
    )
    return figure


def build_pareto_figure(
    pareto: Sequence[Mapping[str, Any]],
) -> go.Figure:
    """Build duration bars with a cumulative share line."""
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    if not pareto:
        figure.update_layout(
            title=Text("当前周期无故障类型数据"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=280,
        )
        return figure

    failure_types = [row["failure_type"] for row in pareto]
    cumulative_hours = [float(row["cumulative_hours"]) for row in pareto]
    cumulative_share = [
        float(row["cumulative_share_pct"]) for row in pareto
    ]
    event_counts = [int(row["event_count"]) for row in pareto]
    figure.add_trace(
        go.Bar(
            x=failure_types,
            y=cumulative_hours,
            name="累计标注故障持续时长",
            marker={"color": PALE_GREEN},
            customdata=event_counts,
            hovertemplate=(
                "<b>%{x}</b><br>事件数：%{customdata}<br>"
                "累计时长：%{y:.2f} 小时<extra></extra>"
            ),
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=failure_types,
            y=cumulative_share,
            mode="lines+markers",
            name="累计占比",
            line={"color": AMBER, "width": 2},
            marker={"size": 7, "color": AMBER},
            hovertemplate="<b>%{x}</b><br>累计占比：%{y:.2f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.update_layout(
        title={
            "text": "按故障类型的累计持续时长 Pareto",
            "font": {"size": 17, "color": INK},
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=340,
        margin={"l": 24, "r": 28, "t": 62, "b": 58},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        hoverlabel={"bgcolor": "#ffffff", "font_color": INK},
    )
    figure.update_xaxes(title="", gridcolor="rgba(0,0,0,0)")
    figure.update_yaxes(
        title="累计小时",
        secondary_y=False,
        gridcolor=GRID,
        rangemode="tozero",
    )
    figure.update_yaxes(
        title="累计占比",
        secondary_y=True,
        range=[0, 105],
        ticksuffix="%",
        showgrid=False,
    )
    return figure


class Text(str):
    """Small wrapper that keeps layout titles explicit in helper tests."""
