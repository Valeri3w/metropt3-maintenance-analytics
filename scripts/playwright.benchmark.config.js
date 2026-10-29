const os = require("os");
const path = require("path");

module.exports = {
  testDir: ".",
  testMatch: "platform_benchmark.spec.js",
  timeout: 90_000,
  workers: 1,
  reporter: "line",
  outputDir: path.join(os.tmpdir(), `metropt-playwright-${Date.now()}`),
  use: {
    baseURL: "http://127.0.0.1:8501",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
};
