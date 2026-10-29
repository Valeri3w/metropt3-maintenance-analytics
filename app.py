#!/usr/bin/env python3
"""Streamlit dashboard for MetroPT-3 annotated failure analysis."""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from metropt.dashboard import (  # noqa: E402
    build_pareto_figure,
    build_timeline_figure,
    event_display_frame,
    format_hours,
    period_bounds,
)
from metropt.data_access import (  # noqa: E402
    get_database_health,
    get_event_gaps,
    get_event_samples,
    get_event_trace,
    get_failure_events,
    get_period_metrics,
    get_period_pareto,
    get_period_quality,
)
from metropt.processing import week_bounds  # noqa: E402
from metropt.weekly_report import (  # noqa: E402
    build_weekly_report,
    render_weekly_html,
    render_weekly_markdown,
)


st.set_page_config(
    page_title="MetroPT-3 标注故障分析",
    page_icon=":material/query_stats:",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
      :root {
        --ink: #17201c;
        --muted: #5c6a62;
        --canvas: #f4f6f3;
        --surface: #ffffff;
        --line: #d7dfda;
        --green: #237a57;
        --green-deep: #185c43;
        --amber: #a66a17;
      }
      [data-testid="stAppViewContainer"] { background: var(--canvas); color: var(--ink); }
      [data-testid="stHeader"] { background: rgba(244, 246, 243, .94); }
      [data-testid="stSidebar"] {
        background: #e9efeb;
        border-right: 1px solid #d0dad3;
      }
      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #435149;
      }
      .block-container {
        max-width: 1480px;
        padding-top: 1.4rem;
        padding-bottom: 3rem;
      }
      h1, h2, h3 { color: var(--ink); letter-spacing: 0; }
      h1 { font-size: 2rem !important; margin-bottom: .25rem !important; }
      .eyebrow {
        color: var(--green-deep);
        font-size: .78rem;
        font-weight: 700;
        text-transform: uppercase;
      }
      .subtitle {
        color: var(--muted);
        font-size: .94rem;
        margin: .15rem 0 1rem;
      }
      .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 12px 0 16px;
      }
      .metric-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-top: 3px solid var(--green);
        border-radius: 6px;
        padding: 14px 16px 13px;
        min-height: 104px;
      }
      .metric-card.alert { border-top-color: var(--amber); }
      .metric-label {
        color: var(--muted);
        font-size: .78rem;
        font-weight: 650;
      }
      .metric-value {
        color: var(--ink);
        font-size: 1.62rem;
        font-weight: 720;
        line-height: 1.2;
        margin-top: 8px;
      }
      .metric-note {
        color: var(--muted);
        font-size: .75rem;
        margin-top: 5px;
      }
      .context-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 8px 18px;
        align-items: center;
        background: #edf3ef;
        border-left: 4px solid var(--green);
        padding: 10px 14px;
        color: #405048;
        font-size: .84rem;
        margin: 0 0 16px;
      }
      .context-bar strong { color: var(--ink); }
      .section-rule {
        border-top: 1px solid #d7dfda;
        margin: 1.35rem 0 1rem;
      }
      .note-block {
        background: #fffaf0;
        border-left: 4px solid var(--amber);
        padding: 12px 14px;
        color: #53452f;
        font-size: .86rem;
      }
      .trace-title {
        color: var(--green-deep);
        font-weight: 720;
        font-size: 1.12rem;
        margin-bottom: 4px;
      }
      .trace-metric-grid .metric-card {
        min-height: 96px;
        padding: 12px 14px;
      }
      .trace-metric-grid .metric-value {
        font-size: 1.3rem;
        overflow-wrap: anywhere;
      }
      .small-copy { color: var(--muted); font-size: .82rem; }
      a { color: #185c43; }
      [data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 6px;
        overflow: hidden;
      }
      [data-testid="stTabs"] button { font-weight: 620; }
      @media (max-width: 900px) {
        .metric-grid { grid-template-columns: 1fr 1fr; }
        .block-container { padding-left: 1rem; padding-right: 1rem; }
      }
      @media (max-width: 560px) {
        .metric-grid { grid-template-columns: 1fr; }
        h1 { font-size: 1.65rem !important; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _load_health() -> dict[str, Any]:
    error: Exception | None = None
    for _ in range(8):
        try:
            return get_database_health()
        except Exception as exc:  # pragma: no cover - depends on container state
            error = exc
            time.sleep(1)
    raise RuntimeError(f"PostgreSQL 暂不可用：{error}")


@st.cache_data(ttl=60, show_spinner=False)
def load_health() -> dict[str, Any]:
    return _load_health()


@st.cache_data(ttl=60, show_spinner=False)
def load_period(
    started_at: datetime,
    ended_at: datetime,
) -> dict[str, Any]:
    return {
        "metrics": get_period_metrics(started_at, ended_at),
        "quality": get_period_quality(started_at, ended_at),
        "pareto": get_period_pareto(started_at, ended_at),
        "events": get_failure_events(started_at, ended_at),
    }


@st.cache_data(ttl=60, show_spinner=False)
def load_event(event_id: str) -> dict[str, Any]:
    return {
        "trace": get_event_trace(event_id),
        "samples": get_event_samples(event_id, sample_limit=8),
        "gaps": get_event_gaps(event_id),
    }


def _metric_card(
    label: str,
    value: str,
    note: str,
    *,
    alert: bool = False,
) -> str:
    css_class = "metric-card alert" if alert else "metric-card"
    return (
        f'<div class="{css_class}">'
        f'<div class="metric-label">{escape(label)}</div>'
        f'<div class="metric-value">{escape(value)}</div>'
        f'<div class="metric-note">{escape(note)}</div>'
        "</div>"
    )


def _format_pct(value: Any) -> str:
    if value is None:
        return "不适用"
    return f"{float(value):.2f}%"


def _trace_samples_frame(samples: list[dict[str, Any]]) -> pd.DataFrame:
    analog_columns = {
        "sample_side": "样本位置",
        "observed_at": "观测时间（UTC）",
        "source_row_number": "CSV 行号",
        "source_index": "源索引",
        "tp2_bar": "TP2（bar）",
        "tp3_bar": "TP3（bar）",
        "h1_bar": "H1（bar）",
        "dv_pressure_bar": "DV 压差（bar）",
        "reservoirs_bar": "储气罐（bar）",
        "oil_temperature_c": "油温（°C）",
        "motor_current_a": "电机电流（A）",
    }
    frame = pd.DataFrame(samples)
    if frame.empty:
        return pd.DataFrame(columns=list(analog_columns.values()))
    available = [key for key in analog_columns if key in frame.columns]
    return frame[available].rename(columns=analog_columns)


def _trace_digital_frame(samples: list[dict[str, Any]]) -> pd.DataFrame:
    digital_columns = {
        "sample_side": "样本位置",
        "observed_at": "观测时间（UTC）",
        "source_row_number": "CSV 行号",
        "source_index": "源索引",
        "comp": "COMP",
        "dv_electric": "DV_electric",
        "towers": "Towers",
        "mpg": "MPG",
        "lps": "LPS",
        "pressure_switch": "Pressure_switch",
        "oil_level": "Oil_level",
        "caudal_impulses": "Caudal_impulses",
    }
    frame = pd.DataFrame(samples)
    if frame.empty:
        return pd.DataFrame(columns=list(digital_columns.values()))
    available = [key for key in digital_columns if key in frame.columns]
    return frame[available].rename(columns=digital_columns)


try:
    health = load_health()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

first_observed = health["first_observed_at"].astimezone(timezone.utc)
last_observed = health["last_observed_at"].astimezone(timezone.utc)

st.markdown(
    '<div class="eyebrow">维护决策支持 · PostgreSQL 指标链</div>',
    unsafe_allow_html=True,
)
st.title("MetroPT-3 标注故障分析")
st.markdown(
    '<div class="subtitle">单台地铁空压机 · 源数据、SQL 指标、原始记录追溯与维护周报</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 分析周期")
    selected_dates = st.date_input(
        "日期范围（UTC）",
        value=(first_observed.date(), last_observed.date()),
        min_value=first_observed.date(),
        max_value=last_observed.date(),
        format="YYYY-MM-DD",
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        selected_start_date, selected_end_date = selected_dates
    else:
        selected_start_date = selected_end_date = first_observed.date()

    try:
        period_started_at, period_ended_at = period_bounds(
            selected_start_date,
            selected_end_date,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    st.caption("结束日期按当日 24:00 UTC 作为半开区间边界。")
    st.divider()
    st.markdown("### 数据基线")
    st.caption(
        f"{health['telemetry_rows']:,} 条遥测 · "
        f"{health['failure_events']} 条源故障记录"
    )
    st.caption("采样频率约 0.1 Hz · 缺口阈值 > 30 秒")
    st.markdown(
        "[UCI MetroPT-3](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset)"
    )

try:
    data = load_period(period_started_at, period_ended_at)
except Exception as exc:
    st.error(f"当前周期查询失败：{exc}")
    st.stop()

metrics = data["metrics"]
quality = data["quality"]
pareto = data["pareto"]
events = data["events"]

st.markdown(
    (
        '<div class="context-bar">'
        f"<span>周期：<strong>{selected_start_date:%Y-%m-%d}</strong> "
        f"至 <strong>{selected_end_date:%Y-%m-%d}</strong>（UTC）</span>"
        f"<span>有效监测：<strong>{format_hours(metrics.get('period_effective_hours'))}</strong></span>"
        f"<span>采集缺口：<strong>{int(quality.get('gap_count') or 0)}</strong> 个</span>"
        f"<span>未观测：<strong>{format_hours(quality.get('unobserved_hours'))}</strong></span>"
        "</div>"
    ),
    unsafe_allow_html=True,
)

event_count = int(metrics.get("event_count") or 0)
longest_text = (
    f"{metrics.get('longest_event_id')} · "
    f"{format_hours(metrics.get('longest_duration_hours'))}"
    if event_count
    else "不适用"
)
cards = [
    _metric_card(
        "标注故障事件",
        str(event_count),
        f"累计 {format_hours(metrics.get('cumulative_duration_hours'))}",
    ),
    _metric_card(
        "平均标注故障持续时长",
        format_hours(metrics.get("average_duration_hours")),
        "结束时间减开始时间",
    ),
    _metric_card(
        "最长标注故障",
        longest_text,
        metrics.get("longest_failure_type") or "本周期无事件",
        alert=True,
    ),
    _metric_card(
        "标注异常区间占有效监测时长",
        _format_pct(metrics.get("annotated_share_of_effective_time_pct")),
        "仅描述性比例，不代表可用率",
    ),
]
st.markdown(
    '<div class="metric-grid">' + "".join(cards) + "</div>",
    unsafe_allow_html=True,
)

dashboard_tab, trace_tab, report_tab, method_tab = st.tabs(
    ["运行总览", "事件追溯", "周报导出", "口径与质量"]
)

with dashboard_tab:
    left, right = st.columns([1.08, 0.92], gap="large")
    with left:
        st.plotly_chart(
            build_timeline_figure(events),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        st.plotly_chart(
            build_pareto_figure(pareto),
            width="stretch",
            config={"displayModeBar": False},
        )

    st.markdown('<div class="section-rule"></div>', unsafe_allow_html=True)
    st.subheader("事件明细")
    st.caption(
        "“距上一标注结束”是相邻标注区间之间的间隔，不推断可靠性或维修等待时间。"
    )
    st.dataframe(
        event_display_frame(events),
        width="stretch",
        hide_index=True,
        column_config={
            "开始（UTC）": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm"
            ),
            "结束（UTC）": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm"
            ),
            "持续时长（h）": st.column_config.NumberColumn(format="%.4f"),
            "距上一标注结束（h）": st.column_config.NumberColumn(
                format="%.4f"
            ),
            "缺口重叠（h）": st.column_config.NumberColumn(format="%.4f"),
        },
    )

with trace_tab:
    if not events:
        st.info("当前周期没有可追溯的标注故障事件。")
    else:
        event_labels = {
            (
                f"{event['event_id']} · {event['failure_type']} · "
                f"{event['started_at']:%Y-%m-%d %H:%M} UTC"
            ): event["event_id"]
            for event in events
        }
        selected_label = st.selectbox(
            "选择事件",
            options=list(event_labels),
            index=0,
        )
        event_id = event_labels[selected_label]
        event_data = load_event(event_id)
        trace = event_data["trace"]
        samples = event_data["samples"]
        gaps = event_data["gaps"]

        st.markdown(
            (
                f'<div class="trace-title">{escape(event_id)} · '
                f"{escape(str(trace.get('failure_type') or ''))}</div>"
                f'<div class="small-copy">{escape(str(trace.get("source_document") or ""))} · '
                "原始时间戳按 UTC 工作解释</div>"
            ),
            unsafe_allow_html=True,
        )
        trace_cards = [
            _metric_card(
                "标注持续时长",
                format_hours(trace.get("duration_hours")),
                "结束时间减开始时间",
            ),
            _metric_card(
                "区间内遥测记录",
                f"{int(trace.get('sample_count') or 0):,}",
                "与标注区间重叠的观测",
            ),
            _metric_card(
                "CSV 行号范围",
                (
                    f"{trace.get('first_source_row_number')}–"
                    f"{trace.get('last_source_row_number')}"
                    if trace.get("first_source_row_number") is not None
                    else "无记录"
                ),
                "可用于回溯源文件",
            ),
            _metric_card(
                "源索引范围",
                (
                    f"{trace.get('first_source_index')}–"
                    f"{trace.get('last_source_index')}"
                    if trace.get("first_source_index") is not None
                    else "无记录"
                ),
                "保留原始索引，不视为时间",
            ),
        ]
        st.markdown(
            '<div class="metric-grid trace-metric-grid">'
            + "".join(trace_cards)
            + "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "源报告维护备注："
            + (str(trace.get("maintenance_remark") or "无"))
        )
        if gaps:
            st.warning(
                f"该标注区间与 {len(gaps)} 个采集缺口重叠；"
                "缺口内没有可用于判断过程状态的观测记录。"
            )
        else:
            st.info("该标注区间未与已识别采集缺口重叠。")

        analog_tab, digital_tab, gap_tab = st.tabs(
            ["模拟量首尾样本", "数字量与脉冲", "缺口重叠"]
        )
        with analog_tab:
            st.caption(
                "显示事件开始与结束附近的有限样本，不加载或绘制传感器全量曲线。"
            )
            st.dataframe(
                _trace_samples_frame(samples),
                width="stretch",
                hide_index=True,
                column_config={
                    "观测时间（UTC）": st.column_config.DatetimeColumn(
                        format="YYYY-MM-DD HH:mm:ss"
                    ),
                },
            )
        with digital_tab:
            st.caption(
                "布尔开关量与 0/1 脉冲信号单独展示，不与模拟量混合聚合。"
            )
            st.dataframe(
                _trace_digital_frame(samples),
                width="stretch",
                hide_index=True,
                column_config={
                    "观测时间（UTC）": st.column_config.DatetimeColumn(
                        format="YYYY-MM-DD HH:mm:ss"
                    ),
                },
            )
        with gap_tab:
            if gaps:
                gap_frame = pd.DataFrame(gaps).rename(
                    columns={
                        "gap_started_at": "缺口开始（UTC）",
                        "gap_ended_at": "缺口结束（UTC）",
                        "unobserved_hours": "未观测（h）",
                        "overlap_started_at": "重叠开始（UTC）",
                        "overlap_ended_at": "重叠结束（UTC）",
                        "overlap_seconds": "重叠（秒）",
                    }
                )
                st.dataframe(
                    gap_frame,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "缺口开始（UTC）": st.column_config.DatetimeColumn(
                            format="YYYY-MM-DD HH:mm:ss"
                        ),
                        "缺口结束（UTC）": st.column_config.DatetimeColumn(
                            format="YYYY-MM-DD HH:mm:ss"
                        ),
                        "重叠开始（UTC）": st.column_config.DatetimeColumn(
                            format="YYYY-MM-DD HH:mm:ss"
                        ),
                        "重叠结束（UTC）": st.column_config.DatetimeColumn(
                            format="YYYY-MM-DD HH:mm:ss"
                        ),
                    },
                )
            else:
                st.write("无缺口重叠记录。")

with report_tab:
    event_weeks: dict[str, date] = {}
    for event in events:
        event_date = event["started_at"].date()
        monday = event_date - timedelta(days=event_date.weekday())
        label = (
            f"{event['event_id']} 所在周 · {monday:%Y-%m-%d} 至 "
            f"{monday + timedelta(days=6):%Y-%m-%d}"
        )
        event_weeks[label] = monday

    if not event_weeks:
        st.info("当前筛选周期内没有事件可用于生成维护周报。")
    else:
        selected_week_label = st.selectbox(
            "周报周期（周一至周日 UTC）",
            options=list(event_weeks),
        )
        week_started_at, week_ended_at = week_bounds(
            event_weeks[selected_week_label]
        )
        try:
            report_data = load_period(week_started_at, week_ended_at)
            report = build_weekly_report(
                week_started_at,
                week_ended_at,
                report_data["events"],
                report_data["metrics"],
                report_data["quality"],
            )
            markdown_report = render_weekly_markdown(report)
            html_report = render_weekly_html(report)
        except Exception as exc:
            st.error(f"周报生成失败：{exc}")
        else:
            report_metrics = report_data["metrics"]
            report_cards = [
                _metric_card(
                    "周内标注事件",
                    str(int(report_metrics.get("event_count") or 0)),
                    selected_week_label,
                ),
                _metric_card(
                    "最长标注故障",
                    (
                        f"{report_metrics.get('longest_event_id')} · "
                        f"{format_hours(report_metrics.get('longest_duration_hours'))}"
                        if report_metrics.get("longest_event_id")
                        else "不适用"
                    ),
                    report_metrics.get("longest_failure_type") or "本周期无事件",
                    alert=True,
                ),
                _metric_card(
                    "周期有效监测",
                    format_hours(report_metrics.get("period_effective_hours")),
                    (
                        f"未观测 "
                        f"{format_hours(report_data['quality'].get('unobserved_hours'))}"
                    ),
                ),
                _metric_card(
                    "标注异常区间占比",
                    _format_pct(
                        report_metrics.get(
                            "annotated_share_of_effective_time_pct"
                        )
                    ),
                    "扣除采集缺口后的有效监测时长",
                ),
            ]
            st.markdown(
                '<div class="metric-grid">'
                + "".join(report_cards)
                + "</div>",
                unsafe_allow_html=True,
            )
            file_stem = f"metropt3_weekly_{week_started_at:%Y%m%d}"
            download_cols = st.columns(2)
            download_cols[0].download_button(
                "下载 HTML 周报",
                data=html_report,
                file_name=f"{file_stem}.html",
                mime="text/html",
                icon=":material/download:",
                width="stretch",
            )
            download_cols[1].download_button(
                "下载 Markdown 周报",
                data=markdown_report,
                file_name=f"{file_stem}.md",
                mime="text/markdown",
                icon=":material/download:",
                width="stretch",
            )
            with st.expander("预览 Markdown 周报", expanded=True):
                st.markdown(markdown_report)

with method_tab:
    st.subheader("指标口径")
    st.markdown(
        """
        - **标注故障持续时长**：源报告结束时间减开始时间。
        - **平均/最长标注故障持续时长**：基于当前筛选周期内的源报告事件。
        - **标注故障间隔**：当前事件开始时间减去上一事件结束时间。
        - **标注异常区间占有效监测时长比例**：标注区间总秒数除以日历区间扣除采集缺口后的有效秒数。
        - **缺口规则**：相邻观测时间差超过 30 秒；未观测时间为差值扣除 10 秒名义采样间隔，缺口内不插值。
        """
    )
    st.markdown('<div class="section-rule"></div>', unsafe_allow_html=True)
    st.subheader("本期数据质量")
    quality_cols = st.columns(4)
    quality_cols[0].metric(
        "日历覆盖率",
        _format_pct(quality.get("calendar_coverage_pct")),
    )
    quality_cols[1].metric(
        "本期缺口",
        f"{int(quality.get('gap_count') or 0)}",
    )
    quality_cols[2].metric(
        "本期未观测",
        format_hours(quality.get("unobserved_hours")),
    )
    quality_cols[3].metric(
        "本期有效监测",
        format_hours(quality.get("effective_monitoring_hours")),
    )
    st.markdown(
        """
        <div class="note-block">
        <strong>解释边界：</strong>标注异常区间不等同于设备停机、维修开始或维修结束；
        本平台不计算 OEE、MTTR 或可用率，不推断成本和预测能力。数字开关量与模拟量分开处理，
        累计计数器不做直接均值。
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-rule"></div>', unsafe_allow_html=True)
    st.subheader("Known Issues")
    st.markdown(
        """
        1. 原始数据未明确声明时区，项目按 UTC 工作解释。
        2. `Caudal_impulses` 的公开说明与实际 0/1 脉冲值存在语义冲突。
        3. 遥测存在采集缺口，跨缺口连续观测假设不成立。
        4. 故障报告为标注区间，不构成维修工单闭环。
        """
    )
    st.caption(
        "完整审计证据见 docs/data_quality.md；指标查询见 sql/metrics.sql。"
    )
