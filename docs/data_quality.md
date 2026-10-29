# MetroPT-3 数据质量审计

> 本文件由 `scripts/audit.py` 根据原始文件生成。源文件保持只读，所有审计结论均可由脚本重跑。

- 生成时间：`2026-10-27T11:11:09.608817Z`
- 审计状态：`pass_with_known_issues`
- 口径：只描述标注异常区间、遥测有效监测时长和数据质量，不把异常区间等同于设备停机或维修时间。

## 1. 数据源与时间范围

- 数据集：MetroPT-3，UCI DOI `10.24432/C5VW3R`。
- UCI 页面：https://archive.ics.uci.edu/dataset/791/metropt+3+dataset
- 下载镜像：https://www.kaggle.com/api/v1/datasets/download/joebeachcapital/metropt-3-dataset
- CSV：`data/raw/metropt3/MetroPT3(AirCompressor).csv`，218,300,507 字节，SHA256 `db30ccb4ea402e3c8bf2c99db06e288d4f2a772f6928f9dbe26a920d69793e24`。
- PDF：`data/raw/metropt3/Data Description_Metro.pdf`，81,208 字节，SHA256 `b00fac0e8899854078309bef4adaa480d82ecf14dc81c5097c3646973e824127`。
- 原始压缩包 SHA256：`6d901b67a5d9420286deb80e53e439db52f8986f2f619503d06860eed2ebe761`。
- 原始压缩包 MD5：`ddd269ad813b11841d6cec45d07939b7`。
- 经审计的遥测范围：`2020-02-01T00:00:00Z` 至 `2020-09-01T03:59:50Z`，统一标记为 UTC。
- 来源说明：Raw files were downloaded from a public UCI mirror because the direct UCI download was impractically slow. Mirror file sizes match the file sizes reported by UCI, but an official archive-level hash comparison was not completed.

## 2. 总行数与字段清单

- 实际数据行数：1,516,948。
- 字段数：17，含 1 个源行标识、1 个时间字段、7 个模拟量、8 个数字量。
- 时间解析失败：0。
- 各字段空值总数：0。
- CSV 字段顺序：`Unnamed: 0, timestamp, TP2, TP3, H1, DV_pressure, Reservoirs, Oil_temperature, Motor_current, COMP, DV_eletric, Towers, MPG, LPS, Pressure_switch, Oil_level, Caudal_impulses`。
- 源索引：最小值 `0`，最大值 `15169470`；递减次数 0。该字段是源文件索引，不是时间。
- 源索引相邻步长：`10`（1,516,947 次）；它不是时间，也不直接等同于数据行号。
- 来源 PDF 声称实例数为 15,169,480，而实际 CSV 为 1,516,948；项目以实际 CSV 和时间戳为准。
- 来源 PDF 的文字写有 1 Hz，但实际相邻时间戳以 10 秒为主，因此本项目使用约 0.1 Hz 的观测口径，不宣称 1 Hz。

## 3. 重复、乱序和缺口

- 重复时间戳：0。
- 乱序记录：0。
- 固定缺口规则：observed inter-sample delta > 30 seconds。
- 缺口数量：331。
- 缺口区间定义：`[previous_timestamp + 10 seconds, next_timestamp)`。
- 未观测时长：908.598 小时（3,270,953 秒）。
- 观测时长：4207.402 小时。
- 日历跨度覆盖率：82.24%。

相邻时间戳差的主要分布：

| 秒 | 出现次数 |
|---:|---:|
| 10 | 1,337,521 |
| 9 | 128,277 |
| 12 | 38,321 |
| 13 | 7,988 |
| 11 | 4,471 |
| 21 | 10 |
| 19 | 5 |
| 22 | 4 |
| 14 | 3 |
| 17 | 3 |

最大缺口：

- 缺口区间：`2020-04-25T01:11:01Z` 至 `2020-04-27T01:12:49Z`。
- 两侧样本：`2020-04-25T01:10:51Z`、`2020-04-27T01:12:49Z`。
- 未观测时长：48.030 小时。

## 4. 夏令时处理

- 审计边界：葡萄牙 `Europe/Lisbon` 2020-03-29 春季切换。
- 若源时间戳是本地墙钟时间，01:00 小时应在切换时缺失。
- 实际边界附近小时计数：2020-03-28T23:00:00: 330；2020-03-29T00:00:00: 363；2020-03-29T01:00:00: 363；2020-03-29T02:00:00: 364；2020-03-29T03:00:00: 363；2020-03-29T04:00:00: 363；2020-03-29T05:00:00: 363。
- 01:00 小时是否出现：`True`。
- Lisbon 在切换前偏移：UTC+0；切换后偏移：UTC+1。
- 处理决定：The source does not declare a timezone. The project fixes a zero-offset UTC interpretation for reproducibility. The absence of a missing 01:00 wall-clock hour at the Portuguese spring-forward boundary is consistent with this interpretation, but is not an authoritative source declaration.
- 因此本项目不执行任何夏令时墙钟平移；源字符串按零偏移标记为 UTC。

