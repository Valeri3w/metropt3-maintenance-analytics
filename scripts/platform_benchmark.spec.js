const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");

test("fixed-week platform benchmark", async ({ page }) => {
  const startedAt = new Date();
  const started = performance.now();
  const steps = [];
  let stepNumber = 0;
  const comparisonDir = path.join(
    __dirname,
    "..",
    "artifacts",
    "business_comparison",
  );
  const screenshotPath = path.join(
    __dirname,
    "..",
    "artifacts",
    "screenshots",
    "platform-benchmark-final.png",
  );
  const reportPath = path.join(
    comparisonDir,
    "platform_week_20200601.html",
  );

  function record(action, evidence) {
    stepNumber += 1;
    steps.push({
      order: stepNumber,
      action,
      elapsed_ms: Math.round((performance.now() - started) * 10) / 10,
      evidence,
    });
  }

  async function setDate(field, value) {
    const parts = value.split("-");
    for (const [type, part] of [
      ["year", parts[0]],
      ["month", parts[1]],
      ["day", parts[2]],
    ]) {
      const segment = field.locator(`[data-type="${type}"]`);
      await segment.click();
      await segment.press("Control+A");
      await segment.pressSequentially(part, { delay: 50 });
      await segment.press("Tab");
    }
  }

  await page.goto("/");
  const pageHeading = page.getByRole("heading", {
    name: "MetroPT-3 标注故障分析",
  });
  await expect(pageHeading).toBeVisible();
  await page.waitForFunction(
    () => document.body.innerText.includes("1,516,948 条遥测"),
    null,
    { timeout: 30_000 },
  );
  record(
    "Open the platform",
    "Streamlit dashboard loaded with 1,516,948 telemetry rows and 4 source events",
  );

  const startField = page.locator('[data-range-field="start"]');
  const endField = page.locator('[data-range-field="end"]');
  await setDate(startField, "2020-06-01");
  await setDate(endField, "2020-06-07");
  await endField.locator('[data-type="day"]').press("Enter");
  await pageHeading.click();
  await expect(startField).toContainText("2020");
  await expect(startField).toContainText("06");
  await expect(startField).toContainText("01");
  await expect(endField).toContainText("2020");
  await expect(endField).toContainText("06");
  await expect(endField).toContainText("07");
  record(
    "Select the fixed week",
    "Date controls set to 2020-06-01 through 2020-06-07 inclusive, "
      + "representing the half-open UTC week 2020-06-01T00:00Z to "
      + "2020-06-08T00:00Z",
  );

  await page.waitForFunction(
    () => document.body.innerText.includes(
      "周期：2020-06-01 至 2020-06-07（UTC）",
    ),
    null,
    { timeout: 30_000 },
  );
  const contextBar = page.locator(".context-bar");
  await expect(contextBar).toContainText("有效监测：141.24 h");
  await expect(contextBar).toContainText("采集缺口：10 个");
  await expect(contextBar).toContainText("未观测：26.76 h");
  const dashboardText = await page.locator("body").innerText();
  expect(dashboardText).toContain("标注故障事件\n1");
  expect(dashboardText).toContain("平均标注故障持续时长\n52.50 h");
  expect(dashboardText).toContain("E03 · 52.50 h");
  expect(dashboardText).toContain("标注异常区间占有效监测时长\n37.17%");
  record(
    "Verify the selected-week metrics",
    "One event; average and longest annotated duration are both 52.50 h; "
      + "E03 is Air Leak; annotated share is 37.17% of effective monitoring time",
  );

  await page.getByRole("tab", { name: "事件追溯" }).click();
  const eventSelector = page.getByRole("combobox", { name: "选择事件" });
  await expect(eventSelector).toHaveValue(/^E03 · Air Leak/);
  const tracePanel = page.getByRole("tabpanel", { name: "事件追溯" });
  await expect(tracePanel).toContainText("源索引范围");
  const traceText = await tracePanel.innerText();
  expect(traceText).toContain("E03 · Air Leak");
  expect(traceText).toContain("区间内遥测记录\n17,315");
  expect(traceText).toContain("CSV 行号范围\n890811–908125");
  expect(traceText).toContain("源索引范围\n8908100–9081240");
  expect(traceText).toContain(
    "该标注区间与 3 个采集缺口重叠",
  );
  record(
    "Open E03 event trace",
    "Source indices 8908100-9081240, CSV rows 890811-908125, "
      + "17,315 telemetry rows, and 3 overlapping gaps are visible",
  );

  await page.getByRole("tab", { name: "周报导出" }).click();
  const htmlDownloadButton = page.getByRole("button", {
    name: /下载 HTML 周报/,
  });
  await expect(htmlDownloadButton).toBeVisible({ timeout: 30_000 });
  const weekSelector = page.getByRole("combobox", {
    name: "周报周期（周一至周日 UTC）",
  });
  await expect(weekSelector).toHaveValue(/^E03 所在周/);
  const reportPanel = page.getByRole("tabpanel", { name: "周报导出" });
  await expect(reportPanel).toContainText("周内标注事件");
  const reportText = await reportPanel.innerText();
  expect(reportText).toContain(
    "E03 所在周 · 2020-06-01 至 2020-06-07",
  );
  expect(reportText).toContain("周内标注事件\n1");
  expect(reportText).toContain("最长标注故障\nE03 · 52.50 h\nAir Leak");
  expect(reportText).toContain("周期有效监测\n141.24 h");
  expect(reportText).toContain("标注异常区间占比\n37.17%");
  expect(reportText).toContain("148.0000 h");
  record(
    "Open the weekly report",
    "The report answers both fixed questions: E03 is the longest event "
      + "at 52.50 h, and Air Leak has the highest cumulative duration at 52.50 h",
  );

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    htmlDownloadButton.click(),
  ]);
  await download.saveAs(reportPath);
  const downloadedReport = fs.readFileSync(reportPath, "utf8");
  expect(downloadedReport).toContain("E03");
  expect(downloadedReport).toContain("Air Leak");
  expect(downloadedReport).toContain("52.5000 h");
  expect(downloadedReport).toContain("2020-06-01 00:00 UTC");
  expect(downloadedReport).toContain("2020-06-08 00:00 UTC");
  record(
    "Download and inspect the HTML report",
    "Downloaded report is non-empty and contains E03, Air Leak, "
      + "52.5000 h, and the 2020-06-01/2020-06-08 half-open UTC bounds",
  );

  await page.screenshot({
    path: screenshotPath,
    fullPage: true,
  });
  record(
    "Capture final evidence",
    "Saved the final browser screenshot and exported HTML report",
  );

  const completedAt = new Date();
  const result = {
    experiment: "personal_n_1_platform_browser_self_experiment",
    disclosure:
      "This is not a user study. It measures one instrumented browser "
      + "workflow and does not include learning, interpretation, or manual "
      + "data-entry time. It does not estimate a population-level time saving.",
    tool: "Playwright 1.x with Microsoft Edge",
    application_url: "http://127.0.0.1:8501",
    week_started_at_utc: "2020-06-01T00:00:00Z",
    week_ended_at_utc: "2020-06-08T00:00:00Z",
    selected_date_range_note:
      "The UI date range is inclusive, so 2020-06-01 through 2020-06-07 "
      + "represents the half-open UTC week ending at 2020-06-08T00:00:00Z.",
    started_at_utc: startedAt.toISOString(),
    completed_at_utc: completedAt.toISOString(),
    elapsed_seconds:
      Math.round(((performance.now() - started) / 1000) * 1000) / 1000,
    operation_count: steps.length,
    answers: {
      weekly_event_count: 1,
      longest_event_id: "E03",
      longest_duration_hours: 52.5,
      highest_duration_type: "Air Leak",
      highest_type_duration_hours: 52.5,
    },
    traceable_to_source_records: true,
    traceability_evidence: {
      source_index_range: "8908100-9081240",
      csv_row_number_range: "890811-908125",
      telemetry_rows_in_annotation: 17315,
      overlapping_gap_count: 3,
    },
    artifacts: {
      screenshot: screenshotPath,
      downloaded_html_report: reportPath,
    },
    steps,
  };
  fs.writeFileSync(
    path.join(comparisonDir, "platform_benchmark.json"),
    JSON.stringify(result, null, 2),
    "utf8",
  );
});
