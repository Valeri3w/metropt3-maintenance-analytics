# MetroPT-3 空压机标注故障分析与维护决策支持平台

> 工业设备维护数据分析项目：把 151 万行遥测和 4 次故障报告转换成可追溯的维护周报。

[在线 Demo](https://metropt3-maintenance-analytics.streamlit.app/) · [部署说明](docs/deployment.md) · [一页案例](docs/case_study.md) · [90 秒演示脚本](docs/demo_script.md) · [数据质量审计](docs/data_quality.md)

**核心结果：** 4 次标注故障 · 最长事件 E03 为 52.5 h · 标注异常区间占有效监测时长 2.08%

**我完成的工作：** 数据审计、PostgreSQL 入库、SQL 指标、事件溯源、Streamlit 看板、周报导出、n=1 业务对比。

**边界：** 仅一台设备、4 次事件；在线 Demo 使用一个完整代表性周；不计算 OEE、MTTR 或可用率，不提供预测、诊断或成本节省结论。

把 MetroPT-3 原始传感器数据和 4 条公开故障报告，转换成一条可追溯、可计算、可导出的维护分析链：

`原始 CSV/PDF -> 数据质量审计 -> PostgreSQL -> SQL 指标 -> Streamlit 看板 -> 维护周报`

本项目只分析**已标注异常区间**。它不把区间解释为实际停机，不推断维修工时，也不提供预测或诊断能力。

![桌面看板](artifacts/screenshots/dashboard-desktop.png)

## 1. 业务问题

### 1.1 目标用户

- 负责单台 MetroPT-3 地铁空压机日常巡检和定期上报的维护工程师。
- 需要核对维护周报口径、数据质量和源记录依据的设备数据分析人员。

当前数据只有一台设备，因此平台不提供多设备排名，也不把单台设备的统计结果外推成车队结论。

### 1.2 当前人工方案及问题

典型人工流程是：读取原始 CSV 和设备传感器定期上报数据，查阅故障报告，在 Excel 中录入事件、写时间差公式、筛选指定周、汇总故障类型，最后手工整理周报。

这种方式存在以下问题：

- 时间格式、时区、缺口规则和指标公式散落在个人工作簿中，缺少统一版本。
- 原始传感器数据约有 151 万行，Excel 直接处理全部记录笨重，且容易误把数字量、脉冲量和模拟量混合聚合。
- 采集缺口、故障区间与缺口重叠、重复时间戳等问题通常没有被显式记录。
- 事件表与原始 CSV 行号之间缺少稳定追溯链。
- 周报口径依赖个人记忆，难以复现，也难以证明每个结论来自哪条 SQL 和哪条源记录。

### 1.3 平台方案

平台采用 PostgreSQL 保存统一口径的数据，使用 SQL 视图和函数计算指标，使用 Streamlit 提供时间筛选、事件追溯和周报下载。

代码结构可以类比为分层 MVC，但不宣称 Streamlit 是严格的传统 MVC 框架：

- Model：`sql/schema.sql`、`sql/metrics.sql` 和 `src/metropt/data_access.py`。
- View：`app.py` 中的 Streamlit 页面、图表、表格和下载控件。
- Controller：日期筛选、事件选择、数据库查询编排和周报生成函数。

第一版不训练机器学习模型。数据中只有 4 条公开故障报告，规模不足以支持可信的分类、预测或智能诊断声明。

## 2. 项目回答的问题

1. 每次标注故障持续多长时间？
2. 平均和最长标注故障持续时长是多少？
3. 相邻标注故障之间相隔多久？
4. 哪类故障累计持续时间最长？
5. 指定周期内发生了哪些故障？
6. 能否快速生成一份可追溯到 SQL 和源记录的维护周报？

## 3. 数据与统一口径

### 3.1 数据源

- 数据集：UCI MetroPT-3，DOI `10.24432/C5VW3R`。
- UCI 页面：https://archive.ics.uci.edu/dataset/791/metropt+3+dataset
- 原始 CSV：`data/raw/metropt3/MetroPT3(AirCompressor).csv`
- 原始说明 PDF：`data/raw/metropt3/Data Description_Metro.pdf`
- 压缩包：`data/raw/metropt+3+dataset.zip`
- 审计遥测范围：`2020-02-01T00:00:00Z` 至 `2020-09-01T03:59:50Z`
- 数据量：1,516,948 行、17 个字段。
- 采样口径：主采样间隔为 10 秒，约 0.1 Hz。来源 PDF 的频率文字与实际时间戳不一致，项目以实际 CSV 为准。
- 来源说明：原始文件通过公开镜像下载；文件大小与 UCI 公布值一致，但官方压缩包哈希对照尚未完成，详见 `docs/data_quality.md`。

原始文件保持只读，不由界面或清洗脚本覆盖。

### 3.2 数据质量规则

- 原始时间戳没有时区声明，项目固定按 UTC 零偏移解释，不执行夏令时墙钟平移。
- 已检查葡萄牙 `Europe/Lisbon` 2020-03-29 春季切换边界，并记录来源时区不确定性。
- 重复时间戳：0。
- 乱序记录：0。
- 缺口规则：相邻观测时间差大于 30 秒。
- 缺口区间：`[上一时间戳 + 10 秒, 下一时间戳)`。
- 全数据缺口：331 个，未观测 908.5981 小时。
- 故障区间与缺口取交集，不插值、不补造真实记录。

完整证据见 [docs/data_quality.md](docs/data_quality.md) 和 [artifacts/audit/audit_report.json](artifacts/audit/audit_report.json)。

### 3.3 字段处理

- 7 个模拟量：`TP2`、`TP3`、`H1`、`DV_pressure`、`Reservoirs`、`Oil_temperature`、`Motor_current`。
- 8 个数字量：`COMP`、`DV_eletric`、`Towers`、`MPG`、`LPS`、`Pressure_switch`、`Oil_level`、`Caudal_impulses`。
- 未识别出单调累计计数器。
- `Caudal_impulses` 实际为 0/1 脉冲信号，不是单调累计计数器，因此不求差分、不取均值冒充流量。
- 模拟量、数字量和脉冲量分别处理，不混合成无业务意义的综合指标。

### 3.4 指标定义

| 指标 | 定义 |
|---|---|
| 单次标注故障持续时长 | `ended_at - started_at` |
| 平均标注故障持续时长 | 当前周期内所选取标注故障持续时长的算术平均值 |
| 最长标注故障 | 当前周期内持续时长最大的标注故障事件 |
| 标注故障间隔 | 当前事件开始时间减去上一事件结束时间 |
| 故障类型累计持续时长 | 按 `failure_type` 汇总的标注故障持续时长 |
| 标注异常区间占有效监测时长比例 | 标注故障累计秒数除以周期内日历跨度扣除采集缺口后的有效监测秒数 |

周期筛选采用 `[开始时间, 结束时间)` 半开区间，事件按开始时间归入周期。当前 4 条事件均完整位于其所属周期内；如果存在跨周期事件，解读比例前应单独核对边界。

## 4. 数据模型与查询层

PostgreSQL 包含三张业务表：

| 表 | 作用 | 当前行数 |
|---|---|---:|
| `assets` | 单台空压机和数据工作约定 | 1 |
| `telemetry` | 统一 UTC 时间、17 个源字段映射后的遥测 | 1,516,948 |
| `failure_events` | 4 条标注故障、严重程度和原文维护备注 | 4 |

维护备注保留在 `failure_events` 中，不拆成虚假的工单闭环表。

数据库共有 8 个视图：`sql/schema.sql` 建立字段目录视图，`sql/metrics.sql` 建立其余 7 个分析视图，并提供按周期查询、Pareto、事件明细、事件追溯和首尾样本查询函数。主要对象包括：

- `telemetry_gaps`
- `failure_event_metrics`
- `failure_type_pareto`
- `data_quality_summary`
- `failure_overall_metrics`
- `failure_gap_overlap`
- `failure_event_gap_summary`
- `sensor_field_catalog`
- `report_period_quality(...)`
- `report_period_metrics(...)`
- `report_failure_pareto(...)`
- `report_failure_events(...)`
- `failure_event_trace(...)`
- `failure_event_samples(...)`

看板只查询预聚合视图和区间查询函数，不把 151 万行遥测一次性读入 pandas。

## 5. 看板与周报

Streamlit 页面包含四个工作区：

1. `运行总览`：标注故障时间轴、Pareto、指标卡、事件明细、日期筛选。
2. `事件追溯`：查看事件的源索引、CSV 行号、首尾原始样本和重叠缺口。
3. `周报导出`：选择自然周，生成并下载 HTML 或 Markdown 维护周报。
4. `口径与质量`：查看指标定义、周期缺口和 Known Issues。

周报包含所选周的标注故障、持续时长、类型、上一事件间隔、缺口质量提示、口径和限制。

示例产物：

- [HTML 周报](artifacts/weekly_reports/metropt3_weekly_20200601.html)
- [Markdown 周报](artifacts/weekly_reports/metropt3_weekly_20200601.md)
- [移动端看板截图](artifacts/screenshots/dashboard-mobile.png)
- [事件追溯截图](artifacts/screenshots/week-20200601-trace.png)
- [周报截图](artifacts/screenshots/week-20200601-report.png)

## 6. 启动方式

### 6.1 Docker Compose

前置条件：Docker Desktop 已启动，`docker compose version` 可用。

```powershell
cd "C:\Users\mengm\OneDrive\项目1"
docker compose up --build -d
docker compose ps -a
```

首次启动时，`loader` 会分块读取原始 CSV、建立表、写入遥测和事件，然后退出。`postgres` 和 `streamlit` 应保持运行；`loader` 成功完成后显示 `Exited (0)`。

访问地址：http://localhost:8501

健康检查：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8501/_stcore/health'
docker compose logs --tail 100 streamlit loader
```

数据库连接：

- 主机端口：`127.0.0.1:5434`
- 数据库：`metropt`
- 用户名：`metropt`
- 密码：`metropt`
- DSN：`postgresql://metropt:metropt@127.0.0.1:5434/metropt`

停止服务：

```powershell
docker compose down
```

数据保存在 Docker 命名卷 `metropt3_metropt_pgdata` 中。再次执行 `docker compose up` 时，loader 会识别已有完整数据并跳过重复加载。

### 6.2 本地审计与测试

安装依赖：

```powershell
py -m pip install -r requirements.txt
```

重跑数据审计：

```powershell
py scripts/audit.py
```

重跑入库脚本：

```powershell
$env:DATABASE_URL = 'postgresql://metropt:metropt@127.0.0.1:5434/metropt'
py scripts/load_db.py --apply-schema --apply-metrics --skip-existing --dsn $env:DATABASE_URL
```

运行测试：

```powershell
$env:DATABASE_URL = 'postgresql://metropt:metropt@127.0.0.1:5434/metropt'
py -m pytest -q
```

PostgreSQL 不可用时，依赖数据库的集成测试会跳过；要与本项目验收结果一致，应先启动 Docker Compose 再运行完整测试。

## 7. 审计基线与 Demo 周

4 条源故障记录：

| 事件 | 开始 UTC | 结束 UTC | 类型 | 持续时长 |
|---|---|---|---|---:|
| E01 | 2020-04-18 00:00 | 2020-04-18 23:59 | Air Leak | 23.9833 h |
| E02 | 2020-05-29 23:30 | 2020-05-30 06:00 | Air Leak | 6.5000 h |
| E03 | 2020-06-05 10:00 | 2020-06-07 14:30 | Air Leak | 52.5000 h |
| E04 | 2020-07-15 14:30 | 2020-07-15 19:00 | Air Leak | 4.5000 h |

全数据基线：

- 平均标注故障持续时长：21.8708 h。
- 最长标注故障：`E03`，52.5000 h。
- 累计标注故障持续时长：87.4833 h。
- 标注异常区间占有效监测时长比例：2.0793%。
- 4 条故障均为 `Air Leak`，所以第一版 Pareto 只有一个实际故障类型。

Demo 周 `2020-06-01T00:00:00Z` 至 `2020-06-08T00:00:00Z`：

- 1 个事件：`E03`。
- 标注故障持续时长：52.5000 h。
- 有效监测时长：141.2378 h。
- 采集缺口：10 个，未观测 26.7622 h。
- 标注异常区间占有效监测时长比例：37.1714%。
- `E03` 与 3 个缺口重叠 4.8206 h。
- 源索引范围：`8908100-9081240`。
- CSV 行号范围：`890811-908125`。
- 区间内遥测：17,315 行。

UI 日期控件按自然日含首尾处理，因此选择 `2020-06-01` 至 `2020-06-07`，对应上述半开 UTC 周。

## 8. n=1 业务对比实验

这是一次个人、脚本化的自我实验，不是用户调研，不估计总体收益。

### 8.1 人工流程

- 工具：Microsoft Excel COM 自动化。
- 操作：16 步。
- 实测操作段：8.632 秒，即约 0.144 分钟。
- 固定问题答案：最长事件为 `E03`，52.5 h；累计持续时长最高的类型为 `Air Leak`。
- 证据：[manual_benchmark.json](artifacts/business_comparison/manual_benchmark.json)、[manual_week_20200601.xlsx](artifacts/business_comparison/manual_week_20200601.xlsx)。
- 追溯限制：工作簿保留事件 ID、源报告时间和维护备注，但没有独立重建全部原始遥测缺口。

### 8.2 平台流程

- 工具：Playwright 驱动 Microsoft Edge。
- 操作：7 步。
- 实测操作段：4.626 秒，即约 0.077 分钟。
- 固定问题答案：最长事件为 `E03`，52.5 h；累计持续时长最高的类型为 `Air Leak`。
- 追溯证据：源索引、CSV 行号、17,315 条区间遥测、3 个重叠缺口均可在界面查看。
- 证据：[platform_benchmark.json](artifacts/business_comparison/platform_benchmark.json)、[平台周报](artifacts/business_comparison/platform_week_20200601.html)、[最终截图](artifacts/screenshots/platform-benchmark-final.png)。

### 8.3 如实解读

在这个狭窄的脚本化定义下，平台记录的交互段快于 Excel 脚本段，两个固定问题的答案一致。该差值只覆盖测试脚本开始后的操作时间，不包含：

- 平台的数据接入、开发、部署和维护时间。
- 学习、解释、人工理解和异常处理时间。
- 人工录入源故障报告的时间。
- 网络、数据库或 Docker 环境准备时间。

因此不能据此宣称普遍效率收益。平台的优势需要由口径统一、可复现查询和源记录追溯来证明，而不是由这一次秒表结果证明。

`platform_benchmark.exploratory.json` 和 `platform-benchmark-initial.png` 是探索性中间产物，不作为最终实验结论。

## 9. 测试与验收

测试覆盖：

- 时间戳转 UTC、排序和重复处理。
- 累计计数器差分边界。
- 故障时长计算。
- 故障类型累计排序。
- 缺口与故障区间的交集。
- 时间筛选和半开区间。
- 时间轴与 Pareto 图的业务口径。
- SQL 返回 4 条事件及审计基线。
- 周报内容、HTML 转义和空周处理。
- 数据库完整加载判断。

验收命令：

```powershell
$env:DATABASE_URL = 'postgresql://metropt:metropt@127.0.0.1:5434/metropt'
py -m pytest -q
```

当前完整测试结果记录为 `32 passed`。最终验收时以本次实际运行输出为准。

数据库快速核验：

```powershell
docker compose exec postgres psql -U metropt -d metropt -c "SELECT COUNT(*) AS telemetry_rows FROM telemetry;"
docker compose exec postgres psql -U metropt -d metropt -c "SELECT COUNT(*) AS failure_events FROM failure_events;"
```

## 10. 目录结构

```text
.
├── app.py
├── artifacts/
│   ├── audit/
│   ├── business_comparison/
│   ├── screenshots/
│   └── weekly_reports/
├── data/raw/
├── docs/data_quality.md
├── scripts/
│   ├── audit.py
│   ├── load_db.py
│   ├── platform_benchmark.spec.js
│   └── run_excel_benchmark.ps1
├── sql/
│   ├── schema.sql
│   └── metrics.sql
├── src/metropt/
│   ├── dashboard.py
│   ├── data_access.py
│   ├── processing.py
│   └── weekly_report.py
├── tests/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## 11. 已知问题与限制

1. 原始时间戳没有官方时区声明，UTC 是项目固定的可复现工作解释。
2. 原始压缩包来自公开镜像，尚未完成与 UCI 官方压缩包的字节级哈希对照。
3. `Caudal_impulses` 的公开语义与实际 0/1 脉冲值存在冲突，当前只按数字脉冲处理。
4. 遥测存在 331 个采集缺口，跨缺口连续观测假设不成立。
5. 故障报告只有 4 条，且全部为同一类型，不能据此建立可信的分类或预测模型。
6. 维护备注只作来源原文保留，不表示维修工单闭环。
7. 项目只包含一台设备，不做设备排名。
8. 本项目的“标注故障持续时长”不是维修时间，“标注故障间隔”不是可靠性模型参数。
9. 本项目计算的是标注异常区间占有效监测时长比例，不计算 OEE，不计算或宣称 MTTR，不使用 availability/可用率，不编造成本节省，不宣称故障预测、AI 诊断、MTBF 或 1 Hz 采样能力。

## 12. 复现证据索引

| 证据 | 文件 |
|---|---|
| 数据审计报告 | `docs/data_quality.md` |
| 机器可读审计结果 | `artifacts/audit/audit_report.json` |
| 缺口明细 | `artifacts/audit/gap_intervals.csv` |
| 事件审计明细 | `artifacts/audit/failure_events.csv` |
| 正式 Excel 实验 | `artifacts/business_comparison/manual_benchmark.json` |
| 正式平台实验 | `artifacts/business_comparison/platform_benchmark.json` |
| 平台实验周报 | `artifacts/business_comparison/platform_week_20200601.html` |
| 桌面截图 | `artifacts/screenshots/dashboard-desktop.png` |
| 移动端截图 | `artifacts/screenshots/dashboard-mobile.png` |
| 事件追溯截图 | `artifacts/screenshots/week-20200601-trace.png` |
| 周报截图 | `artifacts/screenshots/week-20200601-report.png` |