## 5. 字段类型表

| CSV 字段 | 类型 | 观测范围/取值 | 单位 | 说明 | 处理决定 |
|---|---|---|---|---|---|
| Unnamed: 0 | identifier | 0 至 15169470 | source row identifier | 源 CSV 行索引；相邻记录递增 10，不是时间 | 仅作源记录追溯标识 |
| timestamp | time | 时间戳 | UTC timestamp | 原始无时区时间戳，项目固定按 UTC 解释 | 按固定 UTC 工作约定处理 |
| TP2 | analog | -0.032 至 10.676 | bar | 压缩机压力 | 按连续模拟量处理，按要求保留精度 |
| TP3 | analog | 0.73 至 10.302 | bar | 气动面板压力 | 按连续模拟量处理，按要求保留精度 |
| H1 | analog | -0.036 至 10.288 | bar | 旋风分离器排放引起的压力 | 按连续模拟量处理，按要求保留精度 |
| DV_pressure | analog | -0.032 至 9.844 | bar | 干燥塔排放压降 | 按连续模拟量处理，按要求保留精度 |
| Reservoirs | analog | 0.712 至 10.3 | bar | 储气罐下游压力 | 按连续模拟量处理，按要求保留精度 |
| Oil_temperature | analog | 15.4 至 89.05 | degC | 油温 | 按连续模拟量处理，按要求保留精度 |
| Motor_current | analog | 0.02 至 9.295 | A | 电机单相电流 | 按连续模拟量处理，按要求保留精度 |
| COMP | digital_binary | 0/1 | 0/1 | 压缩机进气阀电信号 | 按 0/1 状态单独处理，不并入模拟量 |
| DV_eletric | digital_binary | 0/1 | 0/1 | 压缩机出口阀控制信号 | 按 0/1 状态单独处理，不并入模拟量 |
| Towers | digital_binary | 0/1 | 0/1 | 干燥塔选择信号 | 按 0/1 状态单独处理，不并入模拟量 |
| MPG | digital_binary | 0/1 | 0/1 | 低压启动电信号 | 按 0/1 状态单独处理，不并入模拟量 |
| LPS | digital_binary | 0/1 | 0/1 | 低压检测信号 | 按 0/1 状态单独处理，不并入模拟量 |
| Pressure_switch | digital_binary | 0/1 | 0/1 | 先导控制阀压力信号 | 按 0/1 状态单独处理，不并入模拟量 |
| Oil_level | digital_binary | 0/1 | 0/1 | 低油位检测信号 | 按 0/1 状态单独处理，不并入模拟量 |
| Caudal_impulses | digital_pulse | 0/1 | 0/1 | 流量计脉冲信号 | 按脉冲数字信号处理，不求差分、不取均值 |

- 识别出的模拟量字段：7 个。
- 识别出的数字量字段：8 个。
- 识别出的累计计数器：0 个。
- `Caudal_impulses` 实际取值为 0/1，下降沿次数 7,646，不是单调累计计数器；不执行累计量差分，也不把它求均值当作流量。

## 6. 故障事件有效性检查

| 内部 ID | 源编号 | 开始 UTC | 结束 UTC | 类型 | 严重程度 | 持续小时 | 区间内样本 | 源索引范围 |
|---|---:|---|---|---|---|---:|---:|---|
| E01 | 1 | 2020-04-18T00:00:00Z | 2020-04-18T23:59:00Z | Air Leak | High Stress | 23.9833 | 8657 | 5625640 至 5712200 |
| E02 | 1 | 2020-05-29T23:30:00Z | 2020-05-30T06:00:00Z | Air Leak | High Stress | 6.5000 | 2360 | 8407400 至 8430990 |
| E03 | 3 | 2020-06-05T10:00:00Z | 2020-06-07T14:30:00Z | Air Leak | High Stress | 52.5000 | 17315 | 8908100 至 9081240 |
| E04 | 4 | 2020-07-15T14:30:00Z | 2020-07-15T19:00:00Z | Air Leak | High Stress | 4.5000 | 1622 | 11710930 至 11727140 |

有效性结论：

- 4 条源故障记录均成功解析：`True`。
- 所有开始时间早于结束时间：`True`。
- 所有故障区间位于遥测范围内：`True`。
- 源 PDF 前两条记录都标为 `#1`；本审计保留源编号，另建 `E01` 至 `E04` 内部事件 ID，不修改来源文本。
- 时间字段按 `结束时间 - 开始时间` 计算，不额外加 1 分钟。

| 内部 ID | 维护备注 | 备注与事件结束的关系 | 区间内缺口数 | 缺口重叠小时 | 标注区间观测覆盖 |
|---|---|---|---:|---:|---:|
| E01 | 无 | 无 | 1 | 0.0950 | 99.60% |
| E02 | Maintenance on 30Apr at 12:00 | before_event_end | 0 | 0.0000 | 100.00% |
| E03 | Maintenance on 8Jun at 16:00 | after_event_end | 3 | 4.8206 | 90.82% |
| E04 | Maintenance on 16Jul at 00:00 | after_event_end | 1 | 0.0358 | 99.20% |

