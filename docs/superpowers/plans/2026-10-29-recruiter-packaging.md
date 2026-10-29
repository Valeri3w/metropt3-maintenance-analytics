# MetroPT-3 Recruiter Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a zero-cost, recruiter-facing MetroPT-3 demo and package the existing evidence without changing SQL metrics or core analytics behavior.

**Architecture:** Keep the local full-data Docker Compose workflow. Add a deterministic one-week demo dataset, load it into a free PostgreSQL database, run the existing Streamlit app from a public GitHub repository, and provide recruiter-first documentation and verification artifacts. `DATABASE_URL` and demo-mode configuration are read from Streamlit Secrets in the hosted environment.

**Tech Stack:** Python 3.13, pandas, PostgreSQL 17, psycopg 3, Streamlit, pytest, GitHub, Streamlit Community Cloud, Neon PostgreSQL

---

## File Structure

Create or modify these files:

- `.gitignore`: exclude raw data, secrets, caches, and local database artifacts.
- `.dockerignore`: exclude Git metadata, caches, secrets, and generated local files while preserving current full-data Docker inputs.
- `LICENSE`: MIT license for project code.
- `docs/data_source.md`: separate UCI source attribution from the code license.
- `scripts/export_demo_data.py`: deterministically extract the 2020-06-01 through 2020-06-08 telemetry week and E03 failure record.
- `tests/test_export_demo_data.py`: unit tests for demo filtering and manifest output.
- `data/demo/`: committed one-week telemetry, one-event failure table, and manifest.
- `scripts/load_demo_db.py`: load and validate only the demo week.
- `tests/test_load_demo_db.py`: demo-loader tests.
- `src/metropt/runtime.py`: parse demo mode and apply Streamlit Secrets to environment variables.
- `tests/test_runtime.py`: runtime configuration tests.
- `app.py`: apply runtime secrets before data access and show the representative-subset notice.
- `.streamlit/secrets.toml.example`: credential-free deployment template.
- `README.md`: recruiter-first public entry point.
- `docs/case_study.md`: one-page Chinese project case.
- `docs/deployment.md`: exact Neon, seeding, Secrets, GitHub, and Streamlit deployment steps.
- `docs/demo_script.md`: 90-second demonstration script.
- `docs/resume_bullets.md`: project title and three evidence-based bullets.
- `artifacts/screenshots/demo-subset-desktop.png`: final public-demo screenshot for README.

The existing SQL files, metric functions, chart logic, audit report, and weekly report implementation remain unchanged.

---

## Task 1: Repository Hygiene and Source Attribution

**Files:**
- Create: `.gitignore`
- Create: `.dockerignore`
- Create: `LICENSE`
- Create: `docs/data_source.md`

- [x] **Step 1: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
.env
.streamlit/secrets.toml
test-results/

data/raw/
*.dump
*.sql.gz
*.log

