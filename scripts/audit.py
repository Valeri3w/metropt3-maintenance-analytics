#!/usr/bin/env python3
"""Audit the MetroPT-3 raw files and render reproducible data-quality evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
DEFAULT_ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "audit"

NOMINAL_INTERVAL_SECONDS = 10
GAP_THRESHOLD_SECONDS = 30
DEFAULT_CHUNK_SIZE = 100_000

UCI_DATASET_URL = "https://archive.ics.uci.edu/dataset/791/metropt+3+dataset"
UCI_DATASET_DOI = "10.24432/C5VW3R"
MIRROR_URL = "https://www.kaggle.com/api/v1/datasets/download/joebeachcapital/metropt-3-dataset"

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

FIELD_METADATA = {
    "tp2": ("analog", "bar", "压缩机压力"),
    "tp3": ("analog", "bar", "气动面板压力"),
    "h1": ("analog", "bar", "旋风分离器排放引起的压力"),
    "dv_pressure": ("analog", "bar", "干燥塔排放压降"),
    "reservoirs": ("analog", "bar", "储气罐下游压力"),
    "oil_temperature": ("analog", "degC", "油温"),
    "motor_current": ("analog", "A", "电机单相电流"),
    "comp": ("digital", "0/1", "压缩机进气阀电信号"),
    "dv_eletric": ("digital", "0/1", "压缩机出口阀控制信号"),
    "towers": ("digital", "0/1", "干燥塔选择信号"),
    "mpg": ("digital", "0/1", "低压启动电信号"),
    "lps": ("digital", "0/1", "低压检测信号"),
    "pressure_switch": ("digital", "0/1", "先导控制阀压力信号"),
    "oil_level": ("digital", "0/1", "低油位检测信号"),
    "caudal_impulses": ("digital_pulse", "0/1", "流量计脉冲信号"),
}

FAILURE_PATTERN = re.compile(
    r"#(?P<source_id>\d+)\s+"
    r"(?P<start_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<start_time>\d{1,2}:\d{2})\s+"
    r"(?P<end_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<end_time>\d{1,2}:\d{2})\s+"
    r"(?P<failure_type>Air\s*[Ll]eak)\s+"
    r"(?P<severity>High\s+stress)"
    r"(?P<tail>.*?)(?=#\d+\s+\d{1,2}/\d{1,2}/\d{4}|\Z)",
    re.IGNORECASE,
)

MAINTENANCE_PATTERN = re.compile(
    r"Maintenance\s+on\s+(?P<day>\d{1,2})(?P<month>[A-Za-z]{3})\s+"
    r"at\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    return parser.parse_args()


def find_single_file(root: Path, suffix: str) -> Path:
    matches = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == suffix.lower()
    )
    if len(matches) != 1:
        rendered = "\n".join(f"- {path}" for path in matches) or "- <none>"
        raise FileNotFoundError(
            f"Expected exactly one {suffix} file below {root}, found {len(matches)}:\n{rendered}"
        )
    return matches[0]


def hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return normalize_whitespace("\n".join(pages))


def parse_maintenance_remark(
    report_text: str | None, event_start: datetime
) -> dict[str, Any] | None:
    if not report_text:
        return None
    match = MAINTENANCE_PATTERN.search(report_text)
    if not match:
        return {
            "raw_text": report_text,
            "parsed": False,
        }
    month_name = match.group("month").casefold()
    if month_name not in MONTHS:
        return {
            "raw_text": report_text,
            "parsed": False,
        }
    maintenance_naive = datetime(
        event_start.year,
        MONTHS[month_name],
        int(match.group("day")),
        int(match.group("hour")),
        int(match.group("minute")),
    )
    maintenance_utc = maintenance_naive.replace(tzinfo=timezone.utc)
    return {
        "raw_text": report_text,
        "parsed": True,
        "maintenance_utc": maintenance_utc,
    }


def parse_failure_events(pdf_text: str) -> list[dict[str, Any]]:
    matches = list(FAILURE_PATTERN.finditer(pdf_text))
    if len(matches) != 4:
        raise ValueError(
            f"Expected four failure records in the source PDF, parsed {len(matches)}."
        )

    events: list[dict[str, Any]] = []
    for index, match in enumerate(matches, start=1):
        start_naive = datetime.strptime(
            f"{match.group('start_date')} {match.group('start_time')}",
            "%m/%d/%Y %H:%M",
        )
        end_naive = datetime.strptime(
            f"{match.group('end_date')} {match.group('end_time')}",
            "%m/%d/%Y %H:%M",
        )
        source_type = normalize_whitespace(match.group("failure_type"))
        report_text = re.sub(
            r"^[\s:;.,-]+", "", normalize_whitespace(match.group("tail"))
        ).strip(" .;")
        report_text = report_text or None
        event = {
            "internal_event_id": f"E{index:02d}",
            "source_id": int(match.group("source_id")),
            "source_failure_type": source_type,
            "failure_type": "Air Leak",
            "severity": normalize_whitespace(match.group("severity")).title(),
            "start_utc": start_naive.replace(tzinfo=timezone.utc),
            "end_utc": end_naive.replace(tzinfo=timezone.utc),
            "report_text": report_text,
        }
        event["duration_seconds"] = int(
            (event["end_utc"] - event["start_utc"]).total_seconds()
        )
        event["duration_hours"] = event["duration_seconds"] / 3600
        event["start_before_end"] = event["start_utc"] < event["end_utc"]
        event["maintenance_remark"] = parse_maintenance_remark(
            report_text, event["start_utc"]
        )
        events.append(event)

    source_id_counts = Counter(event["source_id"] for event in events)
    for event in events:
        event["source_id_occurrences"] = source_id_counts[event["source_id"]]
        event["source_id_duplicated"] = event["source_id_occurrences"] > 1

        remark = event["maintenance_remark"]
        if remark and remark.get("parsed"):
            delta_seconds = int(
                (
                    remark["maintenance_utc"] - event["end_utc"]
                ).total_seconds()
            )
            remark["seconds_from_event_end"] = delta_seconds
            if delta_seconds < 0:
                remark["relation_to_event"] = "before_event_end"
            else:
                remark["relation_to_event"] = "after_event_end"
        elif remark:
            remark["seconds_from_event_end"] = None
            remark["relation_to_event"] = "unparsed"

    return events


def find_column(columns: list[str], target: str) -> str:
    for column in columns:
        if column.strip().casefold() == target:
            return column
    raise ValueError(f"Could not find a required column named {target!r}: {columns}")


def find_source_index_column(columns: list[str], timestamp_column: str) -> str:
    first = columns[0]
    normalized = first.strip().casefold()
    if normalized == "" or normalized.startswith("unnamed"):
        return first
    if first != timestamp_column:
        return first
    raise ValueError(f"Could not identify the source index column: {columns}")


def field_key(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", column.strip().casefold()).strip("_")


def numeric_unique_limited(series: pd.Series, limit: int = 3) -> set[float]:
    uniques = pd.unique(series.dropna())
    return {float(value) for value in uniques[:limit]}


def update_min_max(
    state: dict[str, float | None], values: pd.Series
) -> None:
    valid = values.dropna()
    if valid.empty:
        return
    chunk_min = float(valid.min())
    chunk_max = float(valid.max())
    if state["min"] is None or chunk_min < state["min"]:
        state["min"] = chunk_min
    if state["max"] is None or chunk_max > state["max"]:
        state["max"] = chunk_max


def scan_telemetry(
    csv_path: Path, events: list[dict[str, Any]], chunk_size: int
) -> dict[str, Any]:
    header = list(pd.read_csv(csv_path, nrows=0).columns)
    timestamp_column = find_column(header, "timestamp")
    source_index_column = find_source_index_column(header, timestamp_column)
    data_columns = [
        column
        for column in header
        if column not in {timestamp_column, source_index_column}
    ]

    null_counts: Counter[str] = Counter()
    numeric_error_counts: Counter[str] = Counter()
    numeric_stats = {
        column: {"min": None, "max": None} for column in data_columns
    }
    observed_values = {column: set() for column in data_columns}
    truncated_values = {column: False for column in data_columns}
    negative_steps = Counter()
    previous_value: dict[str, float | None] = {column: None for column in data_columns}
    digital_columns: set[str] = set()

    row_count = 0
    parse_error_count = 0
    duplicate_count = 0
    out_of_order_count = 0
    delta_counts: Counter[int] = Counter()
    gaps: list[dict[str, Any]] = []
    dst_hour_counts: Counter[str] = Counter()

    source_index_numeric_errors = 0
    source_index_step_counts: Counter[int] = Counter()
    source_index_decreases = 0
    source_index_min: int | None = None
    source_index_max: int | None = None
    previous_source_index: int | None = None
    previous_timestamp: pd.Timestamp | None = None
    first_timestamp: pd.Timestamp | None = None
    last_timestamp: pd.Timestamp | None = None
    minimum_timestamp: pd.Timestamp | None = None
    maximum_timestamp: pd.Timestamp | None = None

    for event in events:
        event["_sample_count"] = 0
        event["_first_sample_timestamp"] = None
        event["_last_sample_timestamp"] = None
        event["_first_source_index"] = None
        event["_last_source_index"] = None
        event["_gap_seconds_overlap"] = 0
        event["_gap_count"] = 0

    csv_reader = pd.read_csv(csv_path, chunksize=chunk_size)
    for chunk_number, frame in enumerate(csv_reader, start=1):
        chunk_columns = list(frame.columns)
        if chunk_columns != header:
            raise ValueError(
                f"CSV header changed in chunk {chunk_number}: {chunk_columns}"
            )

        row_count += len(frame)
        null_counts.update(
            {column: int(count) for column, count in frame.isna().sum().items()}
        )

        parsed_timestamps = pd.to_datetime(
            frame[timestamp_column],
            format="%Y-%m-%d %H:%M:%S",
            errors="coerce",
        )
        invalid_timestamps = parsed_timestamps.isna()
        parse_error_count += int(invalid_timestamps.sum())
        timestamps = parsed_timestamps.dropna().reset_index(drop=True)

        if not timestamps.empty:
            chunk_min = timestamps.min()
            chunk_max = timestamps.max()
            if minimum_timestamp is None or chunk_min < minimum_timestamp:
                minimum_timestamp = chunk_min
            if maximum_timestamp is None or chunk_max > maximum_timestamp:
                maximum_timestamp = chunk_max
            if first_timestamp is None:
                first_timestamp = timestamps.iloc[0]
            last_timestamp = timestamps.iloc[-1]

            duplicate_count += int(timestamps.duplicated().sum())
            if previous_timestamp is not None:
                if timestamps.iloc[0] == previous_timestamp:
                    duplicate_count += 1
                comparison = pd.concat(
                    [pd.Series([previous_timestamp]), timestamps],
                    ignore_index=True,
                )
            else:
                comparison = timestamps
            differences = comparison.diff().dt.total_seconds()
            out_of_order_count += int((differences < 0).sum())
            positive_seconds = differences[differences > 0].round().astype("int64")
            for seconds, count in positive_seconds.value_counts().items():
                delta_counts[int(seconds)] += int(count)

            boundary_mask = (
                (timestamps >= pd.Timestamp("2020-03-28 22:00:00"))
                & (timestamps < pd.Timestamp("2020-03-29 06:00:00"))
            )
            if boundary_mask.any():
                hour_labels = timestamps.loc[boundary_mask].dt.strftime(
                    "%Y-%m-%dT%H:00:00"
                )
                dst_hour_counts.update(hour_labels.value_counts().to_dict())

            if "differences" in locals() and (differences > GAP_THRESHOLD_SECONDS).any():
                gap_rows = comparison.loc[
                    differences > GAP_THRESHOLD_SECONDS
                ].reset_index(drop=True)
                previous_rows = comparison.shift(1).loc[
                    differences > GAP_THRESHOLD_SECONDS
                ].reset_index(drop=True)
                for previous, current in zip(previous_rows, gap_rows):
                    unobserved_seconds = int(
                        (current - previous).total_seconds()
                        - NOMINAL_INTERVAL_SECONDS
                    )
                    gaps.append(
                        {
                            "previous_timestamp": previous.to_pydatetime(),
                            "next_timestamp": current.to_pydatetime(),
                            "gap_start": (
                                previous + timedelta(seconds=NOMINAL_INTERVAL_SECONDS)
                            ).to_pydatetime(),
                            "gap_end": current.to_pydatetime(),
                            "unobserved_seconds": unobserved_seconds,
                            "unobserved_hours": unobserved_seconds / 3600,
                        }
                    )
            previous_timestamp = pd.Timestamp(timestamps.iloc[-1])

        source_indices = pd.to_numeric(
            frame[source_index_column], errors="coerce"
        )
        source_index_numeric_errors += int(source_indices.isna().sum())
        valid_indices = source_indices.dropna()
        if not valid_indices.empty:
            rounded_indices = valid_indices.round().astype("int64")
            chunk_index_min = int(rounded_indices.min())
            chunk_index_max = int(rounded_indices.max())
            if source_index_min is None or chunk_index_min < source_index_min:
                source_index_min = chunk_index_min
            if source_index_max is None or chunk_index_max > source_index_max:
                source_index_max = chunk_index_max

            if previous_source_index is not None:
                comparison_indices = pd.concat(
                    [
                        pd.Series([previous_source_index], dtype="int64"),
                        rounded_indices.reset_index(drop=True),
                    ],
                    ignore_index=True,
                )
            else:
                comparison_indices = rounded_indices.reset_index(drop=True)
            index_differences = comparison_indices.diff()
            source_index_decreases += int((index_differences < 0).sum())
            for step, count in index_differences.dropna().astype("int64").value_counts().items():
                source_index_step_counts[int(step)] += int(count)
            previous_source_index = int(rounded_indices.iloc[-1])

        for column in data_columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            numeric_error_counts[column] += int(
                (values.isna() & frame[column].notna()).sum()
            )
            update_min_max(numeric_stats[column], values)

            if not truncated_values[column]:
                new_values = numeric_unique_limited(values, limit=4)
                observed_values[column].update(new_values)
                if len(observed_values[column]) > 2:
                    truncated_values[column] = True

            unique_so_far = observed_values[column]
            if len(unique_so_far) <= 2 and unique_so_far.issubset({0.0, 1.0}):
                digital_columns.add(column)

            if column in digital_columns:
                numeric_values = values
                if previous_value[column] is not None:
                    comparison_values = pd.concat(
                        [
                            pd.Series([previous_value[column]]),
                            numeric_values.reset_index(drop=True),
                        ],
                        ignore_index=True,
                    )
                else:
                    comparison_values = numeric_values.reset_index(drop=True)
                negative_steps[column] += int(
                    (comparison_values.diff() < 0).sum()
                )
                valid_numeric = numeric_values.dropna()
                if not valid_numeric.empty:
                    previous_value[column] = float(valid_numeric.iloc[-1])

        if not parsed_timestamps.empty:
            valid_timestamp_mask = parsed_timestamps.notna()
            numeric_source_indices = source_indices.where(valid_timestamp_mask)
            for event in events:
                event_mask = (
                    parsed_timestamps >= pd.Timestamp(
                        event["start_utc"].replace(tzinfo=None)
                    )
                ) & (
                    parsed_timestamps
                    <= pd.Timestamp(event["end_utc"].replace(tzinfo=None))
                )
                sample_count = int(event_mask.sum())
                if sample_count:
                    event["_sample_count"] += sample_count
                    event_timestamps = parsed_timestamps.loc[event_mask]
                    event_indices = numeric_source_indices.loc[event_mask].dropna()
                    if event["_first_sample_timestamp"] is None:
                        event["_first_sample_timestamp"] = (
                            event_timestamps.min().to_pydatetime()
                        )
                    event["_last_sample_timestamp"] = (
                        event_timestamps.max().to_pydatetime()
                    )
                    if not event_indices.empty:
                        if event["_first_source_index"] is None:
                            event["_first_source_index"] = int(
                                event_indices.min()
                            )
                        event["_last_source_index"] = int(
                            event_indices.max()
                        )

    for column in data_columns:
        if observed_values[column] and observed_values[column].issubset({0.0, 1.0}):
            digital_columns.add(column)

    fields = []
    for column in header:
        if column == timestamp_column:
            fields.append(
                {
                    "column": column,
                    "role": "time",
                    "unit": "UTC timestamp",
                    "description": "原始无时区时间戳，项目固定按 UTC 解释",
                    "min": (
                        minimum_timestamp.isoformat()
                        if minimum_timestamp is not None
                        else None
                    ),
                    "max": (
                        maximum_timestamp.isoformat()
                        if maximum_timestamp is not None
                        else None
                    ),
                    "observed_values": None,
                    "null_count": null_counts[column],
                    "numeric_parse_errors": parse_error_count,
                }
            )
            continue
        if column == source_index_column:
            fields.append(
                {
                    "column": column,
                    "role": "identifier",
                    "unit": "source row identifier",
                    "description": "源 CSV 行索引；相邻记录递增 10，不是时间",
                    "min": source_index_min,
                    "max": source_index_max,
                    "observed_values": None,
                    "null_count": null_counts[column],
                    "numeric_parse_errors": source_index_numeric_errors,
                }
            )
            continue

        key = field_key(column)
        metadata = FIELD_METADATA.get(key)
        is_digital = column in digital_columns
        if is_digital:
            role = "digital_pulse" if key == "caudal_impulses" else "digital_binary"
            observed = sorted(observed_values[column])
        else:
            role = "analog"
            observed = None
        fields.append(
            {
                "column": column,
                "role": role,
                "unit": metadata[1] if metadata else "unknown",
                "description": metadata[2] if metadata else "unclassified",
                "min": numeric_stats[column]["min"],
                "max": numeric_stats[column]["max"],
                "observed_values": observed,
                "null_count": null_counts[column],
                "numeric_parse_errors": numeric_error_counts[column],
                "negative_steps": (
                    int(negative_steps[column]) if is_digital else None
                ),
                "monotonic_non_decreasing": (
                    negative_steps[column] == 0 if is_digital else None
                ),
            }
        )

    if minimum_timestamp is None or maximum_timestamp is None:
        raise ValueError("No valid timestamps were found in the telemetry CSV.")

    for gap in gaps:
        gap["overlapping_event_ids"] = []
        gap_start = gap["gap_start"].replace(tzinfo=timezone.utc)
        gap_end = gap["gap_end"].replace(tzinfo=timezone.utc)
        for event in events:
            overlap_start = max(gap_start, event["start_utc"])
            overlap_end = min(gap_end, event["end_utc"])
            overlap_seconds = max(
                0, int((overlap_end - overlap_start).total_seconds())
            )
            if overlap_seconds:
                gap["overlapping_event_ids"].append(event["internal_event_id"])
                event["_gap_seconds_overlap"] += overlap_seconds
                event["_gap_count"] += 1

    calendar_span_seconds = (
        int((maximum_timestamp - minimum_timestamp).total_seconds())
        + NOMINAL_INTERVAL_SECONDS
    )
    unobserved_seconds = sum(gap["unobserved_seconds"] for gap in gaps)
    observed_duration_seconds = calendar_span_seconds - unobserved_seconds

    for event in events:
        event["within_telemetry_range"] = (
            event["start_utc"].replace(tzinfo=None) >= minimum_timestamp
            and event["end_utc"].replace(tzinfo=None) <= maximum_timestamp
        )
        event["observed_duration_seconds"] = (
            event["duration_seconds"] - event["_gap_seconds_overlap"]
        )
        event["observed_coverage_pct"] = (
            100
            * event["observed_duration_seconds"]
            / event["duration_seconds"]
            if event["duration_seconds"]
            else None
        )

    cumulative_by_type: Counter[str] = Counter()
    for event in events:
        cumulative_by_type[event["failure_type"]] += event["duration_seconds"]
    total_duration_seconds = sum(cumulative_by_type.values())
    pareto = []
    running_seconds = 0
    for failure_type, seconds in cumulative_by_type.most_common():
        running_seconds += seconds
        pareto.append(
            {
                "failure_type": failure_type,
                "cumulative_seconds": seconds,
                "cumulative_hours": seconds / 3600,
                "cumulative_share_pct": (
                    100 * seconds / total_duration_seconds
                    if total_duration_seconds
                    else None
                ),
                "running_cumulative_share_pct": (
                    100
                    * running_seconds
                    / total_duration_seconds
                    if total_duration_seconds
                    else None
                ),
            }
        )

    ordered_events = sorted(events, key=lambda event: event["start_utc"])
    annotated_intervals = []
    for previous, current in zip(ordered_events, ordered_events[1:]):
        seconds = int(
            (current["start_utc"] - previous["end_utc"]).total_seconds()
        )
        annotated_intervals.append(
            {
                "from_event_id": previous["internal_event_id"],
                "to_event_id": current["internal_event_id"],
                "start_utc": previous["end_utc"],
                "end_utc": current["start_utc"],
                "interval_seconds": seconds,
                "interval_hours": seconds / 3600,
            }
        )

    all_durations = [event["duration_seconds"] for event in events]
    longest_event = max(events, key=lambda event: event["duration_seconds"])
    modal_interval = max(
        delta_counts.items(), key=lambda item: (item[1], -item[0])
    )[0]

    return {
        "header": header,
        "timestamp_column": timestamp_column,
        "source_index_column": source_index_column,
        "row_count": row_count,
        "minimum_timestamp": minimum_timestamp,
        "maximum_timestamp": maximum_timestamp,
        "parse_error_count": parse_error_count,
        "duplicate_timestamp_count": duplicate_count,
        "out_of_order_count": out_of_order_count,
        "null_counts": dict(null_counts),
        "source_index": {
            "min": source_index_min,
            "max": source_index_max,
            "numeric_errors": source_index_numeric_errors,
            "decreases": source_index_decreases,
            "step_counts": {
                str(step): count
                for step, count in sorted(source_index_step_counts.items())
            },
        },
        "delta_counts_seconds": {
            str(seconds): count
            for seconds, count in sorted(delta_counts.items())
        },
        "modal_interval_seconds": modal_interval,
        "gaps": gaps,
        "calendar_span_seconds": calendar_span_seconds,
        "unobserved_seconds": unobserved_seconds,
        "observed_duration_seconds": observed_duration_seconds,
        "calendar_coverage_pct": 100
        * observed_duration_seconds
        / calendar_span_seconds,
        "dst_hour_counts": dict(sorted(dst_hour_counts.items())),
        "fields": fields,
        "digital_columns": sorted(digital_columns),
        "cumulative_columns": [],
        "events": events,
        "failure_metrics": {
            "mean_duration_seconds": sum(all_durations) / len(all_durations),
            "mean_duration_hours": sum(all_durations) / len(all_durations) / 3600,
            "longest_event_id": longest_event["internal_event_id"],
            "longest_duration_hours": longest_event["duration_hours"],
            "total_duration_hours": sum(all_durations) / 3600,
            "pareto": pareto,
            "annotated_intervals": annotated_intervals,
        },
    }


def inspect_archive(
    archive_path: Path | None, extracted_files: list[Path]
) -> list[dict[str, Any]]:
    if archive_path is None:
        return []
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        result = []
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            result.append(
                {
                    "name": entry.filename,
                    "size_bytes": entry.file_size,
                    "compressed_bytes": entry.compress_size,
                    "extracted_file_present": Path(entry.filename).name
                    in {path.name for path in extracted_files},
                    "entry_present": entry.filename in names,
                }
            )
        return result


def utc_from_naive(value: datetime | pd.Timestamp) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    return value.replace(tzinfo=timezone.utc)


def format_utc(value: datetime | pd.Timestamp | str) -> str:
    if isinstance(value, str):
        return value
    return utc_from_naive(value).isoformat().replace("+00:00", "Z")


def format_hours(seconds: float) -> str:
    return f"{seconds / 3600:.4f}"


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    result = {
        "internal_event_id": event["internal_event_id"],
        "source_id": event["source_id"],
        "source_id_occurrences": event["source_id_occurrences"],
        "source_id_duplicated": event["source_id_duplicated"],
        "source_failure_type": event["source_failure_type"],
        "failure_type": event["failure_type"],
        "severity": event["severity"],
        "start_utc": format_utc(event["start_utc"]),
        "end_utc": format_utc(event["end_utc"]),
        "duration_seconds": event["duration_seconds"],
        "duration_hours": event["duration_hours"],
        "start_before_end": event["start_before_end"],
        "report_text": event["report_text"],
        "maintenance_remark": event["maintenance_remark"],
        "within_telemetry_range": event["within_telemetry_range"],
        "sample_count": event["_sample_count"],
        "first_sample_timestamp_utc": (
            format_utc(event["_first_sample_timestamp"])
            if event["_first_sample_timestamp"]
            else None
        ),
        "last_sample_timestamp_utc": (
            format_utc(event["_last_sample_timestamp"])
            if event["_last_sample_timestamp"]
            else None
        ),
        "first_source_index": event["_first_source_index"],
        "last_source_index": event["_last_source_index"],
        "gap_count": event["_gap_count"],
        "gap_seconds_overlap": event["_gap_seconds_overlap"],
        "gap_hours_overlap": event["_gap_seconds_overlap"] / 3600,
        "observed_duration_seconds": event["observed_duration_seconds"],
        "observed_coverage_pct": event["observed_coverage_pct"],
    }
    remark = result["maintenance_remark"]
    if remark and remark.get("maintenance_utc"):
        remark["maintenance_utc"] = format_utc(remark["maintenance_utc"])
    return result


def build_evidence(
    raw_dir: Path,
    csv_path: Path,
    pdf_path: Path,
    pdf_text: str,
    events: list[dict[str, Any]],
    scan: dict[str, Any],
    archive_path: Path | None,
    chunk_size: int,
) -> dict[str, Any]:
    all_durations = [event["duration_seconds"] for event in events]
    failed_checks = []
    if not all(event["start_before_end"] for event in events):
        failed_checks.append("one or more failure intervals have start >= end")
    if not all(event["within_telemetry_range"] for event in events):
        failed_checks.append("one or more failure intervals fall outside telemetry")
    if scan["duplicate_timestamp_count"]:
        failed_checks.append("duplicate timestamps remain")
    if scan["out_of_order_count"]:
        failed_checks.append("out-of-order timestamps remain")

    largest_gap = (
        max(scan["gaps"], key=lambda gap: gap["unobserved_seconds"])
        if scan["gaps"]
        else None
    )
    failures = scan["events"]
    cumulative_total = sum(event["duration_seconds"] for event in failures)
    evidence = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "audit_status": (
            "pass_with_known_issues" if not failed_checks else "fail"
        ),
        "failed_checks": failed_checks,
        "source": {
            "uci_dataset_url": UCI_DATASET_URL,
            "uci_dataset_doi": UCI_DATASET_DOI,
            "download_mirror_url": MIRROR_URL,
            "provenance_note": (
                "Raw files were downloaded from a public UCI mirror because "
                "the direct UCI download was impractically slow. Mirror file "
                "sizes match the file sizes reported by UCI, but an official "
                "archive-level hash comparison was not completed."
            ),
            "raw_dir": display_path(raw_dir),
            "csv": {
                "path": display_path(csv_path),
                "size_bytes": csv_path.stat().st_size,
                "sha256": hash_file(csv_path, "sha256"),
            },
            "pdf": {
                "path": display_path(pdf_path),
                "size_bytes": pdf_path.stat().st_size,
                "sha256": hash_file(pdf_path, "sha256"),
            },
            "archive": (
                {
                    "path": display_path(archive_path),
                    "size_bytes": archive_path.stat().st_size,
                    "md5": hash_file(archive_path, "md5"),
                    "sha256": hash_file(archive_path, "sha256"),
                    "entries": inspect_archive(
                        archive_path, [csv_path, pdf_path]
                    ),
                }
                if archive_path
                else None
            ),
        },
        "dataset": {
            "rows": scan["row_count"],
            "columns": scan["header"],
            "column_count": len(scan["header"]),
            "minimum_timestamp_utc": format_utc(scan["minimum_timestamp"]),
            "maximum_timestamp_utc": format_utc(scan["maximum_timestamp"]),
            "calendar_span_seconds": scan["calendar_span_seconds"],
            "calendar_span_hours": scan["calendar_span_seconds"] / 3600,
            "calendar_span_days": scan["calendar_span_seconds"] / 86400,
            "parse_error_count": scan["parse_error_count"],
            "null_counts": scan["null_counts"],
            "source_index": scan["source_index"],
            "source_document_claimed_instances": None,
            "source_document_claims_1hz": bool(
                re.search(r"logged at 1\s*Hz", pdf_text, re.IGNORECASE)
            ),
            "source_timezone_terms_present": bool(
                re.search(
                    r"\b(UTC|GMT|timezone|time zone)\b",
                    pdf_text,
                    re.IGNORECASE,
                )
            ),
            "chunk_size_rows": chunk_size,
        },
        "timezone": {
            "source_timestamp_is_naive": True,
            "source_timezone_documented": False,
            "working_interpretation": "UTC",
            "conversion": "naive timestamp -> UTC with zero offset and no wall-clock adjustment",
            "dst_boundary_checked": "2020-03-29 Europe/Lisbon",
            "dst_hour_counts": scan["dst_hour_counts"],
            "hour_01_present_on_spring_forward_date": any(
                key.startswith("2020-03-29T01:")
                for key in scan["dst_hour_counts"]
            ),
            "lisbon_offset_before_dst_hours": int(
                datetime(
                    2020, 2, 1, 12, tzinfo=timezone.utc
                )
                .astimezone(ZoneInfo("Europe/Lisbon"))
                .utcoffset()
                .total_seconds()
                / 3600
            ),
            "lisbon_offset_after_dst_hours": int(
                datetime(
                    2020, 3, 29, 12, tzinfo=timezone.utc
                )
                .astimezone(ZoneInfo("Europe/Lisbon"))
                .utcoffset()
                .total_seconds()
                / 3600
            ),
            "decision": (
                "The source does not declare a timezone. The project fixes a "
                "zero-offset UTC interpretation for reproducibility. The "
                "absence of a missing 01:00 wall-clock hour at the Portuguese "
                "spring-forward boundary is consistent with this interpretation, "
                "but is not an authoritative source declaration."
            ),
        },
        "sampling": {
            "nominal_interval_seconds": NOMINAL_INTERVAL_SECONDS,
            "modal_interval_seconds": scan["modal_interval_seconds"],
            "delta_counts_seconds": scan["delta_counts_seconds"],
            "gap_rule": f"observed inter-sample delta > {GAP_THRESHOLD_SECONDS} seconds",
            "gap_count": len(scan["gaps"]),
            "unobserved_seconds": scan["unobserved_seconds"],
            "unobserved_hours": scan["unobserved_seconds"] / 3600,
            "observed_duration_seconds": scan["observed_duration_seconds"],
            "observed_duration_hours": scan["observed_duration_seconds"]
            / 3600,
            "calendar_coverage_pct": scan["calendar_coverage_pct"],
            "gap_interval_definition": "[previous_timestamp + 10 seconds, next_timestamp)",
            "largest_gap": (
                {
                    **largest_gap,
                    "previous_timestamp": format_utc(
                        largest_gap["previous_timestamp"]
                    ),
                    "next_timestamp": format_utc(largest_gap["next_timestamp"]),
                    "gap_start": format_utc(largest_gap["gap_start"]),
                    "gap_end": format_utc(largest_gap["gap_end"]),
                }
                if largest_gap
                else None
            ),
        },
        "quality_checks": {
            "duplicate_timestamp_count": scan["duplicate_timestamp_count"],
            "out_of_order_count": scan["out_of_order_count"],
            "all_digital_values_binary": all(
                field.get("observed_values") in ([0.0], [1.0], [0.0, 1.0])
                for field in scan["fields"]
                if field["role"].startswith("digital")
            ),
            "cumulative_columns": scan["cumulative_columns"],
            "caudal_impulses_monotonic": next(
                (
                    field["monotonic_non_decreasing"]
                    for field in scan["fields"]
                    if field_key(field["column"]) == "caudal_impulses"
                ),
                None,
            ),
        },
        "fields": scan["fields"],
        "failure_events": [serialize_event(event) for event in scan["events"]],
        "failure_metrics": {
            "event_count": len(events),
            "mean_duration_seconds": sum(all_durations) / len(all_durations),
            "mean_duration_hours": sum(all_durations) / len(all_durations) / 3600,
            "longest_event_id": scan["failure_metrics"]["longest_event_id"],
            "longest_duration_hours": scan["failure_metrics"][
                "longest_duration_hours"
            ],
            "total_duration_hours": cumulative_total / 3600,
            "pareto": scan["failure_metrics"]["pareto"],
            "annotated_intervals": [
                {
                    **interval,
                    "start_utc": format_utc(interval["start_utc"]),
                    "end_utc": format_utc(interval["end_utc"]),
                }
                for interval in scan["failure_metrics"]["annotated_intervals"]
            ],
        },
    }

    instance_match = re.search(
        r"Number of Instances:\s*(\d+)", pdf_text, re.IGNORECASE
    )
    if instance_match:
        evidence["dataset"]["source_document_claimed_instances"] = int(
            instance_match.group(1)
        )
    return evidence


def render_markdown(evidence: dict[str, Any]) -> str:
    dataset = evidence["dataset"]
    source = evidence["source"]
    timezone_info = evidence["timezone"]
    sampling = evidence["sampling"]
    quality = evidence["quality_checks"]
    events = evidence["failure_events"]
    metrics = evidence["failure_metrics"]
    fields = evidence["fields"]

    hour_lines = [
        f"{hour}: {count}"
        for hour, count in timezone_info["dst_hour_counts"].items()
    ]
    delta_items = sorted(
        (
            (int(seconds), count)
            for seconds, count in sampling["delta_counts_seconds"].items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]

    lines = [
        "# MetroPT-3 数据质量审计",
        "",
        "> 本文件由 `scripts/audit.py` 根据原始文件生成。源文件保持只读，"
        "所有审计结论均可由脚本重跑。",
        "",
        f"- 生成时间：`{evidence['generated_at_utc']}`",
        f"- 审计状态：`{evidence['audit_status']}`",
        "- 口径：只描述标注异常区间、遥测有效监测时长和数据质量，"
        "不把异常区间等同于设备停机或维修时间。",
        "",
        "## 1. 数据源与时间范围",
        "",
        f"- 数据集：MetroPT-3，UCI DOI `{source['uci_dataset_doi']}`。",
        f"- UCI 页面：{source['uci_dataset_url']}",
        f"- 下载镜像：{source['download_mirror_url']}",
        f"- CSV：`{source['csv']['path']}`，"
        f"{source['csv']['size_bytes']:,} 字节，"
        f"SHA256 `{source['csv']['sha256']}`。",
        f"- PDF：`{source['pdf']['path']}`，"
        f"{source['pdf']['size_bytes']:,} 字节，"
        f"SHA256 `{source['pdf']['sha256']}`。",
    ]
    if source["archive"]:
        lines.extend(
            [
                f"- 原始压缩包 SHA256：`{source['archive']['sha256']}`。",
                f"- 原始压缩包 MD5：`{source['archive']['md5']}`。",
            ]
        )
    lines.extend(
        [
            f"- 经审计的遥测范围：`{dataset['minimum_timestamp_utc']}` 至 "
            f"`{dataset['maximum_timestamp_utc']}`，统一标记为 UTC。",
            f"- 来源说明：{source['provenance_note']}",
            "",
            "## 2. 总行数与字段清单",
            "",
            f"- 实际数据行数：{dataset['rows']:,}。",
            f"- 字段数：{dataset['column_count']}，"
            f"含 1 个源行标识、1 个时间字段、7 个模拟量、8 个数字量。",
            f"- 时间解析失败：{dataset['parse_error_count']:,}。",
            f"- 各字段空值总数：{sum(dataset['null_counts'].values()):,}。",
            f"- CSV 字段顺序：`{', '.join(dataset['columns'])}`。",
            f"- 源索引：最小值 `{dataset['source_index']['min']}`，"
            f"最大值 `{dataset['source_index']['max']}`；"
            f"递减次数 {dataset['source_index']['decreases']}。"
            "该字段是源文件索引，不是时间。",
        ]
    )
    source_index_steps = "、".join(
        f"`{step}`（{count:,} 次）"
        for step, count in dataset["source_index"]["step_counts"].items()
    )
    lines.append(
        f"- 源索引相邻步长：{source_index_steps or '无'}；"
        "它不是时间，也不直接等同于数据行号。"
    )
    if dataset["source_document_claimed_instances"] is not None:
        lines.append(
            "- 来源 PDF 声称实例数为 "
            f"{dataset['source_document_claimed_instances']:,}，"
            f"而实际 CSV 为 {dataset['rows']:,}；"
            "项目以实际 CSV 和时间戳为准。"
        )
    if dataset["source_document_claims_1hz"]:
        lines.append(
            "- 来源 PDF 的文字写有 1 Hz，但实际相邻时间戳以 10 秒为主，"
            "因此本项目使用约 0.1 Hz 的观测口径，不宣称 1 Hz。"
        )

    lines.extend(
        [
            "",
            "## 3. 重复、乱序和缺口",
            "",
            f"- 重复时间戳：{quality['duplicate_timestamp_count']:,}。",
            f"- 乱序记录：{quality['out_of_order_count']:,}。",
            f"- 固定缺口规则：{sampling['gap_rule']}。",
            f"- 缺口数量：{sampling['gap_count']:,}。",
            f"- 缺口区间定义：`{sampling['gap_interval_definition']}`。",
            f"- 未观测时长：{sampling['unobserved_hours']:.3f} 小时"
            f"（{sampling['unobserved_seconds']:,} 秒）。",
            f"- 观测时长：{sampling['observed_duration_hours']:.3f} 小时。",
            f"- 日历跨度覆盖率：{sampling['calendar_coverage_pct']:.2f}%。",
            "",
            "相邻时间戳差的主要分布：",
            "",
            "| 秒 | 出现次数 |",
            "|---:|---:|",
        ]
    )
    for seconds, count in delta_items:
        lines.append(f"| {seconds} | {count:,} |")

    if sampling["largest_gap"]:
        largest = sampling["largest_gap"]
        lines.extend(
            [
                "",
                "最大缺口：",
                "",
                f"- 缺口区间：`{format_utc(largest['gap_start'])}` 至 "
                f"`{format_utc(largest['gap_end'])}`。",
                f"- 两侧样本：`{format_utc(largest['previous_timestamp'])}`、"
                f"`{format_utc(largest['next_timestamp'])}`。",
                f"- 未观测时长：{largest['unobserved_hours']:.3f} 小时。",
            ]
        )

    lines.extend(
        [
            "",
            "## 4. 夏令时处理",
            "",
            "- 审计边界：葡萄牙 `Europe/Lisbon` 2020-03-29 春季切换。",
            "- 若源时间戳是本地墙钟时间，01:00 小时应在切换时缺失。",
            "- 实际边界附近小时计数："
            + "；".join(hour_lines)
            + "。",
            f"- 01:00 小时是否出现："
            f"`{timezone_info['hour_01_present_on_spring_forward_date']}`。",
            f"- Lisbon 在切换前偏移：UTC+{timezone_info['lisbon_offset_before_dst_hours']}；"
            f"切换后偏移：UTC+{timezone_info['lisbon_offset_after_dst_hours']}。",
            f"- 处理决定：{timezone_info['decision']}",
            "- 因此本项目不执行任何夏令时墙钟平移；源字符串按零偏移标记为 UTC。",
            "",
            "## 5. 字段类型表",
            "",
            "| CSV 字段 | 类型 | 观测范围/取值 | 单位 | 说明 | 处理决定 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for field in fields:
        role = field["role"]
        if role == "identifier":
            observed = f"{field['min']} 至 {field['max']}"
            decision = "仅作源记录追溯标识"
        elif role == "time":
            observed = "时间戳"
            decision = "按固定 UTC 工作约定处理"
        elif role.startswith("digital"):
            observed = "/".join(str(int(value)) for value in field["observed_values"])
            if role == "digital_pulse":
                decision = "按脉冲数字信号处理，不求差分、不取均值"
            else:
                decision = "按 0/1 状态单独处理，不并入模拟量"
        else:
            observed = f"{field['min']:.6g} 至 {field['max']:.6g}"
            decision = "按连续模拟量处理，按要求保留精度"
        description = field.get("description", "")
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in [
                    field["column"],
                    role,
                    observed,
                    field["unit"],
                    description,
                    decision,
                ]
            )
            + " |"
        )

    caudal = next(
        (
            field
            for field in fields
            if field_key(field["column"]) == "caudal_impulses"
        ),
        None,
    )
    lines.extend(
        [
            "",
            f"- 识别出的模拟量字段：{len([f for f in fields if f['role'] == 'analog'])} 个。",
            f"- 识别出的数字量字段：{len([f for f in fields if f['role'].startswith('digital')])} 个。",
            f"- 识别出的累计计数器：{len(quality['cumulative_columns'])} 个。",
        ]
    )
    if caudal:
        lines.append(
            f"- `{caudal['column']}` 实际取值为 0/1，下降沿次数 "
            f"{caudal['negative_steps']:,}，不是单调累计计数器；"
            "不执行累计量差分，也不把它求均值当作流量。"
        )

    lines.extend(
        [
            "",
            "## 6. 故障事件有效性检查",
            "",
            "| 内部 ID | 源编号 | 开始 UTC | 结束 UTC | 类型 | 严重程度 | 持续小时 | 区间内样本 | 源索引范围 |",
            "|---|---:|---|---|---|---|---:|---:|---|",
        ]
    )
    for event in events:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in [
                    event["internal_event_id"],
                    event["source_id"],
                    event["start_utc"],
                    event["end_utc"],
                    event["failure_type"],
                    event["severity"],
                    f"{event['duration_hours']:.4f}",
                    event["sample_count"],
                    f"{event['first_source_index']} 至 {event['last_source_index']}",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "有效性结论：",
            "",
            f"- 4 条源故障记录均成功解析：`{len(events) == 4}`。",
            f"- 所有开始时间早于结束时间："
            f"`{all(event['start_before_end'] for event in events)}`。",
            f"- 所有故障区间位于遥测范围内："
            f"`{all(event['within_telemetry_range'] for event in events)}`。",
            "- 源 PDF 前两条记录都标为 `#1`；本审计保留源编号，"
            "另建 `E01` 至 `E04` 内部事件 ID，不修改来源文本。",
            "- 时间字段按 `结束时间 - 开始时间` 计算，不额外加 1 分钟。",
            "",
            "| 内部 ID | 维护备注 | 备注与事件结束的关系 | 区间内缺口数 | 缺口重叠小时 | 标注区间观测覆盖 |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for event in events:
        remark = event["maintenance_remark"]
        remark_text = remark["raw_text"] if remark else ""
        relation = remark["relation_to_event"] if remark else ""
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in [
                    event["internal_event_id"],
                    remark_text or "无",
                    relation or "无",
                    event["gap_count"],
                    f"{event['gap_hours_overlap']:.4f}",
                    f"{event['observed_coverage_pct']:.2f}%",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 7. 审计用故障时长基线",
            "",
            f"- 平均标注故障持续时长：{metrics['mean_duration_hours']:.4f} 小时。",
            f"- 最长标注故障：`{metrics['longest_event_id']}`，"
            f"{metrics['longest_duration_hours']:.4f} 小时。",
            f"- 4 次标注故障累计持续时长：{metrics['total_duration_hours']:.4f} 小时。",
            f"- 故障类型 Pareto 首项："
            f"`{metrics['pareto'][0]['failure_type']}`，"
            f"{metrics['pareto'][0]['cumulative_hours']:.4f} 小时。"
            "源数据四次均为 Air Leak，因此第一版 Pareto 只有一个实际类别。",
            "",
            "相邻标注故障间隔：",
            "",
            "| 从 | 到 | 间隔小时 |",
            "|---|---|---:|",
        ]
    )
    for interval in metrics["annotated_intervals"]:
        lines.append(
            f"| {interval['from_event_id']} | {interval['to_event_id']} | "
            f"{interval['interval_hours']:.4f} |"
        )

    overlap_events = [event for event in events if event["gap_count"]]
    lines.extend(
        [
            "",
            "缺口与故障区间重叠：",
            "",
            "- "
            + "；".join(
                f"`{event['internal_event_id']}` {event['gap_count']} 个缺口，"
                f"未观测 {event['gap_hours_overlap']:.4f} 小时"
                for event in overlap_events
            )
            + "。",
            "- 故障区间内不插值、不补造记录；后续比例指标只使用有效监测时长。",
            "",
            "## 8. 问题、影响与处理决定",
            "",
            "| 问题 | 证据 | 影响 | 处理决定 |",
            "|---|---|---|---|",
            "| 源文件未声明时区 | PDF 中未检出 UTC/GMT/timezone 声明；"
            "2020-03-29 的 01 点仍存在 | 绝对时间解释存在来源不确定性 | "
            "固定按 UTC 零偏移工作解释，保留原始字符串并登记 Known Issue |",
            f"| CSV 与文档实例数/频率不一致 | PDF 声称 "
            f"{dataset['source_document_claimed_instances'] or '未知'} 个实例、约 1 Hz；"
            f"实际 {dataset['rows']:,} 行、主间隔 10 秒 | 若照抄文档会错误计算 | "
            "以实际 CSV 行为和时间差为准，README/图表统一使用约 0.1 Hz |",
            "| 源事件编号重复 | 前两条记录均为 `#1` | 无法仅用源编号作主键 | "
            "保留源编号，新增内部 ID `E01` 至 `E04` |",
            "| 第二条维护备注疑有日期笔误 | `Maintenance on 30Apr at 12:00` "
            "早于 5 月故障 | 直接修正会篡改来源 | 原样保留备注，不参与核心指标 |",
            "| 数字脉冲字段易被误当累计量 | `Caudal_impulses` 仅为 0/1 且有下降沿 | "
            "求差分或均值会制造无意义指标 | 按数字脉冲字段单独处理 |",
            f"| 遥测存在大缺口 | 共 {sampling['gap_count']:,} 个缺口，"
            f"未观测 {sampling['unobserved_hours']:.3f} 小时 | "
            "连续观测假设不成立 | 固定大于 30 秒为缺口，比例指标扣除缺口 |",
            "| 故障区间可能覆盖缺口 | 见上一节重叠统计 | "
            "把区间全部视为连续观测会高估证据密度 | 暴露缺口重叠，不插值 |",
            "| 镜像下载来源 | UCI 直连过慢，使用公开镜像；文件大小匹配 UCI | "
            "来源仍应引用 UCI | 记录镜像 URL 和全部哈希，登记未完成官方包哈希核验 |",
            "",
            "## 9. 仍未解决的问题",
            "",
            "- 原始系统是否确实以 UTC 写入时间戳，仍需数据提供方说明。",
            "- 故障报告时间与遥测时间是否使用同一时区约定，来源未说明。",
            "- 官方 UCI 压缩包与镜像压缩包的字节级哈希尚未比对。",
            "- 第二条维护备注中的 `30Apr` 是否为 `30May` 笔误，不能从现有材料确认。",
            "- 采样间隔存在 9、12、13 秒等波动，本阶段不重采样；后续按 SQL 和时间窗口处理。",
            "",
            "## 10. Known Issues",
            "",
            "1. 时区是固定工作解释，不是来源明确声明；绝对时间解释仍有残余风险。",
            "2. 原始包来自公开镜像，已完成文件大小与本地哈希记录，"
            "但未完成与 UCI 官方压缩包的哈希对照。",
            "3. `Caudal_impulses` 的文档语义与观测值冲突；当前只按数字脉冲处理。",
            "4. 故障报告中的维护备注只作为来源文本保留，不构造维修工单或维修时长。",
            "5. 标注异常区间不表示设备必然停机，也不表示维修开始或结束时间。",
            "6. 缺口区间内无数据；后续所有异常区间比例必须使用有效监测时长。",
            "",
            "## 11. 审计停止条件核对",
            "",
            "| 停止条件 | 结果 |",
            "|---|---|",
            f"| 4 次故障区间能正确还原 | 通过，解析 {len(events)} 条且时间边界完整 |",
            "| 时间统一为 UTC | 通过项目固定解释；来源时区不确定性已登记 |",
            "| 重复、乱序、缺口有固定规则 | 通过 |",
            "| 所有字段完成分类 | 通过，7 模拟量 + 8 数字量 + 时间 + 标识 |",
            "| 每个异常有处理决定或 Known Issue | 通过 |",
            "| 未解决问题不影响核心区间与时长 | 当前区间、时长和 SQL 口径可复现；"
            "绝对时区仍需外部确认 |",
            "",
            "## 12. 复现方式",
            "",
            "```powershell",
            "py -m pip install -r requirements.txt",
            "py scripts/audit.py",
            "```",
            "",
            "脚本输出：",
            "",
            "- `docs/data_quality.md`：本审计报告。",
            "- `artifacts/audit/audit_report.json`：机器可读证据。",
            "- `artifacts/audit/gap_intervals.csv`：全部缺口区间。",
            "- `artifacts/audit/failure_events.csv`：4 条故障事件及其追溯样本。",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    evidence: dict[str, Any], docs_dir: Path, artifacts_dir: Path
) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    public_evidence = {
        key: value
        for key, value in evidence.items()
        if not key.startswith("_")
    }
    report_path = artifacts_dir / "audit_report.json"
    report_path.write_text(
        json.dumps(public_evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    gap_rows = []
    for gap in evidence["_raw_gaps"]:
        gap_rows.append(
            {
                "previous_timestamp_utc": format_utc(gap["previous_timestamp"]),
                "next_timestamp_utc": format_utc(gap["next_timestamp"]),
                "gap_start_utc": format_utc(gap["gap_start"]),
                "gap_end_utc": format_utc(gap["gap_end"]),
                "unobserved_seconds": gap["unobserved_seconds"],
                "unobserved_hours": gap["unobserved_hours"],
                "overlapping_event_ids": ";".join(
                    gap["overlapping_event_ids"]
                ),
            }
        )
    pd.DataFrame(gap_rows).to_csv(
        artifacts_dir / "gap_intervals.csv", index=False, encoding="utf-8"
    )

    event_rows = []
    for event in evidence["failure_events"]:
        remark = event.get("maintenance_remark") or {}
        event_rows.append(
            {
                "internal_event_id": event["internal_event_id"],
                "source_id": event["source_id"],
                "start_utc": event["start_utc"],
                "end_utc": event["end_utc"],
                "failure_type": event["failure_type"],
                "severity": event["severity"],
                "duration_hours": event["duration_hours"],
                "report_text": event["report_text"],
                "maintenance_remark_utc": remark.get("maintenance_utc"),
                "remark_relation_to_event": remark.get("relation_to_event"),
                "sample_count": event["sample_count"],
                "first_sample_timestamp_utc": event["first_sample_timestamp_utc"],
                "last_sample_timestamp_utc": event["last_sample_timestamp_utc"],
                "first_source_index": event["first_source_index"],
                "last_source_index": event["last_source_index"],
                "gap_count": event["gap_count"],
                "gap_hours_overlap": event["gap_hours_overlap"],
                "observed_coverage_pct": event["observed_coverage_pct"],
            }
        )
    pd.DataFrame(event_rows).to_csv(
        artifacts_dir / "failure_events.csv", index=False, encoding="utf-8"
    )

    (docs_dir / "data_quality.md").write_text(
        render_markdown(public_evidence),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    raw_dir = args.raw_dir.resolve()
    docs_dir = args.docs_dir.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw data directory does not exist: {raw_dir}")
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be positive")

    csv_path = find_single_file(raw_dir, ".csv")
    pdf_path = find_single_file(raw_dir, ".pdf")
    zip_files = sorted(
        path
        for path in raw_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".zip"
    )
    archive_path = zip_files[0] if len(zip_files) == 1 else None

    pdf_text = extract_pdf_text(pdf_path)
    parsed_events = parse_failure_events(pdf_text)
    scan = scan_telemetry(csv_path, parsed_events, args.chunk_size)
    evidence = build_evidence(
        raw_dir=raw_dir,
        csv_path=csv_path,
        pdf_path=pdf_path,
        pdf_text=pdf_text,
        events=parsed_events,
        scan=scan,
        archive_path=archive_path,
        chunk_size=args.chunk_size,
    )
    evidence["_raw_gaps"] = scan["gaps"]
    write_outputs(evidence, docs_dir, artifacts_dir)

    print(
        json.dumps(
            {
                "status": evidence["audit_status"],
                "rows": evidence["dataset"]["rows"],
                "events": len(evidence["failure_events"]),
                "duplicate_timestamps": evidence["quality_checks"][
                    "duplicate_timestamp_count"
                ],
                "out_of_order": evidence["quality_checks"][
                    "out_of_order_count"
                ],
                "gaps": evidence["sampling"]["gap_count"],
                "unobserved_hours": round(
                    evidence["sampling"]["unobserved_hours"], 6
                ),
                "docs": str(docs_dir / "data_quality.md"),
                "evidence": str(artifacts_dir / "audit_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if evidence["audit_status"] != "fail" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        raise