## 7. 审计用故障时长基线

- 平均标注故障持续时长：21.8708 小时。
- 最长标注故障：`E03`，52.5000 小时。
- 4 次标注故障累计持续时长：87.4833 小时。
- 故障类型 Pareto 首项：`Air Leak`，87.4833 小时。源数据四次均为 Air Leak，因此第一版 Pareto 只有一个实际类别。

相邻标注故障间隔：

| 从 | 到 | 间隔小时 |
|---|---|---:|
| E01 | E02 | 983.5167 |
| E02 | E03 | 148.0000 |
| E03 | E04 | 912.0000 |

缺口与故障区间重叠：

- `E01` 1 个缺口，未观测 0.0950 小时；`E03` 3 个缺口，未观测 4.8206 小时；`E04` 1 个缺口，未观测 0.0358 小时。
- 故障区间内不插值、不补造记录；后续比例指标只使用有效监测时长。

## 8. 问题、影响与处理决定

| 问题 | 证据 | 影响 | 处理决定 |
|---|---|---|---|
| 源文件未声明时区 | PDF 中未检出 UTC/GMT/timezone 声明；2020-03-29 的 01 点仍存在 | 绝对时间解释存在来源不确定性 | 固定按 UTC 零偏移工作解释，保留原始字符串并登记 Known Issue |
| CSV 与文档实例数/频率不一致 | PDF 声称 15169480 个实例、约 1 Hz；实际 1,516,948 行、主间隔 10 秒 | 若照抄文档会错误计算 | 以实际 CSV 行为和时间差为准，README/图表统一使用约 0.1 Hz |
| 源事件编号重复 | 前两条记录均为 `#1` | 无法仅用源编号作主键 | 保留源编号，新增内部 ID `E01` 至 `E04` |
| 第二条维护备注疑有日期笔误 | `Maintenance on 30Apr at 12:00` 早于 5 月故障 | 直接修正会篡改来源 | 原样保留备注，不参与核心指标 |
| 数字脉冲字段易被误当累计量 | `Caudal_impulses` 仅为 0/1 且有下降沿 | 求差分或均值会制造无意义指标 | 按数字脉冲字段单独处理 |
| 遥测存在大缺口 | 共 331 个缺口，未观测 908.598 小时 | 连续观测假设不成立 | 固定大于 30 秒为缺口，比例指标扣除缺口 |
| 故障区间可能覆盖缺口 | 见上一节重叠统计 | 把区间全部视为连续观测会高估证据密度 | 暴露缺口重叠，不插值 |
| 镜像下载来源 | UCI 直连过慢，使用公开镜像；文件大小匹配 UCI | 来源仍应引用 UCI | 记录镜像 URL 和全部哈希，登记未完成官方包哈希核验 |

## 9. 仍未解决的问题

- 原始系统是否确实以 UTC 写入时间戳，仍需数据提供方说明。
- 故障报告时间与遥测时间是否使用同一时区约定，来源未说明。
- 官方 UCI 压缩包与镜像压缩包的字节级哈希尚未比对。
- 第二条维护备注中的 `30Apr` 是否为 `30May` 笔误，不能从现有材料确认。
- 采样间隔存在 9、12、13 秒等波动，本阶段不重采样；后续按 SQL 和时间窗口处理。

## 10. Known Issues

1. 时区是固定工作解释，不是来源明确声明；绝对时间解释仍有残余风险。
2. 原始包来自公开镜像，已完成文件大小与本地哈希记录，但未完成与 UCI 官方压缩包的哈希对照。
3. `Caudal_impulses` 的文档语义与观测值冲突；当前只按数字脉冲处理。
4. 故障报告中的维护备注只作为来源文本保留，不构造维修工单或维修时长。
5. 标注异常区间不表示设备必然停机，也不表示维修开始或结束时间。
6. 缺口区间内无数据；后续所有异常区间比例必须使用有效监测时长。

## 11. 审计停止条件核对

| 停止条件 | 结果 |
|---|---|
| 4 次故障区间能正确还原 | 通过，解析 4 条且时间边界完整 |
| 时间统一为 UTC | 通过项目固定解释；来源时区不确定性已登记 |
| 重复、乱序、缺口有固定规则 | 通过 |
| 所有字段完成分类 | 通过，7 模拟量 + 8 数字量 + 时间 + 标识 |
| 每个异常有处理决定或 Known Issue | 通过 |
| 未解决问题不影响核心区间与时长 | 当前区间、时长和 SQL 口径可复现；绝对时区仍需外部确认 |

## 12. 复现方式

```powershell
py -m pip install -r requirements.txt
py scripts/audit.py
```

脚本输出：

- `docs/data_quality.md`：本审计报告。
- `artifacts/audit/audit_report.json`：机器可读证据。
- `artifacts/audit/gap_intervals.csv`：全部缺口区间。
- `artifacts/audit/failure_events.csv`：4 条故障事件及其追溯样本。