.DS_Store
Thumbs.db
```

- [x] **Step 2: Create `.dockerignore`**

```dockerignore
.git
.gitignore
.venv
**/__pycache__
**/*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.streamlit/secrets.toml
test-results/
artifacts/screenshots
data/raw/*.zip
tests
*.dump
*.sql.gz
*.log
```

Preserve the existing useful exclusions while adding cache, test-result, and
secret coverage. Do not exclude `data/raw` as a directory; the current full-data
Dockerfile needs the raw CSV and PDF for local reproduction. The source ZIP,
tests, and generated screenshots are not Docker build inputs.

- [x] **Step 3: Create MIT `LICENSE`**

```text
MIT License

Copyright (c) 2026 The MetroPT-3 Maintenance Analytics Project Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [x] **Step 4: Create `docs/data_source.md`**

```markdown
# Data Source and Licensing

## Source

- Dataset: MetroPT-3
- Provider: UCI Machine Learning Repository
- DOI: `10.24432/C5VW3R`
- Dataset page: https://archive.ics.uci.edu/dataset/791/metropt+3+dataset

## Repository Data Policy

The repository does not redistribute the complete 208 MB raw CSV or the
complete 27.75 MB source archive. The public demo contains only a deterministic
one-week derived subset in `data/demo/`.

The raw source remains downloadable from UCI. Local reproducibility instructions
are documented in `README.md` and `docs/data_quality.md`.

## License Boundary

The MIT license applies to project code and original documentation. It does not
relicense the MetroPT-3 source dataset. Source-data use remains subject to the
provider's terms and citation requirements.
```

- [x] **Step 5: Verify large files and secrets are ignored**

Run:

```powershell
git check-ignore -v data/raw/metropt3/MetroPT3(AirCompressor).csv
git check-ignore -v data/raw/metropt+3+dataset.zip
git check-ignore -v .streamlit/secrets.toml
git check-ignore -v test-results/.last-run.json
```

Expected: all four paths are ignored.

- [x] **Step 6: Commit the existing project baseline with repository hygiene**

The repository currently tracks only the approved design document. Stage the
complete existing application, SQL, tests, audit evidence, and package files by
explicit path so the public repository will contain a runnable project:

```powershell
git add .gitignore .dockerignore LICENSE docs/data_source.md
git add app.py artifacts docker-compose.yml Dockerfile docs/data_quality.md pyproject.toml README.md requirements.txt scripts sql src tests
git diff --cached --check
git diff --cached --name-only | Select-String -Pattern '^data/raw/|secrets.toml$|\.dump$'
git status --short
git commit -m "chore: establish project baseline and repository hygiene"
```

Expected: `git diff --cached --check` produces no output; the forbidden-path
scan produces no output; `git status --short` shows the explicit staged project
files but no raw data, secrets, caches, or `test-results/`.

---

## Task 2: Deterministic Demo Dataset

**Files:**
- Create: `scripts/export_demo_data.py`
- Create: `tests/test_export_demo_data.py`
- Generate: `data/demo/MetroPT3(AirCompressor)_20200601.csv`
- Generate: `data/demo/failure_events_demo.csv`
- Generate: `data/demo/manifest.json`

- [x] **Step 1: Write failing tests for demo filtering**

Create `tests/test_export_demo_data.py`:

```python
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
```

- [x] **Step 2: Run the tests and verify they fail**

Run:

```powershell
py -m pytest tests/test_export_demo_data.py -v
```

Expected: FAIL because `scripts.export_demo_data` does not exist.

- [x] **Step 3: Implement `scripts/export_demo_data.py`**

```python
#!/usr/bin/env python3
"""Extract the deterministic public-demo week from audited source data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_CSV = (
    PROJECT_ROOT / "data" / "raw" / "metropt3" / "MetroPT3(AirCompressor).csv"
)
DEFAULT_FAILURE_CSV = PROJECT_ROOT / "artifacts" / "audit" / "failure_events.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "demo"

DEMO_START = datetime(2020, 6, 1, tzinfo=timezone.utc)
DEMO_END = datetime(2020, 6, 8, tzinfo=timezone.utc)
DEMO_EVENT_ID = "E03"


def filter_demo_telemetry(frame: pd.DataFrame) -> pd.DataFrame:
    timestamps = pd.to_datetime(frame["timestamp"], errors="raise", utc=True)
    mask = (timestamps >= DEMO_START) & (timestamps < DEMO_END)
    return frame.loc[mask].copy()


def filter_demo_events(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.loc[frame["internal_event_id"] == DEMO_EVENT_ID].copy()
    if result.empty:
        raise ValueError(f"Demo event {DEMO_EVENT_ID} was not found.")
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-csv", type=Path, default=DEFAULT_RAW_CSV)
    parser.add_argument("--failure-csv", type=Path, default=DEFAULT_FAILURE_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[pd.DataFrame] = []
    for frame in pd.read_csv(args.raw_csv, chunksize=args.chunk_size):
        filtered = filter_demo_telemetry(frame)
        if not filtered.empty:
            chunks.append(filtered)
    if not chunks:
        raise ValueError("No telemetry rows fell inside the demo week.")
    telemetry = pd.concat(chunks, ignore_index=True)
    telemetry_path = args.output_dir / "MetroPT3(AirCompressor)_20200601.csv"
    telemetry.to_csv(telemetry_path, index=False)

    events = filter_demo_events(pd.read_csv(args.failure_csv))
    events_path = args.output_dir / "failure_events_demo.csv"
    events.to_csv(events_path, index=False)

    manifest = {
        "demo_start_utc": DEMO_START.isoformat(),
        "demo_end_utc": DEMO_END.isoformat(),
        "event_ids": events["internal_event_id"].tolist(),
        "telemetry_rows": int(len(telemetry)),
        "telemetry_first_timestamp": str(telemetry["timestamp"].iloc[0]),
        "telemetry_last_timestamp": str(telemetry["timestamp"].iloc[-1]),
        "telemetry_sha256": sha256_file(telemetry_path),
        "failure_events_sha256": sha256_file(events_path),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run the unit tests**

Run:

```powershell
py -m pytest tests/test_export_demo_data.py -v
```

Expected: `3 passed`.

- [x] **Step 5: Generate the demo files**

Run:

```powershell
py scripts/export_demo_data.py
```

Expected: `event_ids` equals `["E03"]`, telemetry rows are near 60,000, and the generated CSV is below 20 MB.

- [x] **Step 6: Validate demo bounds and size**

Run:

```powershell
Get-Content -Raw data/demo/manifest.json
Get-ChildItem data/demo | Select-Object Name,Length
```

Expected: E03 only, timestamps inside 2020-06-01 through 2020-06-08, and no file over 100 MB.

- [x] **Step 7: Commit the demo generator and generated files**

```powershell
git add scripts/export_demo_data.py tests/test_export_demo_data.py data/demo
git commit -m "feat: add reproducible public demo dataset"
```

---

## Task 3: Demo Database Loader

**Files:**
- Modify: `scripts/load_db.py`
- Create: `scripts/load_demo_db.py`
- Create: `tests/test_load_demo_db.py`
- Modify: `tests/test_load_db.py`

- [ ] **Step 1: Add a failing test for configurable event count**

Append to `tests/test_load_db.py`:

```python
import inspect

from scripts.load_db import load_failure_events


def test_load_failure_events_exposes_expected_event_count() -> None:
    signature = inspect.signature(load_failure_events)

    assert signature.parameters["expected_events"].default == 4
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
py -m pytest tests/test_load_db.py::test_load_failure_events_exposes_expected_event_count -v
```

Expected: FAIL because `expected_events` is missing.

- [ ] **Step 3: Make the event count configurable**

Change the signature in `scripts/load_db.py` from:

```python
def load_failure_events(connection: Connection[Any], failure_csv: Path) -> int:
```

to:

```python
def load_failure_events(
    connection: Connection[Any],
    failure_csv: Path,
    expected_events: int = 4,
) -> int:
```

Replace the hard-coded four-event check with:

```python
    if len(rows) != expected_events:
        raise ValueError(
            f"Expected {expected_events} failure events, found {len(rows)}."
        )
```

All existing callers keep the default of four.

- [ ] **Step 4: Run loader tests**

Run:

```powershell
py -m pytest tests/test_load_db.py -v
```

Expected: pass, with PostgreSQL integration tests skipped only if the database is unavailable.

- [ ] **Step 5: Create `scripts/load_demo_db.py`**

```python
#!/usr/bin/env python3
"""Load and validate only the committed public-demo week."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from psycopg import Connection

from scripts.load_db import (
    ASSET_ID,
    DEFAULT_AUDIT_REPORT,
    DEFAULT_METRICS_SQL,
    DEFAULT_SCHEMA_SQL,
    load_failure_events,
    load_metrics,
    load_schema,
    load_telemetry,
    query_one,
    upsert_asset,
    validate_metric_views,
    wait_for_database,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DIR = PROJECT_ROOT / "data" / "demo"


def validate_demo_load(
    connection: Connection[Any],
    expected_rows: int,
) -> dict[str, Any]:
    count, minimum, maximum = query_one(
        connection,
        """
        SELECT COUNT(*), MIN(observed_at), MAX(observed_at)
        FROM telemetry
        WHERE asset_id = %s
        """,
        (ASSET_ID,),
    )
    event_ids = [
        row[0]
        for row in connection.execute(
            "SELECT event_id FROM failure_events ORDER BY event_id"
        ).fetchall()
    ]
    if count != expected_rows:
        raise RuntimeError(f"Loaded {count} demo rows, expected {expected_rows}.")
    if event_ids != ["E03"]:
        raise RuntimeError(f"Expected only E03, found {event_ids}.")
    return {
        "telemetry_rows": count,
        "first_observed_at": minimum.isoformat(),
        "last_observed_at": maximum.isoformat(),
        "event_ids": event_ids,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    parser.add_argument("--schema-sql", type=Path, default=DEFAULT_SCHEMA_SQL)
    parser.add_argument("--metrics-sql", type=Path, default=DEFAULT_METRICS_SQL)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument(
        "--dsn",
        default=os.getenv("DATABASE_URL"),
        help="Use only a dedicated demo database.",
    )
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("--confirm-reset", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dsn:
        raise ValueError("Provide --dsn or set DATABASE_URL.")
    if not args.confirm_reset:
        raise ValueError(
            "Refusing to truncate tables without --confirm-reset. "
            "Use only a dedicated demo database."
        )

    manifest = json.loads(
        (args.demo_dir / "manifest.json").read_text(encoding="utf-8")
    )
    expected_rows = int(manifest["telemetry_rows"])
    raw_csv = args.demo_dir / "MetroPT3(AirCompressor)_20200601.csv"
    failure_csv = args.demo_dir / "failure_events_demo.csv"

    connection = wait_for_database(args.dsn, args.wait_seconds)
    try:
        with connection.transaction():
            load_schema(connection, args.schema_sql)
            upsert_asset(connection, args.audit_report)
            load_failure_events(connection, failure_csv, expected_events=1)
            load_telemetry(connection, raw_csv, args.chunk_size)
            load_metrics(connection, args.metrics_sql)
            result = validate_demo_load(connection, expected_rows)
            result["metric_views"] = validate_metric_views(connection)
        connection.commit()
    finally:
        connection.close()

    print(json.dumps({"status": "ok", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Add a demo-manifest test**

Create `tests/test_load_demo_db.py`:

```python
import json

from scripts.load_demo_db import DEFAULT_DEMO_DIR


def test_demo_manifest_identifies_one_complete_week_and_e03() -> None:
    manifest = json.loads(
        (DEFAULT_DEMO_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["demo_start_utc"] == "2020-06-01T00:00:00+00:00"
    assert manifest["demo_end_utc"] == "2020-06-08T00:00:00+00:00"
    assert manifest["event_ids"] == ["E03"]
    assert manifest["telemetry_rows"] > 0
```

- [ ] **Step 7: Run demo-loader tests**

Run:

```powershell
py -m pytest tests/test_load_demo_db.py tests/test_load_db.py -v
```

Expected: pass, with database-dependent tests skipped only when PostgreSQL is unavailable.

- [ ] **Step 8: Commit the demo loader**

```powershell
git add scripts/load_db.py scripts/load_demo_db.py tests/test_load_db.py tests/test_load_demo_db.py
git commit -m "feat: add dedicated demo database loader"
```

---

## Task 4: Streamlit Secrets and Demo Notice

**Files:**
- Create: `src/metropt/runtime.py`
- Create: `tests/test_runtime.py`
- Create: `.streamlit/secrets.toml.example`
- Modify: `app.py`

- [ ] **Step 1: Write failing runtime tests**

Create `tests/test_runtime.py`:

```python
from metropt.runtime import (
    apply_secret_environment,
    demo_mode_from_environment,
    is_demo_mode,
)


def test_apply_secret_environment_sets_only_missing_keys() -> None:
    environ = {"DATABASE_URL": "postgresql://existing"}
    secrets = {
        "DATABASE_URL": "postgresql://secret",
        "METROPT_DEMO_MODE": "true",
    }

    apply_secret_environment(secrets, environ)

    assert environ["DATABASE_URL"] == "postgresql://existing"
    assert environ["METROPT_DEMO_MODE"] == "true"


def test_is_demo_mode_accepts_true_forms() -> None:
    assert is_demo_mode("1") is True
    assert is_demo_mode("true") is True
    assert is_demo_mode("YES") is True
    assert is_demo_mode("false") is False
    assert is_demo_mode(None) is False


def test_demo_mode_from_environment_reads_the_runtime_value(monkeypatch) -> None:
    monkeypatch.setenv("METROPT_DEMO_MODE", "on")

    assert demo_mode_from_environment() is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
py -m pytest tests/test_runtime.py -v
```

Expected: FAIL because `metropt.runtime` does not exist.

- [ ] **Step 3: Implement `src/metropt/runtime.py`**

```python
"""Runtime configuration shared by local and hosted application runs."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from typing import Any


SECRET_ENV_KEYS = ("DATABASE_URL", "METROPT_DEMO_MODE")
TRUE_VALUES = {"1", "true", "yes", "on"}


def apply_secret_environment(
    secrets: Mapping[str, Any],
    environ: MutableMapping[str, str] | None = None,
) -> None:
    target = os.environ if environ is None else environ
    for key in SECRET_ENV_KEYS:
        if key in target:
            continue
        value = secrets.get(key)
        if value is not None:
            target[key] = str(value)


def is_demo_mode(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in TRUE_VALUES


def demo_mode_from_environment() -> bool:
    return is_demo_mode(os.getenv("METROPT_DEMO_MODE"))
```

- [ ] **Step 4: Run runtime tests**

Run:

```powershell
py -m pytest tests/test_runtime.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Apply secrets before data access in `app.py`**

After `sys.path.insert(...)`, add:

```python
from metropt.runtime import (  # noqa: E402
    apply_secret_environment,
    demo_mode_from_environment,
)

try:
    apply_secret_environment(st.secrets)
except Exception:
    pass
```

This block must appear before imports from `metropt.data_access`, because `data_access` reads `DATABASE_URL`.

- [ ] **Step 6: Add the persistent demo notice after the subtitle**

Add after the existing subtitle `st.markdown(...)` block:

```python
if demo_mode_from_environment():
    st.info(
        "在线 Demo 使用 2020-06-01 至 2020-06-07 的代表性完整周数据。"
        "全量 4 次故障与完整审计证据见 README。",
        icon=":material/info:",
    )
```

- [ ] **Step 7: Create `.streamlit/secrets.toml.example`**

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
METROPT_DEMO_MODE = "true"
```

- [ ] **Step 8: Run runtime and dashboard tests**

Run:

```powershell
py -m pytest tests/test_runtime.py tests/test_dashboard.py -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit runtime configuration**

```powershell
git add app.py src/metropt/runtime.py tests/test_runtime.py .streamlit/secrets.toml.example
git commit -m "feat: support hosted secrets and demo mode"
```

---

## Task 5: Local Demo Verification

**Files:**
- Generate: `artifacts/screenshots/demo-subset-desktop.png`

- [ ] **Step 1: Start an isolated PostgreSQL demo project**

Run:

```powershell
$env:METROPT_DB_PORT = '5436'
docker compose -p metropt3-demo up -d postgres
docker compose -p metropt3-demo ps
```

Expected: `metropt3-demo-postgres-1` is healthy on host port `5436`.

- [ ] **Step 2: Load the demo week into the isolated database**

Run:

```powershell
py scripts/load_demo_db.py --dsn postgresql://metropt:metropt@127.0.0.1:5436/metropt --confirm-reset
```

Expected: status `ok`, `event_ids: ["E03"]`, and a row count matching `data/demo/manifest.json`.

- [ ] **Step 3: Start the demo app in a separate terminal**

Run:

```powershell
$env:DATABASE_URL = 'postgresql://metropt:metropt@127.0.0.1:5436/metropt'
$env:METROPT_DEMO_MODE = 'true'
py -m streamlit run app.py --server.port 8502 --server.headless true
```

Expected: Streamlit reports `http://localhost:8502`.

- [ ] **Step 4: Verify health and capture the screenshot**

In another terminal, run:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8502/_stcore/health'
npx playwright screenshot --viewport-size="1440,900" "http://127.0.0.1:8502" artifacts/screenshots/demo-subset-desktop.png
```

Expected: health returns `ok`; the screenshot shows the subset notice and E03.

- [ ] **Step 5: Inspect the image**

Open `artifacts/screenshots/demo-subset-desktop.png`.

Expected: the page clearly says the demo is a representative week and does not imply that the one-week subset is the full dataset.

- [ ] **Step 6: Stop the demo app and isolated project**

Stop the Streamlit terminal with `Ctrl+C`, then run:

```powershell
docker compose -p metropt3-demo down -v
```

Expected: the isolated project is removed and the full local `metropt3` database is untouched.

- [ ] **Step 7: Commit the screenshot**

```powershell
git add artifacts/screenshots/demo-subset-desktop.png
git commit -m "docs: add hosted demo screenshot"
```

---

## Task 6: Recruiter-Facing Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/case_study.md`
- Create: `docs/demo_script.md`
- Create: `docs/resume_bullets.md`
- Create: `docs/deployment.md`

- [ ] **Step 1: Insert the recruiter-first block into `README.md`**

Insert immediately after the existing project title:

```markdown
> 工业设备维护数据分析项目：把 151 万行遥测和 4 次故障报告转换成可追溯的维护周报。

[部署与在线 Demo 说明](docs/deployment.md) · [一页案例](docs/case_study.md) · [90 秒演示脚本](docs/demo_script.md) · [数据质量审计](docs/data_quality.md)

**核心结果：** 4 次标注故障 · 最长事件 E03 为 52.5 h · 标注异常区间占有效监测时长 2.08%

**我完成的工作：** 数据审计、PostgreSQL 入库、SQL 指标、事件溯源、Streamlit 看板、周报导出、n=1 业务对比。

**边界：** 仅一台设备、4 次事件；在线 Demo 使用一个完整代表性周；不计算 OEE、MTTR 或可用率，不提供预测、诊断或成本节省结论。
```

Keep existing detailed README sections below this block. After deployment, Task 8 replaces the deployment link with the actual public Demo URL.

- [ ] **Step 2: Create `docs/case_study.md`**

```markdown
# 工业设备维护数据分析平台案例

## 业务问题

维护工程师需要从约 151 万行空压机遥测和 4 条公开故障报告中整理周报。原流程依赖手工筛选、时间差公式和个人经验，难以复现指标，也难以证明结论来自哪一条源记录。

## 方案

项目建立一条可追溯分析链：原始文件审计、PostgreSQL 入库、SQL 指标、Streamlit 看板和 HTML/Markdown 周报。看板支持周期筛选、故障时间轴、事件明细、源索引与 CSV 行号追溯，以及采集缺口提示。

## 数据质量

- 识别 331 个采集缺口，共 908.598 小时未观测。
- 固定缺口阈值大于 30 秒，不插值、不补造记录。
- 区分模拟量、数字量和脉冲量，避免错误聚合。
- 记录时区、来源镜像、字段语义和未解决问题。

## 指标口径

项目计算标注故障持续时长、平均和最长持续时长、相邻标注故障间隔，以及标注异常区间占有效监测时长比例。这些指标不等于停机、维修或可靠性指标。

## 验证

同一 Demo 周使用 Excel 和平台完成周报及两个固定问题。公开结果明确记录操作步骤、耗时、答案一致性和追溯差异，并将其定义为个人 n=1 自我实验，不外推为普遍收益。

## 限制

只有一台设备和 4 次故障；不计算 OEE、MTTR 或可用率；不提供预测、诊断、成本节省或车队推广结论。在线 Demo 使用完整代表性周，全量结论保留在仓库证据中。
```

- [ ] **Step 3: Create `docs/demo_script.md`**

```markdown
# 90 秒演示脚本

## 0-10 秒：定位

“这是工业设备维护数据分析项目。我把 MetroPT-3 的遥测和故障报告做成了一条可追溯的维护周报链。在线版本使用 2020 年 6 月 1 日到 7 日的一个完整代表性周。”

## 10-25 秒：业务问题

“维护人员原本要在 Excel 中筛事件、算持续时长、检查缺口，再手工整理周报。难点不是画图，而是统一口径并证明结果来自哪里。”

## 25-45 秒：核心结果

打开 `运行总览`，展示 E03 的 52.5 小时标注持续时长、事件时间轴和当前周数据质量指标。

## 45-60 秒：技术链路

说明 PostgreSQL 保存结构化遥测与事件，SQL 生成指标，Streamlit 只读取预聚合结果，不把 151 万行一次性读入 pandas。

## 60-75 秒：追溯

打开 `事件追溯`，展示事件 ID、源索引、CSV 行号、首尾样本和重叠缺口。

## 75-90 秒：周报与边界

打开 `周报导出`，展示 HTML 下载，然后说明：“这不是预测，也不计算 OEE、MTTR 或可用率。项目价值是口径统一、查询可复现和记录可追溯。”
```

- [ ] **Step 4: Create `docs/resume_bullets.md`**

```markdown
# 简历项目条目

## 标题

工业设备维护数据分析平台｜Python / PostgreSQL / SQL / Streamlit

## 要点

- 审计约 151 万行工业设备遥测和 4 条故障报告，处理时区、331 个采集缺口、字段类型与事件边界，并形成可重复的数据质量报告。
- 设计 PostgreSQL 数据模型与 SQL 指标，构建事件时间轴、源索引与 CSV 行号追溯、周期筛选及 HTML/Markdown 维护周报。
- 通过 31 项自动化测试和 n=1 人工/平台对比验证结果，明确区分标注异常区间、停机、维修时间与预测能力边界。
```

- [ ] **Step 5: Create the initial `docs/deployment.md`**

```markdown
# 零成本公开部署

## 目标架构

`GitHub -> Streamlit Community Cloud -> Neon PostgreSQL`

公开环境只加载 `data/demo/` 中的完整代表性周，不加载 208 MB 原始 CSV。

## 1. GitHub

1. 在 GitHub 创建公开仓库 `metropt3-maintenance-analytics`。
2. 设置远程并推送 `main` 分支。
3. 确认仓库中不存在 `data/raw/`、`.streamlit/secrets.toml`、数据库 dump 或明文连接串。

## 2. Neon

1. 创建一个免费 PostgreSQL 项目。
2. 从连接详情复制带 `sslmode=require` 的连接串。
3. 将连接串仅保存到本机环境变量 `DEMO_DATABASE_URL`。
4. 执行 Demo loader，将连接串指向专用 Demo 数据库。

## 3. Streamlit Community Cloud

1. 从公开 GitHub 仓库创建应用。
2. 入口文件设置为 `app.py`。
3. Python 版本选择 3.13。
4. 在 Secrets 中写入 `DATABASE_URL` 和 `METROPT_DEMO_MODE = "true"`。
5. 部署后检查首页提示、E03、事件追溯和周报下载。

## 4. 更新 README

将 `README.md` 的部署说明链接替换为 Streamlit 提供的公开 URL，并确认未登录用户可以访问。

## 5. 安全检查

- Neon 密码只存在于 Streamlit Secrets。
- `.streamlit/secrets.toml` 未被 Git 跟踪。
- 原始 CSV 未被 Git 跟踪。
- 公开 Demo 固定为一个完整周，并显示代表性子集提示。
```

- [ ] **Step 6: Validate documentation links and banned claims**

Run:

```powershell
rg -n "OEE|MTTR|availability|可用率|预测|诊断|成本节省|MBTF|MTBF" README.md docs/case_study.md docs/demo_script.md docs/resume_bullets.md docs/deployment.md
```

Expected: terms appear only in explicit limitation or non-goal statements.

- [ ] **Step 7: Commit recruiter documentation**

```powershell
git add README.md docs/case_study.md docs/demo_script.md docs/resume_bullets.md docs/deployment.md
git commit -m "docs: add recruiter-facing project package"
```

---

## Task 7: GitHub, Neon, and Streamlit Deployment

**External resources:**
- Public GitHub repository
- Free Neon PostgreSQL project
- Streamlit Community Cloud account

**Environment variables required from the user:**
- `REPO_URL`: HTTPS clone URL of the new public GitHub repository.
- `DEMO_DATABASE_URL`: Neon pooled PostgreSQL connection string ending with `sslmode=require`.
- `PUBLIC_DEMO_URL`: HTTPS URL returned by Streamlit Community Cloud.

- [ ] **Step 1: Create the public GitHub repository**

In GitHub, create a public repository named `metropt3-maintenance-analytics`. Do not initialize it with a README, license, or ignore file.

Set the remote in PowerShell:

```powershell
$env:REPO_URL = 'https://github.com/YOUR_ACCOUNT/metropt3-maintenance-analytics.git'
git remote add origin $env:REPO_URL
git branch -M main
git push -u origin main
```

Replace `YOUR_ACCOUNT` with the authenticated GitHub account shown in the repository URL. Expected: the complete local commit history is pushed to `main`.

- [ ] **Step 2: Create the Neon database**

Create a free Neon PostgreSQL project named `metropt3-demo`. Copy the pooled connection string into the current PowerShell session:

```powershell
$env:DEMO_DATABASE_URL = 'postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require'
```

Use the actual values displayed by Neon. Do not write this value into a tracked file.

- [ ] **Step 3: Load the one-week demo data into Neon**

Run:

```powershell
py scripts/load_demo_db.py --dsn $env:DEMO_DATABASE_URL --confirm-reset
```

Expected: `status: ok`, one event `E03`, and a telemetry count matching `data/demo/manifest.json`.

- [ ] **Step 4: Create the Streamlit Community Cloud app**

In Streamlit Community Cloud:

1. Choose `New app`.
2. Select the public `metropt3-maintenance-analytics` repository.
3. Set branch to `main`.
4. Set main file path to `app.py`.
5. Select Python 3.13.
6. Open Advanced settings and paste:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
METROPT_DEMO_MODE = "true"
```

Use the exact Neon URL from `DEMO_DATABASE_URL` in the first value. Replace the example URL completely; do not keep the words `USER`, `PASSWORD`, `HOST`, or `DATABASE`.

- [ ] **Step 5: Verify the deployment before editing README**

Open the deployed app in a private browser window and verify:

1. The page shows the representative-subset notice.
2. E03 and 52.5 h are visible.
3. Event trace opens.
4. HTML weekly report downloads.
5. No database error is displayed.

Copy the public Streamlit URL into PowerShell:

```powershell
$env:PUBLIC_DEMO_URL = 'https://YOUR_APP.streamlit.app'
```

- [ ] **Step 6: Add the verified public Demo link to README**

Use `apply_patch` to replace the first standalone line containing `[部署与在线 Demo 说明](docs/deployment.md)` with:

```markdown
[在线 Demo](PUBLIC_DEMO_URL) · [部署说明](docs/deployment.md) · [一页案例](docs/case_study.md) · [90 秒演示脚本](docs/demo_script.md) · [数据质量审计](docs/data_quality.md)
```

Replace the literal token `PUBLIC_DEMO_URL` with the exact value stored in `$env:PUBLIC_DEMO_URL`, without angle brackets or quotation marks. Do not commit the token or any `$env:` reference itself.

- [ ] **Step 7: Commit and push the verified Demo link**

```powershell
git add README.md
git commit -m "docs: link verified public demo"
git push
```

Expected: Streamlit redeploys from the new commit and the README contains the working public URL.

---

## Task 8: Final Verification and Handoff

**Files:**
- Modify: `README.md` only if verification finds a broken link or incorrect statement.

- [ ] **Step 1: Run the complete test suite**

Run:

```powershell
$env:DATABASE_URL = 'postgresql://metropt:metropt@127.0.0.1:5434/metropt'
py -m pytest -q
```

Expected: all 31 collected tests pass; no failures or errors. Record the exact
summary line. If the count differs, stop and reconcile the added tests before
continuing. Then update any stale test-count statement in `README.md` and
`docs/resume_bullets.md` to the observed result.

- [ ] **Step 2: Run focused packaging tests**

Run:

```powershell
py -m pytest tests/test_export_demo_data.py tests/test_load_demo_db.py tests/test_runtime.py -v
```

Expected: all packaging tests pass.

- [ ] **Step 3: Verify secrets and raw data are not tracked**

Run:

```powershell
git ls-files | Select-String -Pattern '^data/raw/|secrets.toml$|\.dump$'
```

Expected: no output.

- [ ] **Step 4: Verify repository file sizes**

Run:

```powershell
git ls-files | ForEach-Object { Get-Item $_ } | Sort-Object Length -Descending | Select-Object -First 10 FullName,Length
```

Expected: no tracked file reaches GitHub's 100 MB per-file limit.

- [ ] **Step 5: Verify the public app health endpoint**

Run:

```powershell
Invoke-RestMethod "$env:PUBLIC_DEMO_URL/_stcore/health"
```

Expected: `ok`.

- [ ] **Step 6: Capture final public evidence**

Run:

```powershell
npx playwright screenshot --viewport-size="1440,900" "$env:PUBLIC_DEMO_URL" artifacts/screenshots/public-demo-desktop.png
```

Expected: the public app loads with the representative-subset notice and the Demo week visible.

- [ ] **Step 7: Inspect final README links**

Run against the recruiter-facing documents only. The implementation plan
intentionally contains deployment placeholders and is not part of the public
verification surface.

```powershell
rg -n "PUBLIC_DEMO_URL|YOUR_APP|YOUR_ACCOUNT|USER:PASSWORD" README.md docs/case_study.md docs/deployment.md docs/demo_script.md docs/resume_bullets.md
```

Expected: no output. Then inspect the first 40 lines of `README.md` and confirm
the online Demo link is the verified public URL rather than a placeholder.

- [ ] **Step 8: Commit final verification evidence**

```powershell
git add README.md docs/resume_bullets.md artifacts/screenshots/public-demo-desktop.png
git commit -m "docs: finalize public verification evidence"
git push
```

If neither documentation file needed correction, the commit still records the
new public-demo screenshot.

- [ ] **Step 9: Confirm clean Git state**

Run:

```powershell
git status --short
```

Expected: no output.
