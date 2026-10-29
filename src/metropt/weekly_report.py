"""Render traceable weekly maintenance reports without inventing data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class WeeklyReport:
    week_started_at: datetime
    week_ended_at: datetime
    events: Sequence[Mapping[str, Any]]
    summary: Mapping[str, Any]
    quality: Mapping[str, Any]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Report timestamps must include a timezone.")
    return value.astimezone(timezone.utc)


def build_weekly_report(
    week_started_at: datetime,
    week_ended_at: datetime,
    events: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    quality: Mapping[str, Any],
) -> WeeklyReport:
    start = _as_utc(week_started_at)
    end = _as_utc(week_ended_at)
    if end <= start:
        raise ValueError("Week end must be later than week start.")
    return WeeklyReport(start, end, list(events), dict(summary), dict(quality))


def _format_dt(value: Any) -> str:
    if value is None:
        return "不适用"
    if isinstance(value, datetime):
        return _as_utc(value).strftime("%Y-%m-%d %H:%M UTC")
    return str(value)


def _format_number(value: Any, digits: int = 4, suffix: str = "") -> str:
    if value is None:
        return "不适用"
    return f"{float(value):.{digits}f}{suffix}"


def _markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _event_rows(report: WeeklyReport) -> list[list[str]]:
    rows: list[list[str]] = []
    for event in report.events:
        rows.append(
            [
                str(event.get("event_id", "")),
                str(event.get("failure_type", "")),
                str(event.get("severity", "") or ""),
                _format_dt(event.get("started_at")),
                _format_dt(event.get("ended_at")),
                _format_number(event.get("duration_hours"), suffix=" h"),
                str(event.get("previous_event_id") or "无"),
                _format_number(
                    event.get("hours_since_previous_annotation"),
                    suffix=" h",
                ),
                _format_number(event.get("gap_overlap_hours"), suffix=" h"),
                str(event.get("maintenance_remark") or ""),
            ]
        )
    return rows


def render_weekly_markdown(report: WeeklyReport) -> str:
    summary = report.summary
    quality = report.quality
    lines = [
        "# MetroPT-3 维护周报",
        "",
        f"- 周期：`{_format_dt(report.week_started_at)}` 至 "
        f"`{_format_dt(report.week_ended_at)}`",
        "- 设备：MetroPT-3 单台空压机",
        "- 时间口径：原始无时区时间戳按 UTC 工作解释；采样约 0.1 Hz。",
        "",
        "## 本周结论",
        "",
        f"- 标注故障事件数：{int(summary.get('event_count') or 0)}。",
        f"- 平均标注故障持续时长："
        f"{_format_number(summary.get('average_duration_hours'), suffix=' h')}。",
        f"- 最长标注故障："
        f"`{summary.get('longest_event_id') or '无'}`，"
        f"{_format_number(summary.get('longest_duration_hours'), suffix=' h')}。",
        f"- 各类型累计标注故障持续时长："
        f"{_format_number(summary.get('cumulative_duration_hours'), suffix=' h')}。",
        f"- 标注异常区间占本期有效监测时长比例："
        f"{_format_number(summary.get('annotated_share_of_effective_time_pct'), suffix='%')}。",
        "",
        "## 故障事件",
        "",
    ]

    if report.events:
        lines.extend(
            [
                "| 事件 | 类型 | 严重程度 | 开始 | 结束 | 持续 | "
                "上一事件 | 标注故障间隔 | 缺口重叠 | 维护备注 |",
                "|---|---|---|---|---|---:|---|---:|---:|---|",
            ]
        )
        for row in _event_rows(report):
            lines.append("| " + " | ".join(_markdown_cell(v) for v in row) + " |")
        lines.extend(
            [
                "",
                "事件明细均为源报告中的标注区间；持续时长为结束时间减开始时间。",
            ]
        )
    else:
        lines.extend(
            [
                "本周无标注故障事件。",
                "",
                f"- 平均标注故障持续时长：均值不适用。",
            ]
        )

    events_with_gaps = [event for event in report.events if event.get("gap_count")]
    lines.extend(
        [
            "",
            "## 数据质量提示",
            "",
            f"- 本期缺口数：{int(quality.get('gap_count') or 0)}。",
            f"- 本期未观测时长："
            f"{_format_number(quality.get('unobserved_hours'), suffix=' h')}。",
            f"- 本期日历覆盖率："
            f"{_format_number(quality.get('calendar_coverage_pct'), suffix='%')}。",
        ]
    )
    if quality.get("global_gap_count") is not None:
        lines.append(
            f"- 全数据审计缺口：{int(quality['global_gap_count'])} 个，"
            f"未观测 {_format_number(quality.get('global_unobserved_hours'), suffix=' h')}。"
        )
    if events_with_gaps:
        lines.append(
            "- 本周与缺口重叠的事件："
            + "；".join(
                f"`{event['event_id']}` {_format_number(event.get('gap_overlap_hours'), suffix=' h')}"
                for event in events_with_gaps
            )
            + "。"
        )
    else:
        lines.append("- 本周标注事件未与已识别采集缺口重叠。")
    lines.extend(
        [
            "",
            "## 口径与限制",
            "",
            "- 标注异常区间不等同于设备停机、维修开始或维修结束。",
            "- 相邻事件的间隔仅称“标注故障间隔”，不推定设备可靠性结论。",
            "- 比例指标只使用扣除采集缺口后的有效监测时长。",
            "- 缺口区间不插值、不补造遥测记录。",
            "- 数据仅包含一台设备，不做多设备排名。",
            "- 时区采用 UTC 工作解释，来源未明确声明时区，详见数据质量文档。",
            "",
            "## Known Issues",
            "",
            "1. 来源未明确声明原始时间戳时区。",
            "2. `Caudal_impulses` 的公开说明与实际 0/1 脉冲值存在语义冲突。",
            "3. 故障报告中的维护备注仅作原文保留，不构成维修工单闭环。",
            "4. 遥测存在采集缺口，跨缺口连续观测假设不成立。",
            "",
            "## 追溯与复现",
            "",
            "- 指标来自 PostgreSQL 的区间查询函数，查询区间与报告周期一致。",
            "- 每次事件可在平台的“事件追溯”页查看源文件行号和起止附近原始记录。",
            "- 数据源：UCI MetroPT-3，DOI `10.24432/C5VW3R`。",
            "",
        ]
    )
    return "\n".join(lines)


def render_weekly_html(report: WeeklyReport) -> str:
    summary = report.summary
    quality = report.quality
    event_rows = []
    for event in report.events:
        cells = [
            event.get("event_id"),
            event.get("failure_type"),
            event.get("severity"),
            _format_dt(event.get("started_at")),
            _format_dt(event.get("ended_at")),
            _format_number(event.get("duration_hours"), suffix=" h"),
            event.get("previous_event_id") or "无",
            _format_number(
                event.get("hours_since_previous_annotation"),
                suffix=" h",
            ),
            _format_number(event.get("gap_overlap_hours"), suffix=" h"),
            event.get("maintenance_remark") or "",
        ]
        event_rows.append(
            "<tr>"
            + "".join(f"<td>{escape(str(cell or ''))}</td>" for cell in cells)
            + "</tr>"
        )

    if event_rows:
        event_table = (
            "<table><thead><tr>"
            "<th>事件</th><th>类型</th><th>严重程度</th><th>开始</th>"
            "<th>结束</th><th>持续</th><th>上一事件</th>"
            "<th>标注故障间隔</th><th>缺口重叠</th><th>维护备注</th>"
            "</tr></thead><tbody>"
            + "".join(event_rows)
            + "</tbody></table>"
        )
    else:
        event_table = "<p class='empty'>本周无标注故障事件。</p>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MetroPT-3 维护周报</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0; background: #f4f6f3; color: #17201c;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.6;
    }}
    main {{ max-width: 1180px; margin: 32px auto; padding: 0 28px 48px; }}
    header {{
      border-left: 5px solid #237a57; padding: 4px 0 4px 18px;
      margin-bottom: 24px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 30px; }}
    h2 {{ margin-top: 30px; font-size: 20px; color: #185c43; }}
    .meta, .note {{ color: #516259; }}
    .kpis {{
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px; margin: 20px 0;
    }}
    .kpi, .quality {{
      background: #fff; border: 1px solid #d7dfda; padding: 16px;
    }}
    .kpi strong {{ display: block; font-size: 22px; color: #14573e; }}
    .kpi span {{ font-size: 13px; color: #5a685f; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 14px; }}
    th, td {{ border: 1px solid #d7dfda; padding: 9px 10px; text-align: left; }}
    th {{ background: #e9f0eb; }}
    .quality {{ border-left: 4px solid #b37a20; }}
    ul {{ padding-left: 22px; }}
    .empty {{ background: #fff; padding: 18px; border: 1px solid #d7dfda; }}
    @media (max-width: 760px) {{
      main {{ margin: 20px auto; padding: 0 14px 32px; }}
      .kpis {{ grid-template-columns: 1fr 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>MetroPT-3 维护周报</h1>
    <div class="meta">{escape(_format_dt(report.week_started_at))} 至
      {escape(_format_dt(report.week_ended_at))} · 单台空压机 · 时区 UTC</div>
  </header>
  <section class="kpis">
    <div class="kpi"><strong>{int(summary.get("event_count") or 0)}</strong><span>标注故障事件</span></div>
    <div class="kpi"><strong>{escape(_format_number(summary.get("average_duration_hours"), suffix=" h"))}</strong><span>平均标注故障持续时长</span></div>
    <div class="kpi"><strong>{escape(_format_number(summary.get("longest_duration_hours"), suffix=" h"))}</strong><span>最长标注故障</span></div>
    <div class="kpi"><strong>{escape(_format_number(summary.get("annotated_share_of_effective_time_pct"), suffix="%"))}</strong><span>异常区间占有效监测时长</span></div>
  </section>
  <h2>故障事件</h2>
  {event_table}
  <h2>数据质量提示</h2>
  <div class="quality">
    <p>本期缺口 {int(quality.get("gap_count") or 0)} 个，未观测
      {escape(_format_number(quality.get("unobserved_hours"), suffix=" h"))}，
      日历覆盖率 {escape(_format_number(quality.get("calendar_coverage_pct"), suffix="%"))}。</p>
    <p>缺口区间不插值、不补造遥测；比例指标使用扣除缺口后的有效监测时长。</p>
  </div>
  <h2>口径与限制</h2>
  <ul>
    <li>标注异常区间不等同于设备停机、维修开始或维修结束。</li>
    <li>相邻事件的间隔仅称“标注故障间隔”。</li>
    <li>采样约 0.1 Hz；原始无时区时间戳按 UTC 工作解释。</li>
    <li>仅一台设备，不做多设备排名。</li>
    <li>维护备注仅作原文保留，不构造维修工单闭环。</li>
  </ul>
  <h2>Known Issues</h2>
  <ul>
    <li>来源未明确声明原始时间戳时区。</li>
    <li><code>Caudal_impulses</code> 的公开说明与实际 0/1 脉冲值存在语义冲突。</li>
    <li>遥测存在采集缺口，跨缺口连续观测假设不成立。</li>
  </ul>
  <p class="note">数据源：UCI MetroPT-3，DOI 10.24432/C5VW3R。</p>
</main>
</body>
</html>
"""
